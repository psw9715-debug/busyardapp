// iOS 사파리 음성 인식 래퍼
//
// 사파리는 continuous 를 사실상 무시하고 발화가 끝나면 인식을 종료한다.
// 그래서 onend 마다 다시 start 를 걸어 연속 인식을 흉내낸다.
// 또 한 세션의 전사(transcript)를 누적해서 돌려주므로, 이미 처리한 토큰 개수를
// 기억해 두고 새로 늘어난 것만 앱에 넘긴다.

import { extractSequence } from './plate.js?v=202609022156';

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

// 다 부른 번호는 이만큼만 기다렸다 넘긴다 (더 이어질 수 없으므로)
const FAST_MS = 120;

export const isSupported = () => Boolean(SR);

export function createVoice({ onToken, onInterim, onStatus, settleMs = 450 }) {
  let rec = null;
  let wanted = false;      // 사용자가 켜 둔 상태인가
  let running = false;     // 실제 엔진이 도는 중인가
  let consumed = 0;        // 현재 세션에서 이미 앱에 넘긴 토큰 개수
  let settled = '';        // 사파리가 확정해 준 말
  let pending = '';        // 아직 말하는 중인 부분
  let restartTimer = null;
  let settleTimer = null;  // 말이 멈춘 뒤 스스로 확정하기까지
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
    if (tokens.length <= consumed) return false;

    const fresh = tokens.slice(consumed);
    // 차단 구간이라도 소비 처리는 해야 한다. 그러지 않으면 차단이 풀리는 순간
    // 안내 음성이 남긴 전사가 뒤늦게 한꺼번에 입력돼 버린다.
    consumed = tokens.length;
    if (Date.now() >= muteUntil) {
      for (const t of fresh) onToken && onToken(t);
    }
    return true;
  }

  /**
   * 한 대를 넣고 나면 인식을 끊었다 다시 켠다.
   *
   * 사파리는 한 세션에서 들은 말을 계속 이어붙여 주는데, 그 위에서 "이번에
   * 새로 늘어난 부분"을 골라내는 방식은 말이 길어질수록 어긋나기 쉽다.
   * 자리마다 새 세션으로 시작하면 늘 빈 종이에서 출발하므로 훨씬 확실하다.
   * (사용자가 손으로 껐다 켜면 잘 되던 것과 같은 상태를 만든다.)
   *
   * 확정 직후는 이미 말이 멎은 뒤라, 끊는다고 말을 자를 일은 없다.
   */
  function recycle() {
    if (!wanted || !running || !rec) return;
    try { rec.abort(); } catch (_) { /* onend 가 알아서 다시 켠다 */ }
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
      // 끊은 뒤에 뒤늦게 도착한 결과는 버린다. 안 그러면 방금 넣은 번호가
      // 새 세션의 빈 상태에서 한 번 더 들어간다.
      if (!running) return;

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

      clearTimeout(settleTimer);
      commitFinal(settled);

      if (pending) {
        if (Date.now() >= muteUntil) onInterim && onInterim(settled + pending, false);

        // 사파리는 말이 끝나고도 한참 뒤에야 확정을 준다. 그때까지 기다리면
        // 자리마다 눈에 띄게 굼뜨다. 말이 멎으면 그 자리에서 확정으로 본다.
        //
        // 다 부른 번호("천칠백이십사")는 더 이어질 수 없으니 거의 바로 넘긴다.
        // 아직 이어질 수 있는 것("천칠백")만 제 시간을 기다린다.
        const tokens = extractSequence(settled + pending);
        const last = tokens[tokens.length - 1];
        const done = tokens.length > consumed && last
          && (last.type !== 'plate' || last.complete);

        settleTimer = setTimeout(() => {
          if (commitFinal(settled + pending)) recycle();
        }, done ? Math.min(settleMs, FAST_MS) : settleMs);
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
      // 사파리가 확정을 안 준 채 세션을 끝내는 경우가 있다. 말은 이미 끝났으니
      // 남아 있던 말을 확정으로 보고 넘긴다 — 안 그러면 한 자리를 통째로 잃는다.
      if (pending) commitFinal(settled + pending);
      consumed = 0; settled = ''; pending = '';
      if (wanted) {
        clearTimeout(restartTimer);
        restartTimer = setTimeout(safeStart, 60);
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
      clearTimeout(settleTimer);
      if (rec && running) { try { rec.abort(); } catch (_) {} }
      running = false;
      status('idle');
    },
    isOn: () => wanted,
    /** 말이 멎고 몇 ms 뒤에 확정할지 — 짧을수록 다음 자리로 빨리 넘어간다 */
    setSettle(ms) { settleMs = ms; },
    /** 안내 음성이 나가는 동안 인식 결과를 무시한다 (에어팟 되먹임 방지) */
    muteFor(ms) { muteUntil = Date.now() + ms; },
    /** 자리를 옮겼으니 지금까지의 전사는 잊고 새로 듣는다 */
    reset() {
      consumed = 0; settled = ''; pending = '';
      clearTimeout(settleTimer);
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
    // 찾던 차량 — 다른 소리와 확실히 구분되게 세 번 튄다
    alert:   [[1320, 0.09], [990, 0.07], [1320, 0.09], [990, 0.07], [1320, 0.14]],
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
export function speak(text, { rate = 1.25, interrupt = true } = {}) {
  if (!window.speechSynthesis) return 0;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'ko-KR';
  u.rate = rate;
  if (interrupt) window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
  // 대략적인 재생 시간(ms) — 되먹임 차단 구간 계산용
  return Math.max(600, (text.length / rate) * 130);
}

const DIGIT_WORD = ['공', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구'];

/**
 * 키패드에서 누른 숫자를 바로 읽어준다.
 * 한 글자짜리라 빠르게 내면 뭉개져 무슨 소리인지 알 수 없다.
 * 잘못 누른 것을 알아채는 게 목적이므로 또렷한 쪽을 택한다.
 */
export function speakDigit(d) {
  const word = DIGIT_WORD[Number(d)];
  if (word === undefined) return;
  speak(word, { rate: 1.0 });
}
