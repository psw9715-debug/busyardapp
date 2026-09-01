import { YARD } from './yard-data.js';
import { BUILD } from './build.js';
import { toKoreanSino } from './plate.js';
import { createVoice, isSupported, beep, speak, speakDigit, primeAudio } from './voice.js';
import { loadSession, setEntry, countFilled, workDate, clearSession } from './store.js';

// ---------------------------------------------------------------- 상태

const spots = YARD.cells.filter((c) => c.kind === 'spot').sort((a, b) => a.spot - b.spot);
const TOTAL = spots.length;

let session = loadSession(YARD.id);
let cursor = firstEmptySpot();
let voice = null;
let wakeLock = null;
const heardLog = [];

const $ = (id) => document.getElementById(id);
const cellEls = new Map();   // spot 번호 -> DOM

function firstEmptySpot() {
  for (let n = 1; n <= TOTAL; n++) if (!session.entries[n]) return n;
  return TOTAL;
}

// ---------------------------------------------------------------- 배치도

function buildMap(container, cls) {
  container.innerHTML = '';
  for (const c of YARD.cells) {
    const el = document.createElement('div');
    el.className = 'cell ' + c.kind;
    el.style.gridColumn = `${c.col} / span ${c.colspan}`;
    el.style.gridRow = `${c.row} / span ${c.rowspan}`;

    // 구역 색은 인쇄물에만 입힌다. 화면은 야간 순회용이라 어두운 채로 둔다.
    // 테두리는 원본의 굵기 차이를 따르지 않고 전부 같은 얇은 선으로 긋는다.
    if (cls === 'print' && c.bg) el.style.background = c.bg;

    if (c.kind === 'spot') {
      el.dataset.spot = c.spot;
      // 순회 번호는 화면에서만 쓴다. 인쇄물은 지금 쓰는 종이와 똑같이
      // 번호 없는 빈 칸에 차량번호만 찍혀야 한다 (CSS에서 숨김).
      el.innerHTML = `<span class="no">${c.spot}</span><span class="plate"></span>`;
      if (cls === 'live') {
        el.addEventListener('click', () => openSpotSheet(c.spot));
        cellEls.set(c.spot, el);
      }
    } else if (c.kind === 'label' || c.kind === 'paint') {
      el.textContent = c.text;
      if (c.kind === 'label' && c.rowspan >= 4) el.classList.add('tall');
    }
    container.appendChild(el);
  }
}

function paintSpot(n) {
  const el = cellEls.get(n);
  if (!el) return;
  const e = session.entries[n];
  const plateEl = el.querySelector('.plate');

  el.classList.remove('filled', 'vacant', 'corrected', 'current');
  if (e && e.status === 'vacant') {
    el.classList.add('vacant');
    plateEl.textContent = '공차';
  } else if (e) {
    el.classList.add('filled');
    if (e.confidence === 'corrected' || e.confidence === 'assumed') el.classList.add('corrected');
    plateEl.textContent = e.plate;
  } else {
    plateEl.textContent = '';
  }
  if (n === cursor) el.classList.add('current');
}

function repaintAll() {
  for (let n = 1; n <= TOTAL; n++) paintSpot(n);
}

// ---------------------------------------------------------------- 안내판

function renderHud(flash) {
  $('hudSpot').textContent = cursor;
  const done = countFilled(session);
  $('hudCount').textContent = `${done} / ${TOTAL}`;
  $('progressFill').style.width = `${(done / TOTAL) * 100}%`;

  const plateEl = $('hudPlate');
  plateEl.className = 'hud-plate';

  const e = flash || session.entries[cursor];
  if (flash) {
    if (flash.status === 'vacant') { plateEl.textContent = '공차'; plateEl.classList.add('vacant'); }
    else { plateEl.textContent = flash.plate; if (flash.confidence !== 'high') plateEl.classList.add('corrected'); }
  } else if (e) {
    if (e.status === 'vacant') { plateEl.textContent = '공차'; plateEl.classList.add('vacant'); }
    else { plateEl.textContent = e.plate; if (e.confidence !== 'high') plateEl.classList.add('corrected'); }
  } else {
    plateEl.innerHTML = '<span class="ph">– – – –</span>';
  }
}

