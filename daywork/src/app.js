// 화면 조립 — 말 한 마디를 카드로 바꿔 쌓고, PC 로 보낸다.
//
// 흐름은 두 칸뿐이다.
//   [번호 대기]  "천백이십"      -> 번호를 크게 띄우고 [내용 대기] 로
//   [내용 대기]  "대차"          -> 2초쯤 말이 없으면 카드로 쌓고 다시 [번호 대기]
//
// 내용을 받을 때 오래 기다린다. 고장 증상은 "브레이크에서 소리가 난다" 처럼 중간에
// 숨을 쉬는 말이라 짧게 끊으면 뒷말이 다음 차의 번호 자리로 흘러간다.
// 다 말했으면 [확인] 을 눌러 기다리지 않고 넣는다.

import {
  createState, handleUtterance, setPlate, removeCard, undo, sendable, barePlate,
} from './entry.js?v=202610090226';
import { createListener, isSupported } from './listen.js?v=202610090226';
import { loadSession, saveSession, clearSession, listDays, getToken, setToken, tokenSource } from './store.js?v=202610090226';
import { workDate } from './workdate.js?v=202610090226';
import { send as sendToPc } from './sync.js?v=202610090226';
import { BUILD, checkForUpdate, forceUpdate } from './update.js?v=202610090226';
import * as logbook from './log.js?v=202610090226';
import * as roster from './roster.js?v=202610090226';
import { beep, primeAudio } from '../../src/voice.js?v=202610090226';

// 내용을 받을 때 말이 멎고 이만큼 기다린다.
// 길수록 중간에 쉬어도 한 줄로 들어오지만 그만큼 굼뜨다. 뒷말이 따로 들어와도
// 방금 그 차에 이어 붙이므로(entry.js) 짧게 잡아도 잃지 않는다.
const SYMPTOM_WAIT = 1100;
// 번호를 받을 때. 다 부른 번호는 listen.js 가 더 빨리(0.15초) 넘긴다.
// 짧으면 "천백… 이십" 처럼 끊어 부를 때 앞 토막이 확정돼 버려진다 —
// 빨리 말해야만 들어가는 꼴이 된다. 천천히 불러도 되도록 넉넉히 둔다.
const PLATE_WAIT = 900;

const $ = (id) => document.getElementById(id);
const esc = (t) => String(t == null ? '' : t).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

const state = (() => {
  const saved = loadSession(workDate());
  return Object.assign(createState(saved.date), { cards: saved.cards });
})();

let padDigits = '';
const heardLog = [];          // 진단에서 보여 줄 "최근에 들린 말"

// ── 기록 남기기 ────────────────────────────────────────
function record(kind, extra) {
  logbook.append(state.date, { kind, ...extra });
}

/** 상태기계가 돌려준 일을 기록으로 옮긴다 */
function recordEvent(ev, heard) {
  if (ev.parked && ev.parked.card) {
    record('add', { plate: ev.parked.card.plate, to: '', heard });
  }
  if (ev.type === 'card') {
    if (ev.updated) record('update', { plate: ev.card.plate, from: ev.before, to: ev.card.symptom, heard });
    else record('add', { plate: ev.card.plate, to: ev.card.symptom, heard });
  } else if (ev.type === 'skip' && ev.plate) {
    record('skip', { plate: ev.plate, heard });
  } else if (ev.type === 'undo' && ev.plate) {
    record('undo', { plate: ev.plate, from: ev.card ? ev.card.symptom : '', heard });
  }
}

// ── 그리기 ─────────────────────────────────────────────
function drawStage() {
  const p = state.pending;
  $('stage').classList.toggle('symptom', Boolean(p));
  $('plate').classList.toggle('idle', !p);
  $('plate').classList.toggle('unknown', Boolean(p && !p.known));
  $('plate').textContent = p ? p.plate : '번호 대기';
  $('hint').textContent = p
    ? (p.known ? '특이사항을 말하세요 — 다 말했으면 [확인]' : '명부에 없는 번호입니다 — 그대로 적을 수 있습니다')
    : '차량번호를 "천백이십" 처럼 불러 주세요';
  // 번호를 기다릴 때도 쓸 수 있다 — 1.5초를 기다리지 않고 지금 넣는다
  $('btnConfirm').disabled = !p && !listener.isOn();
  $('btnSkip').disabled = !p;
}

