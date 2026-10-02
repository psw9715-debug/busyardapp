// 음성 인식 래퍼 — "한 마디 = 글자 한 덩어리"
//
// 순회앱의 src/voice.js 와 왜 따로 두는가
//   저쪽은 들은 말에서 **번호와 명령만** 골라 토큰으로 넘긴다. 자리마다 번호 하나를
//   받는 일에는 그게 맞다. 여기는 번호 뒤에 "브레이크 소음" 같은 **자유로운 말**이
//   따라오므로 글자 그대로가 필요하다. voice.js 는 번호가 없는 말은 아무것도
//   넘기지 않으므로 그대로는 쓸 수 없고, 고치면 매일 돌고 있는 순회앱이 흔들린다.
//   그래서 저쪽에서 비싸게 얻은 교훈만 가져와 이 모양으로 다시 썼다.
//
// 가져온 교훈
//   - 사파리는 continuous 를 무시하고 발화가 끝나면 세션을 닫는다 -> onend 마다 다시 켠다
//   - 한 세션의 전사를 계속 이어붙여 준다 -> 이미 넘긴 글자 수를 기억하고 늘어난 만큼만
//   - 한 마디 받으면 세션을 끊어 빈 종이에서 다시 시작한다 (누적 위에서 골라내면 어긋난다)
//   - 확정을 한참 뒤에야 주므로, 말이 멎으면 그 자리에서 확정으로 본다
//   - 안내 음성이 나가는 동안은 자기 목소리를 되먹지 않게 막는다

import { extractSequence } from '../../src/plate.js?v=202610030013';

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

// 더 이어질 수 없는 말(번호를 다 불렀거나 명령어로 끝)은 이만큼만 기다린다
const FAST_MS = 150;

export const isSupported = () => Boolean(SR);

const strip = (t) => t.replace(/[\s,.\-·]/g, '');

/**
 * 더 이어질 수 없는 말인가.
 * "천칠백" 은 "천칠백이십사" 가 될 수 있지만 "천칠백이십사" 는 끝이다.
 * 번호가 끝에 오고 그것이 완성형이면 기다릴 이유가 없다.
 * (순수 함수라 테스트 페이지에서 그대로 검사한다)
 */
export function closedUtterance(text) {
  const tokens = extractSequence(text);
  const last = tokens[tokens.length - 1];
  if (!last) return false;
  if (!strip(text).endsWith(last.raw)) return false;      // 번호 뒤에 말이 더 붙었다
  if (last.type === 'plate') return last.complete === true;
  return true;                                            // 명령어는 그 자체로 끝
}

export function createListener({ onUtterance, onInterim, onStatus, settleMs = 700 }) {
  let rec = null;
  let wanted = false;       // 사용자가 켜 둔 상태인가
  let running = false;      // 실제 엔진이 도는 중인가
  let settled = '';         // 사파리가 확정해 준 말
  let pending = '';         // 아직 말하는 중인 부분
  let consumed = 0;         // 이 세션에서 이미 넘긴 글자 수
  let restartTimer = null;
  let settleTimer = null;
  let muteUntil = 0;

  const status = (state, detail) => onStatus && onStatus(state, detail);

  /** 한 마디 받았으면 세션을 끊어 빈 종이에서 다시 시작한다 */
  function recycle() {
    if (!wanted || !running || !rec) return;
    try { rec.abort(); } catch (_) { /* onend 가 다시 켠다 */ }
  }

  /** 늘어난 만큼을 한 마디로 넘긴다 */
  function take(andRecycle) {
    const whole = settled + pending;
    if (whole.length <= consumed) return;
    const fresh = whole.slice(consumed).trim();
    consumed = whole.length;
    if (!fresh) return;
    if (Date.now() < muteUntil) return;      // 안내 음성 되먹임
    onUtterance && onUtterance(fresh);
    if (andRecycle) recycle();
  }

  function build() {
    const r = new SR();
    r.lang = 'ko-KR';
    r.continuous = true;        // 사파리는 무시하지만 다른 브라우저에선 유효
    r.interimResults = true;
    r.maxAlternatives = 1;

    r.onstart = () => {
      running = true;
      settled = ''; pending = ''; consumed = 0;
      status('listening');
    };

    r.onresult = (e) => {
      if (!running) return;     // 끊은 뒤 뒤늦게 온 결과는 버린다

      let finalText = '';
      let interimText = '';
      for (let i = 0; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalText += t;
        else interimText += t;
      }
      settled = finalText;
      pending = interimText;

      const whole = settled + pending;
      if (whole.length > consumed && Date.now() >= muteUntil) {
        onInterim && onInterim(whole.slice(consumed).trim());
      }

      clearTimeout(settleTimer);
      settleTimer = null;
      if (whole.length > consumed) {
        settleTimer = setTimeout(() => { settleTimer = null; take(true); },
          closedUtterance(whole) ? FAST_MS : settleMs);
      }
    };

    r.onerror = (e) => {
      if (e.error === 'no-speech' || e.error === 'aborted') return;   // 흔한 일, 그냥 재시작
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        wanted = false;
        status('denied');
        return;
      }
      if (e.error === 'network') { status('network'); return; }
      status('error', e.error);
    };

    r.onend = () => {
      running = false;
      clearTimeout(settleTimer);
      settleTimer = null;
      // 확정을 안 준 채 세션이 끝나는 경우가 있다 — 남은 말을 살린다.
      // 이미 끊긴 뒤라 recycle 은 하지 않는다.
      take(false);
      settled = ''; pending = ''; consumed = 0;
      if (wanted) {
        clearTimeout(restartTimer);
        restartTimer = setTimeout(safeStart, 30);
      } else {
        status('idle');
      }
    };

    return r;
  }

  function safeStart() {
    if (!wanted || running) return;
    if (!rec) rec = build();
    try {
      rec.start();
    } catch (err) {
      // 아직 완전히 끝나지 않은 상태에서 start 하면 InvalidStateError
      clearTimeout(restartTimer);
      restartTimer = setTimeout(safeStart, 60);
    }
  }

  return {
    start() {
      if (!SR) { status('unsupported'); return; }
      wanted = true;
      status('starting');
      safeStart();
    },
    stop() {
      wanted = false;
      clearTimeout(restartTimer);
      clearTimeout(settleTimer);
      settleTimer = null;
      if (rec && running) { try { rec.abort(); } catch (_) {} }
      running = false;
      status('idle');
    },
    isOn: () => wanted,
    /** 말이 멎고 몇 ms 뒤에 확정할지 */
    setSettle(ms) { settleMs = ms; },
    /** 안내 음성이 나가는 동안 인식 결과를 무시한다 */
    muteFor(ms) { muteUntil = Date.now() + ms; },
    /** 지금까지의 전사를 잊고 새로 듣는다 */
    reset() {
      settled = ''; pending = ''; consumed = 0;
      clearTimeout(settleTimer);
      settleTimer = null;
      if (rec && running) { try { rec.abort(); } catch (_) {} }
    },
  };
}
