// iOS 사파리 음성 인식 래퍼
//
// 사파리는 continuous 를 사실상 무시하고 발화가 끝나면 인식을 종료한다.
// 그래서 onend 마다 다시 start 를 걸어 연속 인식을 흉내낸다.
// 또 한 세션의 전사(transcript)를 누적해서 돌려주므로, 이미 처리한 토큰 개수를
// 기억해 두고 새로 늘어난 것만 앱에 넘긴다.

import { extractSequence } from './plate.js';

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

export const isSupported = () => Boolean(SR);

export function createVoice({ onToken, onInterim, onStatus }) {
  let rec = null;
  let wanted = false;      // 사용자가 켜 둔 상태인가
  let running = false;     // 실제 엔진이 도는 중인가
  let consumed = 0;        // 현재 세션에서 이미 앱에 넘긴 토큰 개수
  let settled = '';        // 사파리가 확정해 준 말
  let pending = '';        // 아직 말하는 중인 부분
  let restartTimer = null;
  let muteUntil = 0;       // 안내 음성 재생 중 자기 목소리 되먹임 차단

  const status = (state, detail) => onStatus && onStatus(state, detail);

  /**
   * 확정된 말에서만 입력을 만든다.
   *
   * "천칠백이십사" 를 말하면 사파리는 "천" → "천칠백" → "천칠백이십사" 순으로
   * 중간 결과를 흘린다. 이걸 그대로 받으면 첫 조각 "천"이 1000으로 확정돼
   * 다음 자리로 넘어가 버리고, 완성된 값은 들어갈 자리를 잃는다.
   * 그래서 확정(isFinal) 된 부분만 입력으로 옮긴다.
   */
  function commitFinal(finalText) {
    const tokens = extractSequence(finalText);
    if (tokens.length <= consumed) return;

    const fresh = tokens.slice(consumed);
    // 차단 구간이라도 소비 처리는 해야 한다. 그러지 않으면 차단이 풀리는 순간
    // 안내 음성이 남긴 전사가 뒤늦게 한꺼번에 입력돼 버린다.
    consumed = tokens.length;
    if (Date.now() >= muteUntil) {
      for (const t of fresh) onToken && onToken(t);
    }
  }

  function build() {
    const r = new SR();
    r.lang = 'ko-KR';
    r.continuous = true;      // 사파리는 무시하지만 다른 브라우저에선 유효
    r.interimResults = true;
    r.maxAlternatives = 1;

    r.onstart = () => {
      running = true; consumed = 0; settled = ''; pending = '';
      status('listening');
    };

    r.onresult = (e) => {
      // 사파리는 세션 시작부터의 전사를 누적해서 준다.
      // 확정된 부분과 아직 말하는 중인 부분을 나눠서 받는다.
      let finalText = '';
      let interimText = '';
      for (let i = 0; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalText += t;
        else interimText += t;
      }
      settled = finalText;
      pending = interimText;
      commitFinal(settled);
      if (Date.now() >= muteUntil && interimText) {
        onInterim && onInterim(settled + pending, false);
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
      // 사파리가 확정을 안 준 채 세션을 끝내는 경우가 있다. 말은 이미 끝났으니
      // 남아 있던 말을 확정으로 보고 넘긴다 — 안 그러면 한 자리를 통째로 잃는다.
      if (pending) commitFinal(settled + pending);
      consumed = 0; settled = ''; pending = '';
      if (wanted) {
        clearTimeout(restartTimer);
        restartTimer = setTimeout(safeStart, 120);
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
      // 아직 완전히 종료되지 않은 상태에서 start 하면 InvalidStateError
      clearTimeout(restartTimer);
      restartTimer = setTimeout(safeStart, 250);
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
      if (rec && running) { try { rec.abort(); } catch (_) {} }
      running = false;
      status('idle');
    },
    isOn: () => wanted,
    /** 안내 음성이 나가는 동안 인식 결과를 무시한다 (에어팟 되먹임 방지) */
    muteFor(ms) { muteUntil = Date.now() + ms; },
    /** 자리를 옮겼으니 지금까지의 전사는 잊고 새로 듣는다 */
    reset() {
      consumed = 0; settled = ''; pending = '';
      if (rec && running) { try { rec.abort(); } catch (_) {} }
    },
  };
}

// ---- 소리 피드백 -------------------------------------------------------

let audioCtx = null;

function ctx() {
  if (!audioCtx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) audioCtx = new AC();
  }
  if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume();
  return audioCtx;
}

/** 사용자 제스처 안에서 한 번 불러 오디오를 깨워둔다 (iOS 필수) */
export function primeAudio() { ctx(); }

export function beep(kind) {
  const c = ctx();
  if (!c) return;
  const tones = {
    ok:      [[880, 0.06]],
    warn:    [[520, 0.09], [430, 0.11]],
    error:   [[300, 0.16]],
    back:    [[660, 0.06], [520, 0.08]],
    done:    [[880, 0.08], [1170, 0.14]],
  }[kind] || [[880, 0.06]];

  let t = c.currentTime;
  for (const [freq, dur] of tones) {
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = 'sine';
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.25, t + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(gain).connect(c.destination);
    osc.start(t);
    osc.stop(t + dur + 0.02);
    t += dur;
  }
}

/** 안내 음성. 말하는 동안 인식을 잠시 막으려면 voice.muteFor 를 함께 쓴다. */
export function speak(text, { rate = 1.25 } = {}) {
  if (!window.speechSynthesis) return 0;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'ko-KR';
  u.rate = rate;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
  // 대략적인 재생 시간(ms) — 되먹임 차단 구간 계산용
  return Math.max(600, (text.length / rate) * 130);
}