function note(text, kind) {
  const el = $('hudNote');
  el.textContent = text;
  el.className = 'hud-note' + (kind ? ' ' + kind : '');
}

// ---------------------------------------------------------------- 입력 반영

function commit(spot, entry, { announce = true } = {}) {
  setEntry(session, spot, entry);
  paintSpot(spot);

  const isLast = spot >= TOTAL;
  cursor = isLast ? TOTAL : spot + 1;
  paintSpot(spot);
  paintSpot(cursor);
  renderHud(entry);

  if (entry.confidence === 'corrected') {
    note(`"${entry.heard}"로 들려서 ${entry.plate}로 맞췄습니다`, 'warn');
    beep('warn');
  } else if (entry.confidence === 'assumed') {
    note(`앞자리 1을 붙여 ${entry.plate}로 넣었습니다`, 'warn');
    beep('warn');
  } else if (entry.status === 'vacant') {
    note('공차 처리');
    beep('back');
  } else {
    note('');
    beep('ok');
  }

  if (isLast && countFilled(session) >= TOTAL) {
    note('109자리 전부 입력 완료', 'warn');
    beep('done');
    if (announce) announceSpeak('순회 완료');
    return;
  }
  if (announce) announceSpeak(`${cursor}번`);
}

function goBack() {
  if (cursor > 1) cursor -= 1;
  setEntry(session, cursor, null);
  repaintAll();
  renderHud();
  note(`${cursor}번 자리로 되돌렸습니다`);
  beep('back');
  if (voice) voice.reset();
  announceSpeak(`${cursor}번 다시`);
}

function markVacant() {
  commit(cursor, { plate: null, status: 'vacant', confidence: 'high', method: 'manual' });
}

/** 안내 음성. 말하는 동안 자기 목소리가 다시 인식되지 않게 막는다. */
function announceSpeak(text) {
  if (!ttsOn) return;
  const ms = speak(text);
  if (voice) voice.muteFor(ms + 250);
}

let ttsOn = localStorage.getItem('busyard:tts') === '1';
// 키패드로 넣은 번호를 한국식으로 되읽어 확인시켜 준다 ("734" -> "천칠백삼십사")
let padTtsOn = localStorage.getItem('busyard:padtts') === '1';
// 키패드에서 누른 숫자를 바로 읽어준다 ("7" -> "칠"). 기본 켜짐.
let keyTtsOn = localStorage.getItem('busyard:keytts') !== '0';

// 말이 멎고 얼마 만에 확정할지. 짧을수록 다음 자리로 빨리 넘어가지만,
// 번호를 중간에 끊어 말하면 두 개로 쪼개질 수 있다.
// 다 부른 번호("천칠백이십사")는 이 값과 무관하게 거의 바로 넘어간다.
const SETTLE = [
  { ms: 200, label: '아주 빠름' },
  { ms: 300, label: '빠름' },
  { ms: 450, label: '보통' },
  { ms: 700, label: '느림' },
];
const savedSettle = Number(localStorage.getItem('busyard:settlems'));
let settleIdx = SETTLE.findIndex((s) => s.ms === savedSettle);
if (settleIdx < 0) settleIdx = 1;   // 기본 빠름

function readBackPlate(plate) {
  if (!padTtsOn || !plate) return;
  const ms = speak(toKoreanSino(plate), { rate: 1.7 });
  if (voice) voice.muteFor(ms + 200);
}

// ---------------------------------------------------------------- 음성

function handleToken(t) {
  if (t.type === 'plate') {
    commit(cursor, {
      plate: t.plate, status: 'filled',
      confidence: t.confidence, heard: t.heard, method: 'voice',
    });
  } else if (t.type === 'skip') {
    commit(cursor, { plate: null, status: 'vacant', confidence: 'high', method: 'voice' });
  } else if (t.type === 'back') {
    goBack();
  }
}

