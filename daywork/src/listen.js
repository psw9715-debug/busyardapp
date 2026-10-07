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

import { extractSequence } from '../../src/plate.js?v=202610072212';

// 엔진은 모듈을 읽을 때가 아니라 **쓸 때** 찾는다.
// 그래야 테스트에서 가짜 엔진을 끼워 넣고 전체 흐름을 그대로 돌려볼 수 있다.
const engine = () => window.SpeechRecognition || window.webkitSpeechRecognition;

// 더 이어질 수 없는 말(번호를 다 불렀거나 명령어로 끝)은 이만큼만 기다린다
const FAST_MS = 150;

export const isSupported = () => Boolean(engine());

const strip = (t) => t.replace(/[\s,.\-·]/g, '');

/**
 * 더 이어질 수 없는 말인가.
 * "천칠백" 은 "천칠백이십사" 가 될 수 있지만 "천칠백이십사" 는 끝이다.
 * 번호가 끝에 오고 그것이 완성형이면 기다릴 이유가 없다.
 * (순수 함수라 테스트 페이지에서 그대로 검사한다)
 */
// 숫자로만 이루어진 말인가 (한국식 수사·자리수사·아라비아 숫자)
const NUMERIC_ONLY = /^[0-9영공빵일이삼사오육륙칠팔구천백십]+$/;

/**
 * 아직 번호가 되지 못한 숫자말인가 — "천", "천백", "일이" 처럼 더 이어질 말.
 *
 * 천천히 부르면 음절 사이에 침묵이 생긴다. 그때 반쯤 들린 것을 확정해 버리면
 * 번호가 되지 못한 채 버려지고, 세션이 끊기면서 뒤에 이어 부른 말까지 잃는다.
 * 그래서 이런 말은 확정하지 않고 조금 더 기다린다.
 *
 * 다만 이것만으로는 모자란다. 사파리는 "천" 을 글자가 아니라 숫자 1000 으로
 * 받아 적어서, 전사는 1000 -> 1100 -> 1120 으로 흘러간다. 1000 도 네 자리라
 * 여기서는 '다 부른 번호' 로 보인다. 그 판단은 명부를 아는 쪽(앱)이 해야 하므로
 * createListener 의 holdWhile 로 받는다.
 * (순수 함수라 테스트 페이지에서 그대로 검사한다)
 */
export function unfinishedNumber(text) {
  const bare = strip(text);
  if (!bare || !NUMERIC_ONLY.test(bare)) return false;
  const plate = extractSequence(text).find((t) => t.type === 'plate');
  return !plate || /^[천백십]+$/.test(plate.raw);     // 번호가 없거나, 단위만 불렀다
}

export function closedUtterance(text) {
  const tokens = extractSequence(text);
  const last = tokens[tokens.length - 1];
  if (!last) return false;
  if (!strip(text).endsWith(last.raw)) return false;      // 번호 뒤에 말이 더 붙었다
  if (last.type === 'plate') return last.complete === true;
  return true;                                            // 명령어는 그 자체로 끝
}

// 번호가 아직 덜 불린 것 같을 때 더 기다리는 횟수. 한도를 넘으면 그냥 넘긴다
// (영원히 기다리면 말이 끊긴 줄도 모르고 아무 일도 일어나지 않는다).
const MAX_HOLD = 2;

export function createListener({ onUtterance, onInterim, onStatus, holdWhile, onDropped,
                                settleMs = 700 }) {
  let rec = null;
  let wanted = false;       // 사용자가 켜 둔 상태인가
  let running = false;      // 실제 엔진이 도는 중인가
  let settled = '';         // 사파리가 확정해 준 말
  let pending = '';         // 아직 말하는 중인 부분
  let consumed = 0;         // 이 세션에서 이미 넘긴 글자 수
  let restartTimer = null;
  let settleTimer = null;
  let muteUntil = 0;
  let held = 0;             // 덜 불린 번호를 몇 번 더 기다렸나

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

  /**
   * 말이 멎으면 확정한다. 덜 불린 번호 같으면 한 번 더 기다린다.
   *
   * holding=true 면 짧은 길(0.15초)을 쓰지 않는다. "1000" 은 네 자리라
   * '다 부른 번호' 로 보여 짧은 길로 가는데, 기다리기로 해 놓고 또 0.15초 뒤에
   * 물으면 세 번이 0.45초 만에 소진돼 기다린 보람이 없다.
   */
  function schedule(whole, holding) {
    const wait = (!holding && closedUtterance(whole)) ? FAST_MS : settleMs;
    settleTimer = setTimeout(() => {
      settleTimer = null;
      const now = settled + pending;
      const fresh = now.slice(consumed);
      if (held < MAX_HOLD && (unfinishedNumber(fresh) || (holdWhile && holdWhile(fresh)))) {
        held += 1;
        schedule(now, true);            // "천백" 에서 멈췄다 — 뒤를 넉넉히 기다린다
        return;
      }
      held = 0;
      take(true);
    }, wait);
  }

  function build() {
    const r = new (engine())();
    r.lang = 'ko-KR';
    r.continuous = true;        // 사파리는 무시하지만 다른 브라우저에선 유효
    r.interimResults = true;
    r.maxAlternatives = 1;

    r.onstart = () => {
      running = true;
      settled = ''; pending = ''; consumed = 0; held = 0;
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
        held = 0;                       // 말이 이어졌으니 기다린 횟수를 되돌린다
        schedule(whole);
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
      //
      // 다만 아직 번호가 되지 못한 토막은 넣지 않는다. 사파리는 발화가 끝나면
      // 세션을 끊으므로 번호를 부르다 쉬면 이 길로 들어오는데, 여기서 넣어 버리면
      // "천" 이라고만 했는데 1000 이 들어간다. 세션이 끊긴 뒤라 더 기다릴 수는
      // 없으니 버리고, 무엇을 버렸는지만 남긴다.
      const whole = settled + pending;
      const leftover = whole.slice(consumed).trim();
      if (leftover && (unfinishedNumber(leftover) || (holdWhile && holdWhile(leftover)))) {
        consumed = whole.length;
        if (Date.now() >= muteUntil) onDropped && onDropped(leftover);
      } else {
        take(false);
      }
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
      if (!engine()) { status('unsupported'); return; }
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
    /**
     * 지금까지 들린 말을 기다리지 않고 바로 넘긴다 ([확인] 버튼).
     * 내용을 받을 때는 2초를 기다리므로, 다 말했으면 눌러서 건너뛴다.
     */
    flushNow() {
      clearTimeout(settleTimer);
      settleTimer = null;
      take(true);
    },
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