function drawCards() {
  $('count').textContent = String(state.cards.length);
  const ul = $('cards');
  ul.innerHTML = '';
  if (!state.cards.length) {
    const d = document.createElement('div');
    d.id = 'empty';
    d.textContent = '아직 받은 것이 없습니다';
    ul.appendChild(d);
    return;
  }
  for (const card of [...state.cards].reverse()) {     // 방금 넣은 것이 위로
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
      const gone = removeCard(state, card.plate);
      if (gone) record('delete', { plate: gone.plate, from: gone.symptom });
      saveSession(state);
      draw();
      beep('back');
    });
    ul.appendChild(li);
  }
}

function draw() {
  drawStage();
  drawCards();
}

/** 번호를 기다릴 때와 내용을 기다릴 때의 참을성이 다르다 */
function tuneWait() {
  listener.setSettle(state.pending ? SYMPTOM_WAIT : PLATE_WAIT);
}

// ── 들은 것을 반영 ──────────────────────────────────────
function apply(ev, heard) {
  if (ev.type === 'ignored') return false;
  if (ev.parked) beep('warn');                 // 내용 없이 남겨진 차가 생겼다

  const sound = { pending: ev.known ? 'ok' : 'warn', card: 'done', skip: 'vacant', undo: 'back' }[ev.type];
  if (sound) beep(sound);

  recordEvent(ev, heard);
  saveSession(state);
  draw();
  tuneWait();
  return true;
}

function onUtterance(text) {
  heardLog.push(`${new Date().toTimeString().slice(0, 8)}  ${text}`);
  if (heardLog.length > 60) heardLog.shift();
  $('heard').textContent = text;

  const ev = handleUtterance(state, text);
  if (ev.type === 'ignored' && !state.pending) {
    $('hint').textContent = `"${text}" — 번호를 먼저 불러 주세요`;
    return;
  }
  apply(ev, text);
}

// ── 음성 ───────────────────────────────────────────────
/**
 * 아직 다 부르지 않은 번호 같으면 더 기다리라고 알려 준다.
 *
 * 사파리는 "천" 을 숫자 1000 으로 받아 적는다. "천백이십" 을 부르는 동안 전사는
 * 1000 -> 1100 -> 1120 으로 흘러가는데, 1000 도 네 자리라 '다 부른 번호' 로 보여
 * 0.15초 만에 확정돼 버렸다 — "천" 이라고 말하자마자 1000 이 들어간 이유다.
 * 명부를 보면 갈린다: 1000·1100 은 없고 1120 은 있다.
 * 끝내 그 번호면 그대로 받는다 (명부에 없다고 막지는 않는다).
 */
function holdWhile(text) {
  if (state.pending) return false;        // 내용을 받는 중이면 기다릴 일이 아니다
  const plate = barePlate(text);          // 번호 하나만 불렀을 때만 판단한다
  return Boolean(plate) && !roster.isKnown(plate);
}

const listener = createListener({
  onUtterance,
  holdWhile,
  /** 번호가 되다 만 토막은 넣지 않고 버린다 — 무엇을 버렸는지는 보여 준다 */
  onDropped: (text) => {
    heardLog.push(`${new Date().toTimeString().slice(0, 8)}  (버림) ${text}`);
    if (heardLog.length > 60) heardLog.shift();
    $('heard').textContent = `${text} — 번호가 덜 들렸습니다. 다시 불러 주세요`;
  },
  onInterim: (text) => { $('heard').textContent = text; },
  onStatus: (s, detail) => {
    const label = {
      listening: '듣는 중', starting: '켜는 중', idle: '꺼짐',
      denied: '마이크 거부됨', network: '네트워크 없음',
      unsupported: '음성 안 됨', error: `오류 ${detail || ''}`,
    }[s] || s;
    $('status').textContent = label;
    $('status').className = s === 'listening' ? 'on'
      : (s === 'denied' || s === 'unsupported' || s === 'error') ? 'bad'
      : s === 'network' ? 'warn' : '';
    $('mic').classList.toggle('on', listener.isOn());
    $('mic').textContent = listener.isOn() ? '음성 입력 중지' : '음성 입력 시작';
    drawStage();            // [확인] 은 듣는 중일 때 번호 자리에서도 눌려야 한다
  },
  settleMs: PLATE_WAIT,
});