function handleInterim(text) {
  if (!text) return;
  heardLog.unshift(`${new Date().toLocaleTimeString('ko-KR')} · ${text}`);
  heardLog.length = Math.min(heardLog.length, 10);
}

function handleStatus(state, detail) {
  const mic = $('btnMic');
  const label = mic.querySelector('.mic-label');

  if (state === 'listening') {
    mic.classList.add('on'); label.textContent = '듣는 중 — 누르면 멈춤';
    note('');
  } else if (state === 'starting') {
    mic.classList.add('on'); label.textContent = '마이크 준비 중…';
  } else if (state === 'idle') {
    mic.classList.remove('on'); label.textContent = '음성 입력 시작';
  } else if (state === 'denied') {
    mic.classList.remove('on'); label.textContent = '음성 입력 시작';
    note('마이크 권한이 거부됐습니다. 설정 > Safari에서 허용해 주세요.', 'err');
    beep('error');
  } else if (state === 'network') {
    note('전파가 약해 음성 인식이 안 됩니다. 키패드를 쓰세요.', 'err');
  } else if (state === 'unsupported') {
    mic.classList.remove('on');
    note('이 브라우저는 음성 인식을 지원하지 않습니다. 키패드를 쓰세요.', 'err');
  } else if (state === 'error') {
    note(`음성 오류: ${detail}`, 'err');
  }
}

function ensureVoice() {
  if (!voice) {
    voice = createVoice({
      onToken: handleToken,
      onInterim: handleInterim,
      onStatus: handleStatus,
      settleMs: SETTLE[settleIdx].ms,
    });
  }
  return voice;
}

function toggleMic() {
  primeAudio();
  const v = ensureVoice();
  if (v.isOn()) { v.stop(); releaseWakeLock(); }
  else { v.start(); requestWakeLock(); }
}

// ---------------------------------------------------------------- 화면 꺼짐 방지

async function requestWakeLock() {
  try {
    if ('wakeLock' in navigator) wakeLock = await navigator.wakeLock.request('screen');
  } catch (_) { /* 지원 안 하면 그냥 넘어감 */ }
}
function releaseWakeLock() {
  if (wakeLock) { try { wakeLock.release(); } catch (_) {} wakeLock = null; }
}
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && voice && voice.isOn()) requestWakeLock();
});

// ---------------------------------------------------------------- 키패드

let padSpot = null;
let padDigits = '';

function openPad(spot) {
  primeAudio();
  // 키패드를 쓰는 동안 마이크가 켜져 있으면 숫자 읽는 소리까지 받아 적는다.
  // 닫아도 다시 켜지 않는다 — 음성으로 돌아갈 때 직접 누르면 된다.
  if (voice && voice.isOn()) { voice.stop(); releaseWakeLock(); }

  padSpot = spot; padDigits = '';
  $('padTitle').textContent = `${spot}번 자리`;
  renderPad();
  $('padSheet').hidden = false;
}

function closePad() {
  $('padSheet').hidden = true;
}
function renderPad() {
  document.querySelectorAll('#padDisplay .slot').forEach((el, i) => {
    const ch = padDigits[i];
    el.textContent = ch || '_';
    el.classList.toggle('set', Boolean(ch));
  });
}
function padKey(k) {
  primeAudio();
  if (k === 'del') {
    padDigits = padDigits.slice(0, -1);
    renderPad();
    beep('back');
    return;
  }
  if (k === 'vacant') {
    commit(padSpot, { plate: null, status: 'vacant', confidence: 'high', method: 'keypad' }, { announce: false });
    padSpot = cursor; padDigits = '';
    $('padTitle').textContent = `${padSpot}번 자리`;
    renderPad();
    return;
  }
  if (padDigits.length >= 3) return;
  padDigits += k;
  renderPad();
  if (keyTtsOn) speakDigit(k);   // 무엇을 눌렀는지 귀로 확인
  if (padDigits.length === 3) {
    const plate = '1' + padDigits;
    commit(padSpot, { plate, status: 'filled', confidence: 'high', method: 'keypad' }, { announce: false });
    readBackPlate(plate);
    // 이어서 다음 자리를 계속 찍을 수 있게 시트를 열어 둔다
    padSpot = cursor; padDigits = '';
    $('padTitle').textContent = `${padSpot}번 자리`;
    renderPad();
  }
}

