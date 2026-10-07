// 말 한 마디 -> 카드 한 장. 번호와 특이사항을 받는 상태기계.
//
// 서류철 140여 개를 넘기면서 특이사항이 있는 것만 불러 주는 흐름이다.
//
//   [번호 대기]  "천백이십"        -> 1120 을 들고 [내용 대기] 로
//   [내용 대기]  "대차"            -> 카드 저장, 다시 [번호 대기]
//   한 호흡     "천백이십 대차"    -> 바로 카드 저장
//
// 지켜야 할 것: 기록이 조용히 사라지지 않는다.
//   - 내용을 기다리는 중에 숫자가 들리면 그건 특이사항이 아니라 다음 차다.
//     앞 차는 '내용 없음' 카드로 남겨 두고 넘어간다 (버리지 않는다).
//   - 명부에 없는 번호도 막지 않는다. 'unknown' 으로 표시만 한다.
//
// 브라우저 API를 쓰지 않는 순수 로직이라 테스트 페이지에서 그대로 검사한다.

import { extractSequence } from '../../src/plate.js?v=202610080038';
import { isKnown } from './roster.js?v=202610080038';
import { workDate } from './workdate.js?v=202610080038';

// 공백·쉼표는 extractSequence 가 지우고 본다. 같은 규칙으로 지워야 위치가 맞는다.
const SKIP_CHARS = /[\s,.\-·]/;

// 단위만으로 된 말("천", "천백")은 아직 번호가 아니다.
// 사파리가 말 중간을 확정해 버렸을 때 1000 이 들어가는 것을 막는다.
const UNIT_ONLY = /^[천백십]+$/;

/**
 * 지운 문자열의 위치 -> 원문 위치 대응표.
 * 번호 뒤에 남은 말을 **원문 그대로**(띄어쓰기 살려서) 떼어내기 위한 것.
 * "천백이십 브레이크 소음" 에서 "브레이크 소음" 을 얻어야 한다 — 붙여 버리면
 * 엑셀에 "브레이크소음" 으로 들어가 기존 기록과 모양이 달라진다.
 */
function stripMap(text) {
  let stripped = '';
  const at = [];
  for (let i = 0; i < text.length; i++) {
    if (SKIP_CHARS.test(text[i])) continue;
    stripped += text[i];
    at.push(i);
  }
  return { stripped, at };
}

/** 들린 말 전체가 번호 하나뿐인가. 그렇다면 그 번호(문자열)를, 아니면 null */
export function barePlate(text) {
  const t = onlyPlate(text);
  return t ? t.plate : null;
}

/** 들린 말 전체가 번호 하나뿐인가. 그렇다면 그 토큰을, 아니면 null */
function onlyPlate(text) {
  const tokens = extractSequence(text);
  if (tokens.length !== 1) return null;
  const t = tokens[0];
  if (t.type !== 'plate' || UNIT_ONLY.test(t.raw)) return null;
  return stripMap(text).stripped === t.raw ? t : null;
}

/**
 * 들린 말 전체가 명령 하나뿐인가. 'back' | 'skip' | null
 *
 * 말 중간에 들어 있는 것은 명령으로 보지 않는다 — "노선 안내방송 없음" 이
 * 건너뛰기로, "운행 취소" 가 되돌리기로 읽히면 내용이 통째로 사라진다.
 */
function onlyCommand(text) {
  const tokens = extractSequence(text);
  if (tokens.length !== 1) return null;
  const t = tokens[0];
  if (t.type !== 'back' && t.type !== 'skip') return null;
  return stripMap(text).stripped === t.raw ? t.type : null;
}

/** 첫 낱말과 나머지 */
function splitFirstWord(text) {
  const m = String(text).match(/^\s*(\S+)\s*([\s\S]*)$/);
  return m ? [m[1], m[2].trim()] : [String(text).trim(), ''];
}

/** 그 말 안의 첫 번호 토큰 */
function firstPlate(text) {
  return extractSequence(text).find((t) => t.type === 'plate' && !UNIT_ONLY.test(t.raw)) || null;
}

/**
 * 번호가 원문에서 실제로 차지한 글자.
 *
 * 토큰의 raw 는 숫자 뭉치 **전체**다. 공백이 지워지면 "1122 15" 가 "112215" 로
 * 붙어 한 덩어리가 되는데, 번호로 쓰인 것은 앞 네 자리뿐이다. raw 를 그대로
 * 믿고 건너뛰면 뒤의 "15" 가 내용에서 사라진다 — 실제로 그랬다.
 */