$('mic').addEventListener('click', () => {
  primeAudio();                                // iOS — 제스처 안에서 한 번 깨워야 소리가 난다
  if (listener.isOn()) listener.stop();
  else { listener.start(); tuneWait(); }
});

// ── 조작 버튼 ──────────────────────────────────────────
$('btnConfirm').addEventListener('click', () => {
  primeAudio();
  // 들린 말을 기다리지 않고 지금 넘긴다.
  // 번호는 "천백이십" 처럼 단위로 끝나면 더 이어질 수 있어 1.5초를 기다리는데,
  // 다 불렀으면 이 버튼으로 건너뛴다. 내용도 마찬가지(2초).
  const before = `${state.cards.length}|${state.pending ? state.pending.plate : ''}`;
  listener.flushNow();
  if (before === `${state.cards.length}|${state.pending ? state.pending.plate : ''}`) {
    $('hint').textContent = state.pending
      ? '특이사항을 말한 다음 눌러 주세요' : '번호를 말한 다음 눌러 주세요';
    beep('error');
  }
});

$('btnSkip').addEventListener('click', () => {
  primeAudio();
  if (!state.pending) return;
  const plate = state.pending.plate;
  state.pending = null;
  state.phase = 'plate';
  record('skip', { plate });
  beep('vacant');
  saveSession(state);
  draw();
  tuneWait();
});

$('btnBack').addEventListener('click', () => {
  primeAudio();
  apply(undo(state));
});

// ── 키패드 (앞자리 1은 고정, 뒤 세 자리만) ──────────────
function drawPad() { $('padEcho').textContent = `1${padDigits.padEnd(3, '·')}`; }

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
  $('padKeys').appendChild(b);
}
for (const [label, k] of [['지우기', 'back'], ['닫기', 'close']]) {
  const b = document.createElement('button');
  b.textContent = label;
  b.addEventListener('pointerdown', (e) => { e.preventDefault(); padPress(k); });
  $('padKeys').appendChild(b);
}

function togglePad(on) {
  $('pad').hidden = on === undefined ? !$('pad').hidden : !on;
  padDigits = '';
  drawPad();
  $('btnPad').textContent = $('pad').hidden ? '키패드' : '닫기';
}
$('btnPad').addEventListener('click', () => togglePad());

// ── PC 로 보내기 ───────────────────────────────────────
function note(text, kind) {
  $('sendNote').textContent = text;
  $('sendNote').className = kind || '';
}

$('btnSend').addEventListener('click', async () => {
  const ready = sendable(state);
  if (!ready.length) { note('보낼 것이 없습니다', 'warn'); return; }
  if (!getToken()) { note('토큰이 없습니다 — [진단]에서 한 번만 넣어 주세요', 'bad'); return; }

  $('btnSend').disabled = true;
  note('보내는 중…');
  try {
    const n = await sendToPc(state);
    record('send', { count: n });
    note(`${n}건 보냄 · ${new Date().toTimeString().slice(0, 5)} — PC가 받아 적습니다`, 'ok');
    beep('done');
  } catch (err) {
    note(`보내지 못했습니다 — ${err.message || err}`, 'bad');
    beep('error');
  } finally {
    $('btnSend').disabled = false;
  }
});

$('btnClear').addEventListener('click', () => {
  if (!state.cards.length) return;
  if (!confirm(`오늘 받은 ${state.cards.length}건을 모두 지울까요?\n(기록에는 남습니다)`)) return;
  record('clear', { count: state.cards.length });
  clearSession(state);
  draw();
  note('');
  beep('error');
});

