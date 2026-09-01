// 음성 인식 결과 문자열 -> 차량번호 / 명령 토큰 시퀀스
//
// 차고지 규칙: 모든 차량번호는 4자리이며 첫 자리는 항상 1 (1000번대).
// 이 제약을 이용해 3자리만 인식돼도 복원하고, 첫 자리 오인식도 교정한다.
//
// 브라우저 API를 쓰지 않는 순수 로직이라 node로 그대로 테스트 가능.

const DIGIT = {
  '공': 0, '영': 0, '빵': 0,
  '일': 1, '이': 2, '삼': 3, '사': 4, '오': 5,
  '육': 6, '륙': 6, '칠': 7, '팔': 8, '구': 9,
};

const UNIT = { '천': 1000, '백': 100, '십': 10 };

// 긴 것부터 검사해야 "이전"이 "이"로 먼저 잘리지 않는다
const COMMANDS = [
  ['공차', 'skip'], ['빈자리', 'skip'], ['빈칸', 'skip'], ['패스', 'skip'],
  ['스킵', 'skip'], ['없음', 'skip'], ['비었음', 'skip'], ['비어있음', 'skip'],
  ['이전', 'back'], ['정정', 'back'], ['뒤로', 'back'], ['취소', 'back'],
  ['잘못', 'back'], ['백스페이스', 'back'],
];

const isDigitChar = (ch) => ch >= '0' && ch <= '9';
const isNumChar = (ch) => isDigitChar(ch) || ch in DIGIT || ch in UNIT;

/** "천사십이" 같은 한자어 수사를 정수 배열로. 천 단위가 다시 나오면 새 숫자로 끊는다. */
function parseSinoRun(run) {
  const out = [];
  let total = 0;
  let cur = 0;
  let seen = false;

  for (const ch of run) {
    if (isDigitChar(ch)) {
      cur = cur * 10 + Number(ch);
      seen = true;
    } else if (ch in DIGIT) {
      cur = DIGIT[ch];
      seen = true;
    } else if (ch in UNIT) {
      const unit = UNIT[ch];
      // 이미 천 단위를 채운 뒤 또 천이 나오면 다음 차량번호가 시작된 것
      if (unit === 1000 && total >= 1000) {
        out.push(total + cur);
        total = 0;
        cur = 0;
      }
      total += (cur || 1) * unit;
      cur = 0;
      seen = true;
    }
  }
  if (seen) out.push(total + cur);
  return out.filter((n) => n > 0);
}

/** "일공사이" / "1042" 처럼 자릿수를 하나씩 읽은 것을 숫자 문자열로. */
function parseDigitRun(run) {
  let s = '';
  for (const ch of run) {
    if (isDigitChar(ch)) s += ch;
    else if (ch in DIGIT) s += String(DIGIT[ch]);
  }
  return s;
}

/** 자릿수 문자열을 4자리 단위로 끊는다. "10421134" -> ["1042","1134"] */
function chunkDigits(s) {
  const out = [];
  let i = 0;
  while (s.length - i >= 4) {
    out.push(s.slice(i, i + 4));
    i += 4;
  }
  const rest = s.slice(i);
  if (rest.length >= 3) out.push(rest);
  return out;
}

/**
 * 자릿수 문자열 -> 차량번호. 1000번대 고정 규칙을 적용한다.
 * confidence: high(그대로) / assumed(앞자리 1 보충) / corrected(앞자리 1로 교정)
 */
export function normalizePlate(digits) {
  if (!digits) return null;
  let s = digits;
  if (s.length > 4) s = s.slice(-4);

  if (s.length === 4) {
    if (s[0] === '1') return { plate: s, confidence: 'high' };
    return { plate: '1' + s.slice(1), confidence: 'corrected', heard: s };
  }
  if (s.length === 3) {
    return { plate: '1' + s, confidence: 'assumed', heard: s };
  }
  return null;
}

const ONES = ['', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구'];

/**
 * 1042 -> "천사십이" 처럼 한국식으로 읽는다.
 * 확인용으로 되읽어 줄 때 쓰며, extractSequence 의 정확한 역함수다.
 * 1000번대만 다루면 되므로 만 단위는 고려하지 않는다.
 */
export function toKoreanSino(plate) {
  const n = Number(plate);
  if (!Number.isInteger(n) || n < 1 || n > 9999) return String(plate);

  const digits = [Math.floor(n / 1000) % 10, Math.floor(n / 100) % 10, Math.floor(n / 10) % 10, n % 10];
  const units = ['천', '백', '십', ''];
  let out = '';

  digits.forEach((d, i) => {
    if (d === 0) return;
    // 1000/100/10 자리의 1은 "일천"이 아니라 그냥 "천"으로 읽는다
    out += (d === 1 && i < 3) ? units[i] : ONES[d] + units[i];
  });

  return out;
}

/**
 * 인식 문장 전체에서 명령/차량번호를 나온 순서대로 뽑는다.
 * iOS 사파리는 한 세션의 인식 결과를 누적해서 돌려주므로, 앱은 이 배열의
 * 길이와 이미 처리한 개수를 비교해 새로 늘어난 것만 반영하면 된다.
 */
export function extractSequence(text) {
  if (!text) return [];
  const s = String(text).replace(/[\s,.\-·]/g, '');
  const tokens = [];
  let i = 0;

  while (i < s.length) {
    // 1) 명령어 우선 ("이전"이 숫자 2로 오해되지 않도록)
    let matched = null;
    for (const [word, type] of COMMANDS) {
      if (s.startsWith(word, i)) { matched = [word, type]; break; }
    }
    if (matched) {
      tokens.push({ type: matched[1], raw: matched[0] });
      i += matched[0].length;
      continue;
    }

    // 2) 숫자로 읽을 수 있는 구간을 최대한 길게
    if (isNumChar(s[i])) {
      let j = i;
      while (j < s.length && isNumChar(s[j])) {
        // 숫자 구간 안에 명령어가 끼어 있으면 거기서 끊는다 ("천사십이공차")
        let stop = false;
        for (const [word] of COMMANDS) {
          if (s.startsWith(word, j)) { stop = true; break; }
        }
        if (stop) break;
        j++;
      }
      const run = s.slice(i, j);
      const hasUnit = [...run].some((ch) => ch in UNIT);

      if (hasUnit) {
        for (const n of parseSinoRun(run)) {
          const p = normalizePlate(String(n));
          if (p) tokens.push({ type: 'plate', ...p, raw: run });
        }
      } else {
        for (const chunk of chunkDigits(parseDigitRun(run))) {
          const p = normalizePlate(chunk);
          if (p) tokens.push({ type: 'plate', ...p, raw: run });
        }
      }
      i = j;
      continue;
    }

    i++;
  }

  return tokens;
}