function plateSpan(tok) {
  if (/^\d+$/.test(tok.raw)) return tok.raw.slice(0, Math.min(4, tok.raw.length));
  // 한국식 수사는 글자 수로 자를 수 없다. 그 번호가 되는 가장 짧은 앞부분을 찾는다.
  for (let i = 1; i <= tok.raw.length; i++) {
    const head = tok.raw.slice(0, i);
    const t = extractSequence(head);
    if (t.length === 1 && t[0].type === 'plate' && t[0].plate === tok.plate) return head;
  }
  return tok.raw;
}

/** 번호 뒤에 남은 말을 원문에서 떼어낸다 */
function restAfter(text, raw) {
  const { stripped, at } = stripMap(text);
  const i = stripped.indexOf(raw);
  if (i < 0) return '';
  const end = i + raw.length;
  if (end >= at.length) return '';
  return text.slice(at[end]).trim();
}

export function createState(date = workDate()) {
  return { date, phase: 'plate', pending: null, cards: [] };
}

// 사파리는 자릿수를 나타내는 말을 숫자로 바꿔 버린다.
// "사십분경" -> "40분 10,000,000,000,000,000" (경 = 10^16). 일지에 그런 수가 쓰일
// 일은 없으므로 말로 되돌린다. 억·만은 "삼만원" 처럼 실제로 쓰일 수 있어 두 개만 본다.
const BIG_NUMBER_WORDS = [
  [/10,?000,?000,?000,?000,?000/g, '경'],
  [/1,?000,?000,?000,?000/g, '조'],
];

function tidy(text) {
  let out = text;
  for (const [re, word] of BIG_NUMBER_WORDS) out = out.replace(re, word);
  return out.replace(/\s{2,}/g, ' ').trim();
}

function makeCard(plate, symptom, now) {
  const text = tidy(symptom || '');
  return {
    plate,
    symptom: text,
    status: !text ? 'nosymptom' : (isKnown(plate) ? 'ok' : 'unknown'),
    at: now.toISOString(),
  };
}

/**
 * 카드를 넣는다. 같은 차가 오늘 또 들어오면 덮어쓴다 —
 * PC 프로그램이 같은 차량번호를 다시 입력했을 때 기존 행을 고치는 것과 같은 규칙.
 */
function put(state, card) {
  const i = state.cards.findIndex((c) => c.plate === card.plate);
  if (i >= 0) {
    const before = state.cards[i].symptom;    // 변경 기록에 남길 '바뀌기 전'
    state.cards[i] = card;
    return { type: 'card', card, updated: true, before };
  }
  state.cards.push(card);
  return { type: 'card', card, updated: false };
}

/** 내용을 못 받은 채 넘어가는 차를 카드로 남긴다 */
function parkPending(state, now) {
  if (!state.pending) return null;
  const card = makeCard(state.pending.plate, '', now);
  const ev = put(state, card);
  state.pending = null;
  return ev;
}

/**
 * 확정된(사파리가 isFinal 로 준) 말 한 마디를 처리한다.
 *
 * complete 플래그는 보지 않는다. "천백이십" 은 "천백이십사" 가 될 수 있어
 * complete=false 로 오지만, 여기 들어왔다는 것은 이미 말이 멎었다는 뜻이다.
 * 말하는 중간에 섣불리 넣는 문제는 호출하는 쪽(음성 래퍼)이 막는다.
 */