// ---------------------------------------------------------------- 자리 탭 시트

let sheetSpot = null;
function openSpotSheet(spot) {
  sheetSpot = spot;
  const e = session.entries[spot];
  $('spotTitle').textContent = `${spot}번 자리` + (e ? ` — ${e.status === 'vacant' ? '공차' : e.plate}` : '');
  $('spotClear').hidden = !e;
  $('spotSheet').hidden = false;
}

// ---------------------------------------------------------------- 진단

function openDiag() {
  const rows = [
    ['음성 인식 지원', isSupported(), isSupported() ? '사용 가능' : '미지원'],
    ['보안 연결(HTTPS)', window.isSecureContext, window.isSecureContext ? '정상' : '마이크 사용 불가'],
    ['음성 넘어가는 속도', true, `${SETTLE[settleIdx].label} (${SETTLE[settleIdx].ms}ms) — 눌러서 바꾸기`],
    ['키패드 숫자 읽기', keyTtsOn, keyTtsOn ? '켜짐 — 눌러서 끄기' : '꺼짐 — 눌러서 켜기'],
    ['다음 자리 안내 음성', ttsOn, ttsOn ? '켜짐 — 눌러서 끄기' : '꺼짐 — 눌러서 켜기'],
    ['키패드 입력 되읽기', padTtsOn, padTtsOn ? '켜짐 — 눌러서 끄기' : '꺼짐 — 눌러서 켜기'],
    ['화면 꺼짐 방지', 'wakeLock' in navigator, 'wakeLock' in navigator ? '지원' : '미지원'],
    ['홈화면 설치 상태', window.navigator.standalone === true, window.navigator.standalone ? '설치됨' : '사파리 탭'],
    ['네트워크', navigator.onLine, navigator.onLine ? '온라인' : '오프라인 — 음성 불가'],
  ];
  const TOGGLES = ['안내 음성', '되읽기', '숫자 읽기', '넘어가는 속도'];
  $('diagBody').innerHTML = rows.map(([k, ok, v]) => {
    const toggle = TOGGLES.some((t) => k.includes(t)) ? ' toggle' : '';
    return `<div class="diag-row${toggle}"><b>${k}</b><span class="${ok ? 'ok' : 'no'}">${v}</span></div>`;
  }).join('') +
  `<div class="diag-row"><b>저장된 순회</b><span>${workDate()} · ${countFilled(session)}건</span></div>`;

  $('diagLog').innerHTML = heardLog.length
    ? heardLog.map((l) => `<li>${l.replace(/</g, '&lt;')}</li>`).join('')
    : '<li>아직 인식된 내용이 없습니다</li>';

  $('diagBuild').textContent = BUILD;
  $('diagSheet').hidden = false;
}

/**
 * 새 버전이 올라왔는지 확인하고, 올라왔으면 알아서 새로 받는다.
 *
 * 사파리는 옛 파일을 꽤 오래 붙잡고 있어서 새로고침만으로는 풀리지 않는다.
 * version.json 만 캐시를 완전히 건너뛰고 받아와 지금 돌고 있는 것과 비교한다.
 * 같은 버전으로 두 번 새로 받는 일이 없도록 한 번 시도한 것은 기억해 둔다.
 */