// ── 기록 ───────────────────────────────────────────────
function openLog(date = state.date) {
  const days = new Set([...logbook.days(), ...listDays().map((d) => d.date), state.date]);
  const sorted = [...days].sort().reverse();

  $('logDays').innerHTML = '';
  for (const d of sorted) {
    const b = document.createElement('button');
    b.className = 'day' + (d === date ? ' on' : '');
    b.textContent = d === state.date ? `${d} (오늘)` : d;
    b.addEventListener('click', () => openLog(d));
    $('logDays').appendChild(b);
  }

  const rows = logbook.read(date);
  const saved = date === state.date ? state : loadSession(date);
  const parts = [`<h3>${date} — 받은 것 ${saved.cards.length}건</h3>`];
  parts.push(saved.cards.length
    ? `<ul class="plain">${saved.cards.map((c) =>
        `<li><b>${esc(c.plate)}</b> ${esc(c.symptom) || '—'}</li>`).join('')}</ul>`
    : '<p class="muted">없음</p>');
  parts.push(`<h3>변경 기록 ${rows.length}줄</h3>`);
  parts.push(rows.length
    ? `<ul class="plain">${[...rows].reverse().map((r) =>
        `<li>${esc(logbook.describe(r))}</li>`).join('')}</ul>`
    : '<p class="muted">없음</p>');
  $('logRows').innerHTML = parts.join('');

  $('logSheet').hidden = false;
}

$('btnLog').addEventListener('click', () => openLog());
$('logClose').addEventListener('click', () => { $('logSheet').hidden = true; });

// ── 진단 ───────────────────────────────────────────────
function openDiag() {
  const rows = [
    ['버전', BUILD],
    ['근무일', state.date],
    ['받은 것', `${state.cards.length}건 (보낼 것 ${sendable(state).length}건)`],
    ['명부', `${roster.size}대`],
    ['PC 전송 토큰', getToken() ? `있음 (${tokenSource()})` : '없음 — 아래에서 한 번만 넣으면 됩니다'],
    ['음성', isSupported() ? '쓸 수 있음' : '이 브라우저는 안 됨'],
  ];
  $('diagInfo').innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
  $('diagHeard').innerHTML = heardLog.length
    ? [...heardLog].reverse().map((l) => `<li>${esc(l)}</li>`).join('')
    : '<li class="muted">아직 들린 말이 없습니다</li>';
  $('diagSheet').hidden = false;
}

$('btnToken').addEventListener('click', () => {
  // iOS 는 홈화면 웹앱마다 저장 공간을 따로 주므로 순회앱 토큰이 안 보일 수 있다.
  // 그래서 이 앱에서도 한 번 넣을 수 있어야 한다. 한 번 넣으면 계속 쓴다.
  const t = prompt('GitHub 토큰을 붙여 넣으세요 (PC로 보내기에 씁니다)', getToken());
  if (t === null) return;
  setToken(t);
  openDiag();
  note(getToken() ? '토큰을 넣었습니다' : '토큰을 지웠습니다', getToken() ? 'ok' : 'warn');
});

$('btnDiag').addEventListener('click', openDiag);
$('diagClose').addEventListener('click', () => { $('diagSheet').hidden = true; });
$('diagUpdate').addEventListener('click', async () => {
  $('diagUpdate').textContent = '받는 중…';
  $('diagUpdate').disabled = true;
  await forceUpdate();
});

// 시트 바깥을 누르면 닫힌다
for (const id of ['logSheet', 'diagSheet']) {
  $(id).addEventListener('click', (e) => { if (e.target === $(id)) $(id).hidden = true; });
}

// ── 시작 ───────────────────────────────────────────────
$('date').textContent = state.date;
if (!isSupported()) {
  $('mic').disabled = true;
  $('mic').textContent = '이 브라우저는 음성 입력이 안 됩니다';
  togglePad(true);
}
drawPad();
draw();
logbook.prune(state.date);

// 화면을 벗어날 때 기다리던 번호를 잃지 않게 저장해 둔다
window.addEventListener('pagehide', () => saveSession(state));

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js').catch(() => {});
}

// 켤 때마다 새 버전이 올라왔는지 본다. 올라왔으면 한 번은 알아서 받는다.
checkForUpdate().then((r) => {
  if (r === 'stuck') note('새 버전이 있습니다 — [진단]에서 "최신 버전 받기"', 'warn');
});
