// 화면 조립 — 말 한 마디를 카드로 바꿔 쌓는다.
//
// 흐름은 두 칸뿐이다.
//   [번호 대기]  "천백이십"      -> 번호를 크게 띄우고 [내용 대기] 로
//   [내용 대기]  "대차"          -> 카드로 쌓고 다시 [번호 대기]
//
// 손이 비면 어휘 버튼이 더 빠르고 정확하다. 음성이 안 될 때는 키패드.
// 어느 길로 넣어도 들어가는 자리는 같다.

import { createState, handleUtterance, setPlate, setSymptom, removeCard, undo } from './entry.js?v=202610030013';
import { createListener, isSupported } from './listen.js?v=202610030013';
import { loadSession, saveSession, clearSession } from './store.js?v=202610030013';
import { workDate } from './workdate.js?v=202610030013';
import { WORDS } from './words.js?v=202610030013';
import { beep, primeAudio } from '../../src/voice.js?v=202610030013';

const $ = (id) => document.getElementById(id);
const el = {
  date: $('date'), status: $('status'), stage: $('stage'), plate: $('plate'),
  hint: $('hint'), heard: $('heard'), mic: $('mic'), words: $('words'),
  pad: $('pad'), padEcho: $('padEcho'), padKeys: $('padKeys'),
  count: $('count'), cards: $('cards'), padBtn: $('padBtn'), clearBtn: $('clearBtn'),
};

// 저장된 판을 이어받되, 상태기계가 쓰는 모양으로 맞춘다
const saved = loadSession(workDate());
const state = Object.assign(createState(saved.date), { cards: saved.cards });

let padDigits = '';

// ── 그리기 ─────────────────────────────────────────────
function drawStage() {
  const p = state.pending;
  el.stage.classList.toggle('symptom', Boolean(p));
  el.plate.classList.toggle('idle', !p);
  el.plate.classList.toggle('unknown', Boolean(p && !p.known));
  el.plate.textContent = p ? p.plate : '번호 대기';
  el.hint.textContent = p
    ? (p.known ? '특이사항을 말하거나 아래에서 고르세요' : '명부에 없는 번호입니다 — 그대로 적을 수 있습니다')
    : '차량번호를 "천백이십" 처럼 불러 주세요';
  el.words.classList.toggle('off', !p);
}

function drawCards() {
  el.count.textContent = String(state.cards.length);
  el.cards.innerHTML = '';
  if (!state.cards.length) {
    const d = document.createElement('div');
    d.id = 'empty';
    d.textContent = '아직 받은 것이 없습니다';
    el.cards.appendChild(d);
    return;
  }
  // 방금 넣은 것이 위로
  for (const card of [...state.cards].reverse()) {
    const li = document.createElement('li');
    if (card.status !== 'ok') li.className = card.status;
    const no = document.createElement('span');
    no.className = 'no';
    no.textContent = card.plate;
    const what = document.createElement('span');
    what.className = 'what';
    what.textContent = card.symptom || '—';
    li.append(no, what);
    if (card.status !== 'ok') {
      const badge = document.createElement('span');
      badge.className = 'badge';
      badge.textContent = card.status === 'unknown' ? '명부에 없음' : '내용 없음';
      li.appendChild(badge);
    }
    li.addEventListener('click', () => {
      if (!confirm(`${card.plate} ${card.symptom || ''} — 지울까요?`)) return;
      removeCard(state, card.plate);
      saveSession(state);
      draw();
      beep('back');
    });
    el.cards.appendChild(li);
  }
}

function draw() {
  drawStage();
  drawCards();
}

// ── 들은 것을 반영 ──────────────────────────────────────
function apply(ev) {
  if (ev.parked) beep('warn');              // 내용 없이 남겨진 차가 생겼다

  switch (ev.type) {
    case 'pending':
      beep(ev.known ? 'ok' : 'warn');
      break;
    case 'card':
      beep('done');
      break;
    case 'skip':
      beep('vacant');
      break;
    case 'undo':
      beep('back');
      break;
    default:
      return;                               // 'ignored' — 아무 일도 하지 않는다
  }
  saveSession(state);
  draw();
}

function onUtterance(text) {
  el.heard.textContent = text;
  const ev = handleUtterance(state, text);
  if (ev.type === 'ignored' && !state.pending) {
    el.hint.textContent = `"${text}" — 번호를 먼저 불러 주세요`;
    return;
  }
  apply(ev);
}