async function checkForUpdate() {
  let remote;
  try {
    const res = await fetch(`version.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) return;
    remote = (await res.json()).build;
  } catch (_) {
    return;   // 전파가 없으면 그냥 지금 것으로 쓴다
  }
  if (!remote || remote === BUILD) return;

  if (sessionStorage.getItem('busyard:tried') === remote) {
    // 이미 받아봤는데도 그대로다. 무한 새로고침 대신 사용자에게 알린다.
    note('새 버전이 있습니다 — 진단에서 "최신 버전 받기"', 'warn');
    return;
  }
  sessionStorage.setItem('busyard:tried', remote);
  await forceUpdate();
}

/**
 * 사파리와 서비스 워커가 옛 파일을 붙잡고 있을 때 쓴다.
 * 캐시와 서비스 워커를 전부 지우고 주소에 새 값을 붙여 다시 받는다.
 * 입력해 둔 순회 데이터(localStorage)는 건드리지 않는다.
 */
async function forceUpdate() {
  const btn = $('diagUpdate');
  if (btn) { btn.textContent = '받는 중…'; btn.disabled = true; }
  try {
    if ('serviceWorker' in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.unregister()));
    }
    if (window.caches) {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    }
  } catch (_) { /* 지우기에 실패해도 아래 재요청은 해본다 */ }

  const url = new URL(location.href);
  url.searchParams.set('v', Date.now().toString(36));
  location.replace(url.toString());
}

// ---------------------------------------------------------------- 인쇄

// 프린터 전용 와이파이 이름. iOS는 웹에서든 앱에서든 특정 와이파이에 자동
// 접속시킬 방법이 없으므로, 어느 것을 골라야 하는지 보여주는 데까지만 한다.
const PRINTER_SSID = 'DIRECT-s0-EPSON-WF-C579R Series';

function askPrint() {
  const done = countFilled(session);
  if (done === 0) { note('입력된 자리가 없습니다', 'warn'); beep('error'); return; }
  $('printCount').textContent = `${done}자리 입력됨 · ${TOTAL - done}자리 비어 있음`;
  $('printSsid').textContent = PRINTER_SSID;
  $('printSheet').hidden = false;
}

function doPrint() {
  const done = countFilled(session);
  if (done === 0) return;
  $('printSheet').hidden = true;

  const area = $('printArea');
  area.innerHTML =
    `<div class="p-title">${YARD.name}</div>` +
    `<div class="p-meta">${session.date} · ${session.round}회차 · ${done}/${TOTAL} 입력</div>` +
    `<div class="p-map" id="pMap"></div>`;
  const pMap = $('pMap');
  buildMap(pMap, 'print');
  // 공차는 찍지 않는다. 종이에서는 빈 칸이 곧 공차이고, 글자가 있으면 지저분하다.
  pMap.querySelectorAll('.cell.spot').forEach((el) => {
    const e = session.entries[Number(el.dataset.spot)];
    if (e && e.status === 'filled') el.querySelector('.plate').textContent = e.plate;
  });
  window.print();
}

// ---------------------------------------------------------------- 시작

function init() {
  $('yardName').textContent = YARD.name.replace(/\s*\(.*\)/, '');
  $('roundName').textContent = `${session.round}회차 · ${session.date}`;

  buildMap($('map'), 'live');
  repaintAll();
  renderHud();
  if (countFilled(session) > 0) note(`이어서 ${cursor}번부터 입력합니다`);

  $('btnMic').addEventListener('click', toggleMic);
  $('btnBack').addEventListener('click', () => { primeAudio(); goBack(); });
  $('btnVacant').addEventListener('click', () => { primeAudio(); markVacant(); });
  $('btnPad').addEventListener('click', () => openPad(cursor));
  $('btnPrint').addEventListener('click', askPrint);
  $('btnDiag').addEventListener('click', openDiag);

  $('printClose').addEventListener('click', () => { $('printSheet').hidden = true; });
  $('printGo').addEventListener('click', doPrint);
  $('printCopySsid').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(PRINTER_SSID);
      $('printCopySsid').textContent = '복사됨';
      setTimeout(() => { $('printCopySsid').textContent = '이름 복사'; }, 1500);
    } catch (_) {
      $('printCopySsid').textContent = '복사 실패';
    }
  });

  $('padClose').addEventListener('click', closePad);
  document.querySelectorAll('.pad-keys button').forEach((b) =>
    b.addEventListener('click', () => padKey(b.dataset.k)));

  $('spotClose').addEventListener('click', () => { $('spotSheet').hidden = true; });
  $('spotGoto').addEventListener('click', () => {
    cursor = sheetSpot; repaintAll(); renderHud();
    $('spotSheet').hidden = true;
    if (voice) voice.reset();
    note(`${cursor}번 자리부터 입력합니다`);
  });
  $('spotPad').addEventListener('click', () => { $('spotSheet').hidden = true; openPad(sheetSpot); });
  $('spotVacant').addEventListener('click', () => {
    commit(sheetSpot, { plate: null, status: 'vacant', confidence: 'high', method: 'manual' }, { announce: false });
    $('spotSheet').hidden = true;
  });
  $('spotClear').addEventListener('click', () => {
    setEntry(session, sheetSpot, null);
    cursor = firstEmptySpot();
    repaintAll(); renderHud();
    $('spotSheet').hidden = true;
  });

  $('diagClose').addEventListener('click', () => { $('diagSheet').hidden = true; });
  $('diagUpdate').addEventListener('click', forceUpdate);

  // 되돌릴 수 없는 일이라 두 번 눌러야 지워진다
  let clearArmed = false;
  $('diagClear').addEventListener('click', () => {
    if (!clearArmed) {
      clearArmed = true;
      $('diagClear').textContent = '정말 지울까요? 한 번 더 누르세요';
      $('diagClear').classList.add('armed');
      setTimeout(() => {
        if (!clearArmed) return;
        clearArmed = false;
        $('diagClear').textContent = '이 회차 입력 전부 지우기';
        $('diagClear').classList.remove('armed');
      }, 4000);
      return;
    }
    clearArmed = false;
    clearSession(session);
    cursor = 1;
    repaintAll();
    renderHud();
    $('diagClear').textContent = '이 회차 입력 전부 지우기';
    $('diagClear').classList.remove('armed');
    $('diagSheet').hidden = true;
    note('입력을 전부 지웠습니다. 1번 자리부터 시작합니다.');
    beep('back');
  });
  $('diagBody').addEventListener('click', (ev) => {
    const row = ev.target.closest('.diag-row');
    if (!row) return;
    const name = row.querySelector('b').textContent;
    primeAudio();

    if (name.includes('안내 음성')) {
      ttsOn = !ttsOn;
      localStorage.setItem('busyard:tts', ttsOn ? '1' : '0');
      openDiag();
      if (ttsOn) speak('다음 자리를 읽어 드립니다');
    } else if (name.includes('되읽기')) {
      padTtsOn = !padTtsOn;
      localStorage.setItem('busyard:padtts', padTtsOn ? '1' : '0');
      openDiag();
      if (padTtsOn) speak(toKoreanSino('1734'), { rate: 1.7 });   // 실제 속도로 미리 들려준다
    } else if (name.includes('숫자 읽기')) {
      keyTtsOn = !keyTtsOn;
      localStorage.setItem('busyard:keytts', keyTtsOn ? '1' : '0');
      openDiag();
      if (keyTtsOn) speakDigit('7');
    } else if (name.includes('넘어가는 속도')) {
      settleIdx = (settleIdx + 1) % SETTLE.length;
      localStorage.setItem('busyard:settlems', String(SETTLE[settleIdx].ms));
      if (voice) voice.setSettle(SETTLE[settleIdx].ms);
      openDiag();
    }
  });

  [$('padSheet'), $('spotSheet'), $('diagSheet')].forEach((bg) =>
    bg.addEventListener('click', (ev) => {
      if (ev.target !== bg) return;
      if (bg.id === 'padSheet') closePad(); else bg.hidden = true;
    }));

  if (!isSupported()) handleStatus('unsupported');

  if ('serviceWorker' in navigator) {
    // updateViaCache:'none' — 서비스 워커 파일만은 사파리 캐시를 거치지 않게 한다
    navigator.serviceWorker.register('sw.js', { updateViaCache: 'none' })
      .then((reg) => reg.update().catch(() => {}))
      .catch(() => {});
  }
  checkForUpdate();
}

init();