export function handleUtterance(state, text, now = new Date()) {
  const raw = String(text || '');
  const cmd = onlyCommand(raw);          // 말 전체가 명령일 때만 명령이다
  const back = cmd === 'back';
  const skip = cmd === 'skip';

  // ── 내용을 기다리는 중 ────────────────────────────────────────────
  // 들린 말은 그냥 내용이다. 번호가 섞여 있어도 마찬가지다 —
  // 실제 일지 220건 중 98건(45%)이 내용 안에 번호를 담고 있고
  // ("1118 대차", "1138-> 1142 차량 교체"), 55건(25%)은 번호로 시작한다.
  // 번호만 달랑 말했을 때에만 다음 차로 넘어간다. 내용이 번호 하나뿐인 경우는
  // 그 220건에 한 건도 없었으므로 이 예외는 안전하다.
  if (state.phase === 'symptom' && state.pending) {
    if (back) return undo(state);
    if (skip) {
      const had = state.pending;
      state.pending = null;
      state.phase = 'plate';
      return { type: 'skip', plate: had.plate, parked: null };
    }
    if (!onlyPlate(raw)) {
      const plate = state.pending.plate;
      state.pending = null;
      state.phase = 'plate';
      return put(state, makeCard(plate, raw, now));
    }
    // 번호만 말했다 — 아래로 내려가 다음 차로 넘어간다 (앞 차는 '내용 없음' 으로 남는다)
  }

  // ── 번호를 기다리는 중 ────────────────────────────────────────────
  // 원문에서 번호 바로 뒤를 떼어내 내용으로 둔다.
  //
  // 다만 띄어 말한 두 번호가 한 덩어리로 읽히는 일이 있다 — 공백이 지워지면
  // "천삼백오십이 1305" 가 "천삼백오십이1305" 가 되어 22655 처럼 엉뚱한 값이 된다.
  // 그때만 첫 낱말을 믿는다. (첫 낱말로 찾은 번호와 전체에서 찾은 번호가 다르면
  // 그런 경우다.)
  const wholePlate = firstPlate(raw);
  const [head, tail] = splitFirstWord(raw);
  const headPlate = firstPlate(head);

  let plateTok = wholePlate;
  let rest = wholePlate ? restAfter(raw, plateSpan(wholePlate)) : '';
  if (headPlate && wholePlate && headPlate.plate !== wholePlate.plate) {
    plateTok = headPlate;
    rest = tail;
  }
  // "천백이십오호," 의 '호' 와 뒤따르는 쉼표는 번호에 붙는 말이지 내용이 아니다
  rest = rest.replace(/^[\s,.·]+/, '').replace(/^호[\s,.·]*/, '').trim();

  if (plateTok) {
    const parked = state.pending && state.pending.plate !== plateTok.plate
      ? parkPending(state, now) : null;
    state.pending = null;

    // "천백이십 없음" — 특이사항 없는 차. 적지 않고 넘어간다.
    // 뒤에 붙은 말이 통째로 명령일 때만이다 ("천백이십 안내방송 없음" 은 내용이다).
    if (rest && onlyCommand(rest)) {
      state.phase = 'plate';
      return { type: 'skip', plate: plateTok.plate, parked };
    }

    // 한 호흡에 다 불렀다
    if (rest) {
      state.phase = 'plate';
      const ev = put(state, makeCard(plateTok.plate, rest, now));
      return { ...ev, parked };
    }

    // 번호만 불렀다 — 내용을 기다린다
    state.pending = { plate: plateTok.plate, known: isKnown(plateTok.plate) };
    state.phase = 'symptom';
    return { type: 'pending', plate: plateTok.plate, known: state.pending.known, parked };
  }

  if (back) return undo(state);

  if (skip) {
    const had = state.pending;
    state.pending = null;
    state.phase = 'plate';
    return { type: 'skip', plate: had ? had.plate : null, parked: null };
  }

  return { type: 'ignored', heard: raw };
}

/** 기다리는 번호가 있으면 그것을, 없으면 직전 카드를 되돌린다 */
export function undo(state) {
  if (state.pending) {
    const plate = state.pending.plate;
    state.pending = null;
    state.phase = 'plate';
    return { type: 'undo', plate, from: 'pending' };
  }
  const card = state.cards.pop();
  state.phase = 'plate';
  return card ? { type: 'undo', plate: card.plate, card, from: 'card' }
              : { type: 'undo', plate: null, from: 'none' };
}

/**
 * 키패드로 번호를 넣는다. 음성 파서를 거치지 않는다.
 * 앞자리 1은 고정이라 뒤 세 자리만 받는다.
 */
export function setPlate(state, plate, now = new Date()) {
  const parked = state.pending && state.pending.plate !== plate ? parkPending(state, now) : null;
  state.pending = { plate, known: isKnown(plate) };
  state.phase = 'symptom';
  return { type: 'pending', plate, known: state.pending.known, parked };
}

/** 카드 한 장을 지운다 (목록에서 손으로). 지운 카드를 돌려준다 — 기록에 남기려고. */
export function removeCard(state, plate) {
  const i = state.cards.findIndex((c) => c.plate === plate);
  if (i < 0) return null;
  return state.cards.splice(i, 1)[0];
}

/** PC 로 보낼 것만 추린다 — 내용 없는 카드는 보내지 않는다(엑셀에 빈 줄이 생기므로) */
export function sendable(state) {
  return state.cards.filter((c) => c.symptom);
}