// ── 음성 ───────────────────────────────────────────────
const listener = createListener({
  onUtterance,
  onInterim: (text) => { el.heard.textContent = text; },
  onStatus: (s, detail) => {
    const label = {
      listening: '듣는 중', starting: '켜는 중', idle: '꺼짐',
      denied: '마이크 거부됨', network: '네트워크 없음',
      unsupported: '이 브라우저는 음성 안 됨', error: `오류 ${detail || ''}`,
    }[s] || s;
    el.status.textContent = label;
    el.status.className = s === 'listening' ? 'on'
      : (s === 'denied' || s === 'unsupported' || s === 'error') ? 'bad'
      : s === 'network' ? 'warn' : '';
    el.mic.classList.toggle('on', listener.isOn());
    el.mic.textContent = listener.isOn() ? '음성 입력 중지' : '음성 입력 시작';
  },
});

el.mic.addEventListener('click', () => {
  primeAudio();                              // iOS — 제스처 안에서 한 번 깨워야 소리가 난다
  if (listener.isOn()) listener.stop();
  else listener.start();
});

// ── 어휘 버튼 ──────────────────────────────────────────
// 스물일곱 가지를 다 펴면 열네 줄이 되어 받은 목록이 화면 밖으로 밀린다.
// 실제로 쓰이는 것은 대차·세차에 크게 쏠려 있으므로 자주 쓰는 것만 펴 두고
// 나머지는 접어 둔다 (PC 프로그램의 버튼 배열과 같은 순서).
const OPEN_COUNT = 8;
let wordsOpen = false;

function drawWords() {
  el.words.innerHTML = '';
  const shown = wordsOpen ? WORDS : WORDS.slice(0, OPEN_COUNT);
  for (const w of shown) {
    const b = document.createElement('button');
    b.textContent = w.text;
    b.addEventListener('click', () => {
      primeAudio();
      if (!state.pending) {
        el.hint.textContent = '번호를 먼저 불러 주세요';
        beep('error');
        return;
      }
      apply(setSymptom(state, w.text));
    });
    el.words.appendChild(b);
  }
  if (WORDS.length > OPEN_COUNT) {
    const more = document.createElement('button');
    more.id = 'moreWords';
    more.textContent = wordsOpen ? '접기' : `더 보기 (${WORDS.length - OPEN_COUNT})`;
    more.addEventListener('click', () => { wordsOpen = !wordsOpen; drawWords(); });
    el.words.appendChild(more);
  }
}
drawWords();

// ── 키패드 (앞자리 1은 고정, 뒤 세 자리만) ──────────────
function drawPad() {
  el.padEcho.textContent = `1${padDigits.padEnd(3, '·')}`;
}

function padPress(k) {
  primeAudio();
  if (k === 'back') {
    if (padDigits) padDigits = padDigits.slice(0, -1);
    else apply(undo(state));
    beep('back');
    drawPad();
    return;
  }
  if (k === 'close') { togglePad(false); return; }
  if (padDigits.length >= 3) return;
  padDigits += k;
  beep('ok');
  drawPad();
  if (padDigits.length === 3) {
    apply(setPlate(state, `1${padDigits}`));
    padDigits = '';
    drawPad();
  }
}

for (const k of ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']) {
  const b = document.createElement('button');
  b.textContent = k;
  b.addEventListener('pointerdown', (e) => { e.preventDefault(); padPress(k); });
  el.padKeys.appendChild(b);
}
for (const [label, k, wide] of [['지우기', 'back', false], ['닫기', 'close', false]]) {
  const b = document.createElement('button');
  b.textContent = label;
  if (wide) b.className = 'wide';
  b.addEventListener('pointerdown', (e) => { e.preventDefault(); padPress(k); });
  el.padKeys.appendChild(b);
}

function togglePad(on) {
  el.pad.hidden = on === undefined ? !el.pad.hidden : !on;
  padDigits = '';
  drawPad();
  el.padBtn.textContent = el.pad.hidden ? '키패드' : '키패드 닫기';
}
el.padBtn.addEventListener('click', () => togglePad());

// ── 오늘 지우기 ────────────────────────────────────────
el.clearBtn.addEventListener('click', () => {
  if (!state.cards.length) return;
  if (!confirm(`오늘 받은 ${state.cards.length}건을 모두 지울까요?`)) return;
  clearSession(state);
  draw();
  beep('error');
});

// ── 시작 ───────────────────────────────────────────────
el.date.textContent = `근무일 ${state.date}`;
if (!isSupported()) {
  el.mic.disabled = true;
  el.mic.textContent = '이 브라우저는 음성 입력이 안 됩니다';
  el.status.textContent = '음성 불가';
  el.status.className = 'bad';
  togglePad(true);
}
drawPad();
draw();

// 화면을 벗어날 때 기다리던 번호를 잃지 않게 저장해 둔다
window.addEventListener('pagehide', () => saveSession(state));

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js').catch(() => {});
}
