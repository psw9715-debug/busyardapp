import { YARD as YARD_NEW } from './yard-data.js?v=202609260602';
import { YARD_OLD } from './yard-old-data.js?v=202609260602';
import { BUILD } from './build.js?v=202609260602';
import { toKoreanSino, walkSay } from './plate.js?v=202609260602';
import { createVoice, isSupported, beep, speak, speakDigit, primeAudio } from './voice.js?v=202609260602';
import {
  loadSession, setEntry, countFilled, workDate, clearSession,
  saveLog, listLogs, readLog, deleteLog, restoreLog, mergeLegacyRound2,
  countRound, ROUNDS, upgradeSession, onSave,
} from './store.js?v=202609260602';
import { createSync, getToken, setToken } from './sync.js?v=202609260602';

// ---------------------------------------------------------------- 상태

// 차고지는 둘이다. 바꾸면 판도 커서도 따로 간다(저장 키에 차고지가 들어 있다).
// 바꿀 때는 화면을 다시 열어 처음부터 그 차고지로 세운다 — 반쯤 갈아 끼우다 어긋나지 않게.
const YARD = localStorage.getItem('busyard:yard') === 'old' ? YARD_OLD : YARD_NEW;
const OLD_YARD = YARD.id === 'old';

const spots = YARD.cells.filter((c) => c.kind === 'spot').sort((a, b) => a.spot - b.spot);
const ALL = spots.length;
// 걷는 순서에 든 자리 수. 그 뒤 번호는 예비 칸 — 눌러서 손으로만 적는다.
const TOTAL = spots.filter((c) => !c.extra).length;
const routeFilled = () => Object.keys(session.entries).filter((n) => Number(n) <= TOTAL).length;
const SPOT = new Map(spots.map((c) => [c.spot, c]));
const SPOT_BY_XL = Object.fromEntries(spots.map((c) => [c.xl, c.spot]));

/** 순회 순번 -> 엑셀에 적힌 이름 ("B5-10", "1-3-1") */
const spotName = (n) => (SPOT.get(n) ? SPOT.get(n).label : String(n));

// 구차고지는 적힌 이름과 부르는 이름이 다르다. 구두로 "1차고지 3열" 이라고 하므로
// 화면과 음성 모두 그렇게 부른다.
const ZONE = {
  '1-1': '1차고지 1열', '1-2': '1차고지 2열', '1-3': '1차고지 3열',
  '2-1': '2차고지 1열', '2-2': '2차고지 2열', '2-3': '2차고지 3열',
  '조': '조신병', '한노': '한노', '예비': '예비',
};

/** 자리가 속한 구역의 부르는 이름 ("1차고지 3열", "B5") */
function spotZone(n) {
  const label = spotName(n);
  const zone = label.slice(0, label.lastIndexOf('-'));
  return ZONE[zone] || zone;
}

/** 안내 음성용 — "B5-10" 은 "B5 10번", "1-3-1" 은 "1차고지 3열 1번" */
function spotSay(n) {
  const label = spotName(n);
  const num = label.slice(label.lastIndexOf('-') + 1);
  return OLD_YARD ? `${spotZone(n)} ${num}번` : `${label.replace('-', ' ')}번`;
}

// 회차는 "지금 무엇으로 적는가" 일 뿐이다. 순회 판은 하루에 하나이고
// 입력마다 회차 표시가 붙는다. 2회차는 1회차에 비어 있던 자리를 채우러 가는 것이라
// 기존 입력이 지워지면 안 된다.
// 회차는 그날 판에만 딸린다. 어제 2회차로 끝냈다고 오늘 첫 순찰이 2회차로 적히면 안 된다.
let round = ROUNDS.includes(Number(localStorage.getItem('busyard:round')))
  && localStorage.getItem('busyard:roundDate') === workDate()
  ? Number(localStorage.getItem('busyard:round')) : 1;
let session = upgradeSession(mergeLegacyRound2(loadSession(YARD.id, workDate(), 1)), SPOT_BY_XL);
let cursor = startSpot();
let voice = null;

// 판이 바뀌면 입력이 멎고 30초 뒤 GitHub 에 올려 둔다. 사무실 PC 가 받아서 인쇄한다.
let syncState = { state: getToken() ? 'idle' : 'notoken' };
const sync = createSync({
  getSession: () => session,
  onStatus: (st) => { syncState = st; if (!$('diagSheet').hidden) openDiag(); },
});
onSave(() => sync.schedule());
let wakeLock = null;
const heardLog = [];

const $ = (id) => document.getElementById(id);
const cellEls = new Map();   // spot 번호 -> DOM

/**
 * 2회차에 다시 들러야 하는 자리인가.
 * 공차는 "차가 없었다"는 뜻이라 그 사이에 새로 들어왔을 수 있다.
 * 아직 안 적은 칸과 똑같이 취급해서 건너뛰지 않는다.
 */
function isOpen(n) {
  const e = session.entries[n];
  if (!e) return true;
  return round === 2 && e.status === 'vacant';
}

/**
 * 앱을 다시 열었을 때 시작할 자리.
 * 2회차 확인은 걷는 순서 첫 자리부터 한 칸씩 도는 것이라 1번에서 시작하고,
 * 돌던 중에 껐으면 그 자리에서 이어받는다.
 */
function startSpot() {
  try {
    const c = JSON.parse(localStorage.getItem('busyard:cursor') || 'null');
    if (c && c.date === session.date && c.round === round && c.spot >= 1 && c.spot <= TOTAL) return c.spot;
  } catch (_) { /* 깨졌으면 처음부터 */ }
  return round === 2 ? 1 : firstEmptySpot();
}

function saveCursor() {
  localStorage.setItem('busyard:cursor', JSON.stringify({ date: session.date, round, spot: cursor }));
}

function firstEmptySpot() {
  for (let n = 1; n <= TOTAL; n++) if (isOpen(n)) return n;
  return TOTAL;
}

function openCount() {
  let c = 0;
  for (let n = 1; n <= TOTAL; n++) if (isOpen(n)) c += 1;
  return c;
}

// ---------------------------------------------------------------- 배치도

function buildMap(container, cls) {
  container.innerHTML = '';
  for (const c of YARD.cells) {
    const el = document.createElement('div');
    el.className = 'cell ' + c.kind;
    el.style.gridColumn = `${c.col} / span ${c.colspan}`;
    el.style.gridRow = `${c.row} / span ${c.rowspan}`;

    // 테두리는 원본의 굵기 차이를 따르지 않고 전부 같은 얇은 선으로 긋는다.

    if (c.kind === 'spot') {
      el.dataset.spot = c.spot;
      // 순회 번호는 화면에서만 쓴다. 인쇄물은 지금 쓰는 종이와 똑같이
      // 번호 없는 빈 칸에 차량번호만 찍혀야 한다 (CSS에서 숨김).
      // 칸이 좁아 "에디슨-13" 이 다 안 들어간다. 한글 구역은 첫 글자만 남긴다 (에13).
      // 예비 칸은 번호를 찍지 않는다.
      // 칸이 좁다. 신차고지는 구역 첫 글자만(에13), 구차고지는 번호만 남긴다(줄은 배치로 안다).
      const short = c.extra ? ''
        : OLD_YARD ? c.label.slice(c.label.lastIndexOf('-') + 1)
          : c.label.replace(/^([가-힣])[가-힣]*-/, '$1');
      el.innerHTML = `<span class="no">${short}</span><span class="plate"></span>`;
      if (cls === 'live') {
        // 두 번 톡(확대)의 첫 번째 톡일 수 있으므로 잠깐 기다렸다 연다
        el.addEventListener('click', () => {
          clearTimeout(tapTimer);
          tapTimer = setTimeout(() => openSpotSheet(c.spot), DOUBLE_TAP_MS);
        });
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

  el.classList.remove('filled', 'vacant', 'car', 'corrected', 'current', 'target', 'k-cctv', 'k-key', 'r1', 'r2');
  if (e && e.status === 'car') {
    el.classList.add('car');
    plateEl.textContent = '승용차';
  } else if (e && e.status === 'vacant') {
    el.classList.add('vacant');
    plateEl.textContent = '공차';
  } else if (e) {
    // 회차마다 색이 달라야 2회차에 무엇이 바뀌었는지 눈에 들어온다.
    // 음성이든 키패드든 같은 회차면 같은 색이다.
    el.classList.add('filled', 'r' + (e.round || 1));
    if (e.confidence === 'corrected' || e.confidence === 'assumed') el.classList.add('corrected');
    const kind = targetKind(e.plate);
    if (kind) el.classList.add('target', 'k-' + kind);
    plateEl.textContent = e.plate;
  } else {
    plateEl.textContent = '';
  }
  if (n === cursor) el.classList.add('current');
}

function repaintAll() {
  for (const n of SPOT.keys()) paintSpot(n);
}

// ---------------------------------------------------------------- 배치도 확대

// 화면이 작아 칸을 손가락으로 짚기 어렵다. 두 손가락으로 벌리면 커진다.
// transform 대신 폭을 늘리는 방식이라, 커진 만큼 스크롤도 그대로 따라온다.
const ZOOM_MIN = 1;
const ZOOM_MAX = 4;
const TAP_ZOOM = 2.5;        // 두 번 톡 쳤을 때 배율
const DOUBLE_TAP_MS = 300;
let tapTimer = null;         // 칸 한 번 톡 — 두 번째 톡이 오면 취소
let zoom = Number(localStorage.getItem('busyard:zoom')) || 1;

// 확대하지 않았을 때의 배치도 크기. 폭만 늘리면 세로가 따라오지 않아
// 비율이 깨지므로, 통째로 배율을 걸고 담는 상자를 그만큼 키운다.
let natW = 0;
let natH = 0;

function measureNatural() {
  const box = $('mapZoom');
  const map = $('map');
  map.style.transform = 'none';
  map.style.width = '100%';
  box.style.width = '';
  box.style.height = '';
  natW = map.offsetWidth;
  natH = map.offsetHeight;
}

function applyZoom(next, anchor) {
  const wrap = $('mapwrap');
  const box = $('mapZoom');
  const map = $('map');
  if (!natW) measureNatural();

  const k = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, next));

  // 손가락 사이 지점이 제자리에 있도록 스크롤을 맞춘다
  const a = anchor || { x: wrap.clientWidth / 2, y: wrap.clientHeight / 2 };
  const rx = (wrap.scrollLeft + a.x) / (natW * zoom || 1);
  const ry = (wrap.scrollTop + a.y) / (natH * zoom || 1);

  zoom = k;
  localStorage.setItem('busyard:zoom', String(k));

  map.style.width = `${natW}px`;
  map.style.transformOrigin = '0 0';
  map.style.transform = `scale(${k})`;
  box.style.width = `${natW * k}px`;
  box.style.height = `${natH * k}px`;

  wrap.scrollLeft = rx * natW * k - a.x;
  wrap.scrollTop = ry * natH * k - a.y;

  const chip = $('zoomChip');
  chip.textContent = `${k.toFixed(1)}×`;
  chip.hidden = k <= 1.001;
}

function setupZoom() {
  const wrap = $('mapwrap');
  let start = null;
  const gap = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);

  // 두 번 톡 — 대략 짚은 곳을 가운데로 크게, 커진 상태면 원래대로
  let tap = null;       // 손가락 하나로 짚고 움직이지 않은 톡
  let lastTap = null;

  wrap.addEventListener('touchstart', (e) => {
    tap = e.touches.length === 1 ? { x: e.touches[0].clientX, y: e.touches[0].clientY } : null;
    if (e.touches.length !== 2) { start = null; return; }
    const r = wrap.getBoundingClientRect();
    start = {
      d: gap(e.touches),
      z: zoom,
      anchor: {
        x: (e.touches[0].clientX + e.touches[1].clientX) / 2 - r.left,
        y: (e.touches[0].clientY + e.touches[1].clientY) / 2 - r.top,
      },
    };
  }, { passive: true });

  wrap.addEventListener('touchmove', (e) => {
    if (tap && Math.hypot(e.touches[0].clientX - tap.x, e.touches[0].clientY - tap.y) > 10) tap = null;
    if (e.touches.length !== 2 || !start) return;
    e.preventDefault();                       // 사파리가 페이지째 확대하는 것을 막는다
    applyZoom(start.z * (gap(e.touches) / start.d), start.anchor);
  }, { passive: false });

  wrap.addEventListener('touchend', (e) => {
    start = null;
    if (!tap || e.touches.length) { lastTap = null; return; }
    const now = Date.now();
    const t = { at: now, x: tap.x, y: tap.y };
    tap = null;
    if (!lastTap || now - lastTap.at > DOUBLE_TAP_MS || Math.hypot(t.x - lastTap.x, t.y - lastTap.y) > 40) {
      lastTap = t;
      return;
    }
    lastTap = null;
    e.preventDefault();                       // 두 번째 톡이 칸을 누른 것으로 가지 않게
    clearTimeout(tapTimer);
    const r = wrap.getBoundingClientRect();
    const a = { x: t.x - r.left, y: t.y - r.top };
    if (zoom > 1.001) { applyZoom(1, a); return; }
    applyZoom(TAP_ZOOM, a);
    wrap.scrollLeft += a.x - wrap.clientWidth / 2;
    wrap.scrollTop += a.y - wrap.clientHeight / 2;
  }, { passive: false });

  $('zoomChip').addEventListener('click', () => applyZoom(1));

  // 화면이 돌아가거나 크기가 바뀌면 기준 크기를 다시 잰다
  window.addEventListener('resize', () => {
    const k = zoom;
    measureNatural();
    zoom = 1;
    applyZoom(k);
  });

  measureNatural();
  applyZoom(zoom);
}

// ---------------------------------------------------------------- 안내판

function renderHud(flash) {
  $('hudSpot').textContent = spotName(cursor);
  if (OLD_YARD) $('hudUnit').textContent = spotZone(cursor);
  const done = routeFilled();
  $('hudCount').textContent = `${done} / ${TOTAL}`;
  $('progressFill').style.width = `${(done / TOTAL) * 100}%`;

  const plateEl = $('hudPlate');
  plateEl.className = 'hud-plate';

  const e = flash || session.entries[cursor];
  if (e && e.status === 'car') {
    plateEl.textContent = phoneText(e.phone);
    plateEl.classList.add('car');
  } else if (flash) {
    if (flash.status === 'vacant') { plateEl.textContent = '공차'; plateEl.classList.add('vacant'); }
    else { plateEl.textContent = flash.plate; if (flash.confidence !== 'high') plateEl.classList.add('corrected'); }
  } else if (e) {
    if (e.status === 'vacant') { plateEl.textContent = '공차'; plateEl.classList.add('vacant'); }
    else { plateEl.textContent = e.plate; if (e.confidence !== 'high') plateEl.classList.add('corrected'); }
  } else {
    plateEl.innerHTML = '<span class="ph">– – – –</span>';
  }
}

/** 01012345678 -> 010-1234-5678 */
const phoneText = (p) => (p ? `${p.slice(0, 3)}-${p.slice(3, 7)}-${p.slice(7)}` : '');

function note(text, kind) {
  const el = $('hudNote');
  el.textContent = text;
  el.className = 'hud-note' + (kind ? ' ' + kind : '');
}

// ---------------------------------------------------------------- 입력 반영

/**
 * 다음에 갈 자리 — 걷는 순서 그대로 한 칸.
 * 2회차도 모든 칸을 지나간다. 적힌 번호가 눈앞의 차와 같으면 "확인" 한 번으로
 * 바로 넘어가고, 차가 바뀌었거나 빠진 칸에만 손을 댄다.
 */
function nextSpotAfter(spot) {
  return Math.min(spot + 1, TOTAL);
}

/** 2회차 확인 — 적힌 그대로 두고 다음 칸으로 */
function confirmSpot() {
  if (cursor >= TOTAL) {
    note('마지막 자리입니다', 'warn');
    beep('done');
    return;
  }
  beep('ok');
  const from = cursor;
  cursor = nextSpotAfter(cursor);
  saveCursor();
  paintSpot(from);
  paintSpot(cursor);
  renderHud();
  note('');
  if (!$('padSheet').hidden) padFollowCursor();
  announceCursor();
}

function commit(spot, entry, { announce = true } = {}) {
  setEntry(session, spot, { ...entry, round });
  saveCursor();
  paintSpot(spot);

  // 예비 칸은 걷는 순서 밖이라 커서를 움직이지 않는다
  const isLast = spot === TOTAL;
  if (spot <= TOTAL) cursor = isLast ? TOTAL : nextSpotAfter(spot);
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
    beep('vacant');
  } else {
    note('');
    beep('ok');
  }

  renderTargetBadge();

  // 찾던 차량이면 다른 안내보다 먼저, 확실하게 알린다
  const hitKind = entry.status === 'filled' ? targetKind(entry.plate) : null;
  if (hitKind) {
    announceTarget(entry.plate, spot, hitKind);
    return;
  }

  if (isLast && routeFilled() >= TOTAL) {
    note(`${TOTAL}자리 전부 입력 완료`, 'warn');
    beep('done');
    if (announce) announceSpeak('순회 완료');
    return;
  }
  if (announce) announceCursor();
}

function goBack() {
  // 이번 회차에 방금 넣은 것을 되돌린다. 지난 회차 기록은 건드리지 않는다.
  let n = cursor - 1;
  if (round === 2) {
    while (n >= 1 && !(session.entries[n] && (session.entries[n].round || 1) === 2)) n -= 1;
    if (n < 1) {
      note('되돌릴 2회차 입력이 없습니다', 'warn');
      beep('error');
      return;
    }
  }
  if (n < 1) n = 1;

  // "다음" 으로 한꺼번에 공차 처리한 칸은 한꺼번에 되돌린다
  const e = session.entries[n];
  if (e && e.method === 'next') {
    for (let k = e.from; k <= TOTAL; k++) {
      if (session.entries[k] && session.entries[k].from === e.from) setEntry(session, k, null);
      else if (k > n) break;
    }
    n = e.from;
  } else {
    setEntry(session, n, null);
  }

  cursor = n;
  repaintAll();
  renderHud();
  note(`${spotName(cursor)}번 자리로 되돌렸습니다`);
  beep('back');
  saveCursor();
  if (voice) voice.reset();
  saidSeg = null;   // 되돌아온 자리가 어느 구역인지 다시 알려 준다
  announceCursor();
}

function markVacant() {
  commit(cursor, { plate: null, status: 'vacant', confidence: 'high', method: 'manual' });
}

/**
 * 이 구역에 더 볼 차가 없을 때 다음 구역 첫 자리로 건너뛴다 (B0-10 에서 B2-1 로).
 * 1회차는 남은 칸을 공차로 채운다 — 차가 없어 넘어간 것이니 공차가 맞고,
 * 그래야 2회차에 다시 들를 자리로 남는다. 2회차는 빈 자리만 찾아갈 뿐 적지 않는다.
 */
function goNext() {
  const seg = SPOT.get(cursor).seg;
  let to = cursor;
  while (to <= TOTAL && SPOT.get(to).seg === seg) to += 1;

  if (round === 1) {
    const from = cursor;
    for (let n = from; n < to; n++) {
      if (session.entries[n]) continue;
      setEntry(session, n, { plate: null, status: 'vacant', confidence: 'high', method: 'next', from, round });
    }
  }
  if (to > TOTAL) {
    if (round === 1) cursor = TOTAL;
    repaintAll();
    renderHud();
    note(round === 1 ? '마지막 구역입니다 — 남은 칸을 공차로 채웠습니다' : '뒤에 남은 빈 자리가 없습니다', 'warn');
    beep('done');
    return;
  }

  cursor = to;
  repaintAll();
  renderHud();
  note(`다음 구역 — ${spotName(cursor)}번 자리`);
  beep('next');
  saveCursor();
  if (voice) voice.reset();
  saidSeg = null;   // 구역이 바뀌었으니 자리 이름부터 읽는다
  announceCursor();
}

/** 안내 음성. 말하는 동안 자기 목소리가 다시 인식되지 않게 막는다. */
function announceSpeak(text) {
  if (!ttsOn) return;
  const ms = speak(text, { rate: rate.say });
  if (voice) voice.muteFor(ms + 250);
}

// 방금 읽어 준 자리의 구역. 구역이 바뀐 첫 칸에서만 자리 이름을 읽는다.
let saidSeg = null;

/**
 * 커서가 선 자리를 읽어 준다.
 * 1회차는 갈 자리를 불러 주면 되고, 2회차 확인은 눈앞의 차와 맞춰 볼
 * "적혀 있는 번호" 를 불러 줘야 한다.
 */
function announceCursor() {
  const cell = SPOT.get(cursor);
  const newSeg = !cell || cell.seg !== saidSeg;
  saidSeg = cell ? cell.seg : null;
  if (round === 2) announceSpeak(walkSay(spotSay(cursor), session.entries[cursor], newSeg));
  else announceSpeak(spotSay(cursor));
}

// 2회차 확인은 적힌 번호를 귀로 듣는 것이 핵심이라 기본 켜짐
let ttsOn = localStorage.getItem('busyard:tts') !== '0';
// 키패드로 넣은 번호를 한국식으로 되읽어 확인시켜 준다 ("734" -> "천칠백삼십사")
let padTtsOn = localStorage.getItem('busyard:padtts') === '1';
// 키패드에서 누른 숫자를 바로 읽어준다 ("7" -> "칠"). 기본 켜짐.
let keyTtsOn = localStorage.getItem('busyard:keytts') !== '0';

// 말이 멎고 얼마 만에 확정할지. 짧을수록 다음 자리로 빨리 넘어가지만,
// 번호를 중간에 끊어 말하면 두 개로 쪼개질 수 있다.
// 다 부른 번호("천칠백이십사")는 이 값과 무관하게 거의 바로 넘어간다.
const SETTLE = [
  { ms: 120, label: '번개' },
  { ms: 200, label: '아주 빠름' },
  { ms: 300, label: '빠름' },
  { ms: 450, label: '보통' },
  { ms: 700, label: '느림' },
];
/**
 * 읽어 주는 속도 — 소리마다 하는 일이 달라 알맞은 빠르기도 다르다.
 * 숫자 하나는 또박또박, 되읽기는 빠르게, 안내는 그 중간이다.
 * 각각 진단에서 따로 고른다.
 */
const RATES = {
  say:   { steps: [0.9, 1, 1.25, 1.6, 2], def: 1.25, key: 'busyard:sayrate' },
  digit: { steps: [0.6, 0.75, 1, 1.3], def: 0.75, key: 'busyard:digitrate' },
  read:  { steps: [1.1, 1.4, 1.7, 2], def: 1.7, key: 'busyard:readrate' },
};
const rate = {};
for (const [name, r] of Object.entries(RATES)) {
  const saved = Number(localStorage.getItem(r.key));
  rate[name] = r.steps.includes(saved) ? saved : r.def;
}

/** 다음 단계로 돌린다 (마지막 다음은 처음으로) */
function cycleRate(name) {
  const r = RATES[name];
  rate[name] = r.steps[(r.steps.indexOf(rate[name]) + 1) % r.steps.length];
  localStorage.setItem(r.key, String(rate[name]));
  return rate[name];
}

const savedSettle = Number(localStorage.getItem('busyard:settlems'));
let settleIdx = SETTLE.findIndex((s) => s.ms === savedSettle);
if (settleIdx < 0) settleIdx = 1;   // 기본 아주 빠름

function readBackPlate(plate) {
  if (!padTtsOn || !plate) return;
  const ms = speak(toKoreanSino(plate), { rate: rate.read });
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
  } else if (t.type === 'next') {
    goNext();
  } else if (t.type === 'car') {
    // 전화번호는 여덟 자리라 말로 받으면 한 자리만 틀려도 못 쓴다. 키패드로 받는다.
    openPad(cursor);
    padPhone = true;
    padDigits = '';
    renderPad();
    beep('warn');
  } else if (t.type === 'confirm') {
    if (round === 2) confirmSpot();
    else beep('warn');   // 1회차에는 확인할 것이 없다
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
// 승용차 전화번호를 받는 중인가. 앞 010 은 고정이라 나머지 여덟 자리만 받는다.
let padPhone = false;

function openPad(spot) {
  primeAudio();
  // 1회차에 키패드를 쓰는 동안 마이크가 켜져 있으면 숫자 읽는 소리까지 받아 적는다.
  // 닫아도 다시 켜지 않는다 — 음성으로 돌아갈 때 직접 누르면 된다.
  // 2회차 확인은 이 화면을 켜 둔 채 "확인" 이라고 말하며 도는 것이라 마이크를 끄지 않는다.
  if (round === 1 && voice && voice.isOn()) { voice.stop(); releaseWakeLock(); }

  padSpot = spot; padDigits = ''; padPhone = false;
  $('padTitle').textContent = padTitleOf(spot);
  renderPad();
  $('padSheet').hidden = false;
}

/** 입력·이전·다음 뒤에 커서가 간 자리를 이어서 받는다 */
function padFollowCursor() {
  padSpot = cursor; padDigits = ''; padPhone = false;
  $('padTitle').textContent = padTitleOf(padSpot);
  renderPad();
}

function closePad() {
  $('padSheet').hidden = true;
}
function renderPad() {
  if (padPhone) {
    $('padDisplay').className = 'pad-display phone';
    const d = padDigits.padEnd(8, '_');
    $('padPhone').textContent = `010-${d.slice(0, 4)}-${d.slice(4)}`;
    return;
  }
  // 아직 아무것도 안 눌렀으면 이미 적혀 있는 번호를 크게 보여 준다.
  // 2회차에 눈앞의 차와 맞춰 보는 것이 이 화면이 하는 일이다.
  const e = padDigits ? null : session.entries[padSpot];
  $('padDisplay').className = 'pad-display' + (e ? ' kept' : '');
  $('padKept').textContent = e ? (e.status === 'vacant' ? '공차' : e.plate) : '';
  document.querySelectorAll('#padDisplay .slot').forEach((el, i) => {
    const ch = padDigits[i];
    el.textContent = ch || '_';
    el.classList.toggle('set', Boolean(ch));
  });
}
/** 키패드 머리에 쓰는 자리 이름 */
const padTitleOf = (spot) => (OLD_YARD ? `${spotZone(spot)} ${spotName(spot).split('-').pop()}번 자리`
  : `${spotName(spot)}번 자리`);

function padKey(k) {
  primeAudio();
  if (k === 'car') {
    // 버스 자리에 승용차가 서 있다 — 그 차 주인의 전화번호를 받는다
    padPhone = true;
    padDigits = '';
    renderPad();
    beep('warn');
    return;
  }
  if (k === 'ok') {
    confirmSpot();
    return;
  }
  if (k === 'back' && padDigits) {
    // 누르던 숫자가 있으면 그것부터 지운다. 없을 때만 앞 자리로 되돌린다.
    padDigits = padDigits.slice(0, -1);
    renderPad();
    beep('back');
    return;
  }
  if (k === 'vacant') {
    commit(padSpot, { plate: null, status: 'vacant', confidence: 'high', method: 'keypad' }, { announce: false });
    padFollowCursor();
    return;
  }
  if (k === 'back' || k === 'next') {
    // 시트를 자리 탭으로 연 경우도 있으니 커서를 그 자리에 맞춘 뒤 움직인다
    if (padSpot <= TOTAL) cursor = padSpot;
    if (k === 'back') goBack(); else goNext();
    padFollowCursor();
    return;
  }
  const room = padPhone ? 8 : 3;
  if (padDigits.length >= room) return;
  padDigits += k;
  renderPad();
  if (keyTtsOn) speakDigit(k, rate.digit);   // 무엇을 눌렀는지 귀로 확인
  if (padDigits.length < room) return;

  if (padPhone) {
    const phone = '010' + padDigits;
    commit(padSpot, { plate: null, phone, status: 'car', confidence: 'high', method: 'keypad' },
      { announce: false });
    note(`승용차 ${phoneText(phone)}`);
  } else {
    const plate = '1' + padDigits;
    commit(padSpot, { plate, status: 'filled', confidence: 'high', method: 'keypad' }, { announce: false });
    readBackPlate(plate);
  }
  // 이어서 다음 자리를 계속 찍을 수 있게 시트를 열어 둔다
  padFollowCursor();
}

// ---------------------------------------------------------------- 자리 탭 시트

let sheetSpot = null;
function openSpotSheet(spot) {
  sheetSpot = spot;
  const e = session.entries[spot];
  $('spotTitle').textContent = `${spotName(spot)}번 자리` + (e ? ` — ${e.status === 'vacant' ? '공차' : e.plate}` : '');
  $('spotClear').hidden = !e;
  $('spotGoto').hidden = spot > TOTAL;
  $('spotSheet').hidden = false;
}

// ---------------------------------------------------------------- 찾을 차량

const MAX_TARGETS = 10;

// 회수해야 하는 것이 무엇이냐에 따라 나뉜다. 색과 안내 음성이 다르다.
const KINDS = {
  cctv: { label: 'CCTV', say: '비디오' },
  key:  { label: 'KEY',  say: '열쇠' },
};

function loadTargets() {
  try {
    const v = JSON.parse(localStorage.getItem('busyard:targets') || '[]');
    if (!Array.isArray(v)) return [];
    // 예전에는 번호만 문자열로 담았다. 그때 것은 CCTV로 본다.
    return v.slice(0, MAX_TARGETS).map((t) =>
      (typeof t === 'string' ? { plate: t, kind: 'cctv' }
        : { plate: t.plate, kind: KINDS[t.kind] ? t.kind : 'cctv' }));
  } catch (_) { return []; }
}
let targets = loadTargets();

function saveTargets() {
  localStorage.setItem('busyard:targets', JSON.stringify(targets));
  renderTargetBadge();
}

/** 이 번호가 찾을 차량이면 그 종류를 돌려준다 */
function targetKind(plate) {
  if (!plate) return null;
  const t = targets.find((x) => x.plate === plate);
  return t ? t.kind : null;
}

function foundCount() {
  return targets.filter((t) =>
    Object.values(session.entries).some((e) => e.plate === t.plate)).length;
}

function renderTargetBadge() {
  const badge = $('targetBadge');
  const found = foundCount();
  badge.hidden = targets.length === 0;
  badge.textContent = targets.length ? `${found}/${targets.length}` : '';
  badge.classList.toggle('all', targets.length > 0 && found === targets.length);
}

/** 찾던 차를 만났을 때 — 소리와 음성으로 알리고 화면에 남긴다 */
function announceTarget(plate, spot, kind) {
  const k = KINDS[kind] || KINDS.cctv;
  beep('alert');
  const ms = speak(`${k.say}, ${toKoreanSino(plate)}, ${spotSay(spot)} 자리`, { rate: 1.1 });
  if (voice) voice.muteFor(ms + 300);
  note(`★ ${k.label} ${plate} — ${spotName(spot)}번 자리`, 'warn');
}

function renderTargetList() {
  const ul = $('targetList');
  $('targetCount').textContent = `${targets.length}/${MAX_TARGETS}`;
  if (!targets.length) {
    ul.innerHTML = '<li class="target-empty">아직 없습니다</li>';
    return;
  }
  ul.innerHTML = targets.map((t) => {
    const spot = Object.keys(session.entries).find((n) => session.entries[n].plate === t.plate);
    const where = spot ? `<span class="target-at">${spotName(Number(spot))}번 자리</span>` : '<span class="target-wait">아직</span>';
    return `<li class="k-${t.kind}"><span class="target-kind">${KINDS[t.kind].label}</span>`
      + `<b>${t.plate}</b>${where}<button data-plate="${t.plate}" aria-label="빼기">✕</button></li>`;
  }).join('');
}

// ---------------------------------------------------------------- 찾기

/** 뒤 세 자리로 시작하는 차량이 있는 자리들 */
function findSpots(digits) {
  const out = [];
  for (const [n, e] of Object.entries(session.entries)) {
    if (e.status !== 'filled' || !e.plate) continue;
    if (e.plate.slice(1).startsWith(digits)) out.push({ spot: Number(n), plate: e.plate });
  }
  return out.sort((a, b) => a.spot - b.spot);
}

function highlightSpot(n) {
  cellEls.forEach((el) => el.classList.remove('found'));
  const el = cellEls.get(n);
  if (!el) return;
  el.classList.add('found');
  el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
}

// ---------------------------------------------------------------- 회차

function renderRound() {
  const btn = $('btnRound');
  btn.textContent = `${round}회차`;
  btn.classList.toggle('r2', round === 2);
  // 2회차에는 1회차 기록을 죽여서, 아직 차가 안 들어온 자리가 도드라지게 한다
  document.body.classList.toggle('round2', round === 2);
}

/**
 * 회차를 바꾼다. 순회 판은 그대로 두고 "지금 무엇으로 적는가" 만 바뀐다.
 * 2회차는 1회차에 비어 있던 자리를 채우러 가는 것이므로, 앞서 적은 것은
 * 1회차 색 그대로 남고 커서만 첫 빈 칸으로 간다.
 */
function switchRound(next) {
  if (!ROUNDS.includes(next) || next === round) return;
  if (voice && voice.isOn()) voice.stop();

  round = next;
  localStorage.setItem('busyard:round', String(round));
  localStorage.setItem('busyard:roundDate', workDate());
  cursor = round === 2 ? 1 : firstEmptySpot();   // 확인은 걷는 순서 첫 자리부터
  saveCursor();
  saidSeg = null;

  renderRound();
  repaintAll();
  renderHud();

  note(round === 2
    ? `2회차 확인 — ${spotName(cursor)}번부터 한 칸씩 (채울 칸 ${openCount()})`
    : `1회차로 돌아왔습니다`);
  beep('back');

  // 구차고지 2회차는 방향이 반대다. 1차 뒤에 들어온 차를 사무실에서 엑셀에 적어 두므로,
  // 그 판을 받아다 깔고 그 위에서 고치고 더한다.
  if (OLD_YARD && round === 2) pullFromExcel();
}

/** PC 에게 원본 엑셀의 지금 자리들을 받아다 판에 깐다 */
async function pullFromExcel() {
  if (!getToken()) {
    note('토큰이 없습니다 — [진단] → PC 전송에서 넣으세요', 'warn');
    return;
  }
  note('PC가 엑셀에서 가져오는 중…');
  let id;
  try {
    id = await sync.requestPrint('pull');
  } catch (err) {
    note(`가져오기를 보내지 못했습니다: ${err.message}`, 'warn');
    beep('error');
    return;
  }

  const until = Date.now() + 300000;
  while (Date.now() < until) {
    await new Promise((r) => setTimeout(r, 3000));
    let got = null;
    try { got = await sync.readPulled(); } catch (_) { continue; }
    if (!got || got.id !== id) continue;

    // 받아 온 것은 밑바탕이다 — 1회차로 깔아 두면 인쇄물에서 흐리게 나오고,
    // 지금부터 고치거나 더하는 것만 2회차로 진하게 나온다.
    for (const [spot, e] of Object.entries(got.entries)) {
      setEntry(session, spot, { ...e, round: 1, method: 'excel' });
    }
    cursor = 1;
    saveCursor();
    saidSeg = null;
    repaintAll();
    renderHud();
    note(`엑셀에서 ${Object.keys(got.entries).length}대를 받았습니다 — ${spotName(cursor)}번부터`);
    beep('done');
    return;
  }
  note('PC 응답이 없습니다 — sctc-copy 가 켜져 있는지 확인하세요', 'warn');
  beep('warn');
}

// ---------------------------------------------------------------- 일지 보관

function renderLogList() {
  const ul = $('logList');
  const logs = listLogs();
  if (!logs.length) {
    ul.innerHTML = '<li class="log-empty">저장된 일지가 없습니다</li>';
    return;
  }
  ul.innerHTML = logs.map((l) => {
    const time = new Date(l.savedAt).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    const today = l.date === workDate() ? '<span class="log-today">오늘</span>' : '';
    return `<li>
      <div class="log-when"><b>${l.date}</b>${today}
        <span class="log-meta">${time} 저장 · 1회차 ${l.counts[0]}대 · 2회차 ${l.counts[1]}대 · 대상 ${l.targets}대</span></div>
      <button class="log-load" data-date="${l.date}">불러오기</button>
      <button class="log-del" data-del="${l.date}" aria-label="지우기">✕</button>
    </li>`;
  }).join('');
}

function doSaveLog() {
  const counts = ROUNDS.map((r) => countRound(session.entries, r));
  if (!counts.some(Boolean)) {
    $('logSaveNote').textContent = '입력된 자리가 없어 저장할 것이 없습니다.';
    beep('error');
    return;
  }
  saveLog(session, targets);
  sync.flush();
  $('logSaveNote').textContent =
    `${workDate()} 저장 완료 — 1회차 ${counts[0]}대 · 2회차 ${counts[1]}대 · 대상 ${targets.length}대`;
  renderLogList();
  beep('done');
}

/** 저장해 둔 날짜의 배치와 대상 목록을 지금 화면으로 되살린다 */
function doLoadLog(date) {
  const rec = readLog(date);
  if (!rec) return;

  restoreLog(rec, session, SPOT_BY_XL);
  targets = (rec.targets || []).map((t) =>
    (typeof t === 'string' ? { plate: t, kind: 'cctv' } : t));
  saveTargets();

  cursor = firstEmptySpot();
  repaintAll();
  renderHud();
  renderTargetBadge();
  $('logSheet').hidden = true;
  note(`${date} 일지를 불러왔습니다 — 모두 ${countFilled(session)}대`);
  beep('ok');
}

// ---------------------------------------------------------------- 진단

/** 속도를 한 단계 돌리고(소리로 들려주고) 화면을 새 값으로 다시 그린다 */
function openDiagAfter(change) {
  change();
  openDiag();
}

function syncText() {
  const st = syncState;
  if (st.state === 'notoken') return '토큰 없음 — 눌러서 넣기';
  if (st.state === 'fail') return `실패: ${st.detail} — 눌러서 다시`;
  if (st.state === 'ok') {
    const t = `${String(st.at.getHours()).padStart(2, '0')}:${String(st.at.getMinutes()).padStart(2, '0')}`;
    return `${t} 올림 — 눌러서 지금 올리기`;
  }
  return '아직 안 올림 — 눌러서 지금 올리기';
}

function openDiag() {
  const rows = [
    ['음성 인식 지원', isSupported(), isSupported() ? '사용 가능' : '미지원'],
    ['보안 연결(HTTPS)', window.isSecureContext, window.isSecureContext ? '정상' : '마이크 사용 불가'],
    ['음성 넘어가는 속도', true, `${SETTLE[settleIdx].label} (${SETTLE[settleIdx].ms}ms) — 눌러서 바꾸기`, 'settle'],
    ['키패드 숫자 읽기', keyTtsOn, keyTtsOn ? '켜짐 — 눌러서 끄기' : '꺼짐 — 눌러서 켜기', 'keytts'],
    ['└ 숫자 읽는 속도', true, `${rate.digit}배 — 눌러서 바꾸기`, 'digitrate'],
    ['다음 자리 안내 음성', ttsOn, ttsOn ? '켜짐 — 눌러서 끄기' : '꺼짐 — 눌러서 켜기', 'tts'],
    ['└ 자리·번호 읽는 속도', true, `${rate.say}배 — 눌러서 바꾸기`, 'sayrate'],
    ['키패드 입력 되읽기', padTtsOn, padTtsOn ? '켜짐 — 눌러서 끄기' : '꺼짐 — 눌러서 켜기', 'padtts'],
    ['└ 되읽는 속도', true, `${rate.read}배 — 눌러서 바꾸기`, 'readrate'],
    ['화면 꺼짐 방지', 'wakeLock' in navigator, 'wakeLock' in navigator ? '지원' : '미지원'],
    ['홈화면 설치 상태', window.navigator.standalone === true, window.navigator.standalone ? '설치됨' : '사파리 탭'],
    ['네트워크', navigator.onLine, navigator.onLine ? '온라인' : '오프라인 — 음성 불가'],
    ['PC 전송', syncState.state === 'ok' || syncState.state === 'idle', syncText(), 'sync'],
  ];
  $('diagBody').innerHTML = rows.map(([k, ok, v, act]) => {
    const sub = k.startsWith('└') ? ' sub' : '';
    return `<div class="diag-row${act ? ' toggle' : ''}${sub}"${act ? ` data-act="${act}"` : ''}>`
      + `<b>${k}</b><span class="${ok ? 'ok' : 'no'}">${v}</span></div>`;
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

// 인쇄도 엑셀 입력도 사무실 PC 가 한다. 폰은 판과 요청을 GitHub 에 올리고,
// PC(sctc-copy 안의 tools/inbox.py)가 받아 종이로 뽑거나 운영관리 엑셀에 넣고 결과를 남긴다.
//
//   종이 인쇄 — 원본 엑셀에 채워 기본 프린터로
//   엑셀 입력 — 그날 "입출차 운영관리" 의 6차고지 칸에 그대로 (손으로 옮겨 적던 일)
// 종이는 금방 나오지만, 운영관리 엑셀은 파일이 무거워 여는 데만 30초가 넘는다
const WAIT_MS = { paper: 90000, excel: 300000 };
let printing = false;   // 보낸 요청의 결과를 기다리는 중

function printMsg(text, kind) {
  $('printMsg').textContent = text;
  $('printMsg').className = 'print-msg' + (kind ? ' ' + kind : '');
}

/** 인쇄 시트를 연다. 무엇을 할지는 시트 안에서 고른다. */
function openPrint() {
  const done = countFilled(session);
  if (done === 0) { note('입력된 자리가 없습니다', 'warn'); beep('error'); return; }
  const r2 = countRound(session.entries, 2);
  $('printCount').textContent = r2 > 0
    ? `모두 ${done}자리 — 2회차 ${r2}자리는 진하게, 1회차는 흐리게`
    : `${done}자리 입력됨 · ${ALL - done}자리 비어 있음`;
  if (!printing) printMsg(getToken() ? '' : '토큰이 없습니다 — [진단] → PC 전송에서 넣으세요',
    getToken() ? '' : 'no');
  $('printSheet').hidden = false;
}

async function doPrint(what) {
  if (printing) return;   // 이미 보낸 것을 기다리는 중 — 두 번 하지 않는다
  if (!getToken()) {
    printMsg('토큰이 없습니다 — [진단] → PC 전송에서 넣으세요', 'no');
    beep('error');
    return;
  }

  printing = true;
  printMsg('PC로 보내는 중…');
  let id;
  try {
    id = await sync.requestPrint(what);
  } catch (err) {
    printing = false;
    printMsg(`보내지 못했습니다: ${err.message} — 다시 누르세요`, 'no');
    beep('error');
    return;
  }
  printMsg(what === 'excel'
    ? 'PC가 엑셀에 넣는 중… (파일이 커서 1~2분 걸립니다)'
    : 'PC가 인쇄하기를 기다리는 중…');

  const until = Date.now() + WAIT_MS[what];
  while (Date.now() < until) {
    await new Promise((r) => setTimeout(r, 3000));
    let st = null;
    try { st = await sync.readStatus(); } catch (_) { continue; }   // 전파가 잠깐 끊겨도 계속 기다린다
    if (!st || st.id !== id) continue;
    printing = false;
    if (st.state === 'done') {
      printMsg(`${what === 'excel' ? '엑셀에 넣었습니다' : '인쇄했습니다'} — ${st.msg}`, 'ok');
      beep('done');
    } else {
      printMsg(`PC가 하지 못했습니다: ${st.msg}`, 'no');
      beep('error');
    }
    return;
  }
  printing = false;
  printMsg('PC 응답이 없습니다 — PC의 sctc-copy 가 켜져 있는지 확인하세요. '
    + '10분 안에 켜지면 그때 처리됩니다.', 'no');
  beep('warn');
}

// ---------------------------------------------------------------- 시작

function init() {
  $('yardName').textContent = YARD.name.replace(/\s*\(.*\)/, '');
  document.body.classList.toggle('yard-old', OLD_YARD);
  if (OLD_YARD) $('hudUnit').textContent = spotZone(cursor);
  renderRound();

  buildMap($('map'), 'live');
  setupZoom();
  repaintAll();
  renderHud();
  renderTargetBadge();
  if (countFilled(session) > 0) note(`이어서 ${spotName(cursor)}번부터 입력합니다`);

  $('btnRound').addEventListener('click', () => {
    primeAudio();
    switchRound(round === 1 ? 2 : 1);
  });
  $('btnMic').addEventListener('click', toggleMic);
  $('btnBack').addEventListener('click', () => { primeAudio(); goBack(); });
  $('btnVacant').addEventListener('click', () => { primeAudio(); markVacant(); });
  $('btnNext').addEventListener('click', () => { primeAudio(); goNext(); });
  $('btnPad').addEventListener('click', () => openPad(cursor));
  $('btnPrint').addEventListener('click', openPrint);
  $('printPaper').addEventListener('click', () => doPrint('paper'));
  $('printExcel').addEventListener('click', () => doPrint('excel'));
  $('btnDiag').addEventListener('click', openDiag);
  $('yardName').addEventListener('click', () => {
    // 차고지를 바꾸면 판·커서·배치도가 전부 그 차고지 것으로 바뀐다.
    // 반쯤 갈아 끼우다 어긋나지 않게 화면을 처음부터 다시 세운다.
    localStorage.setItem('busyard:yard', OLD_YARD ? 'new' : 'old');
    location.reload();
  });

  // ---- 차량번호 찾기 ----
  let findDigits = '';
  const renderFind = () => {
    document.querySelectorAll('#findDisplay .slot').forEach((el, i) => {
      el.textContent = findDigits[i] || '_';
      el.classList.toggle('set', Boolean(findDigits[i]));
    });
    const box = $('findResults');
    if (!findDigits) {
      box.innerHTML = '<div class="find-none">숫자를 누르면 찾습니다</div>';
      return;
    }
    const hits = findSpots(findDigits);
    box.innerHTML = hits.length
      ? hits.map((h) => `<button class="find-hit" data-spot="${h.spot}"><b>${h.plate}</b><span>${spotName(h.spot)}번 자리</span></button>`).join('')
      : '<div class="find-none">입력된 차량 중에 없습니다</div>';
  };
  $('btnFind').addEventListener('click', () => {
    primeAudio();
    if (voice && voice.isOn()) voice.stop();
    findDigits = ''; renderFind();
    $('findSheet').hidden = false;
  });
  $('findClose').addEventListener('click', () => { $('findSheet').hidden = true; });
  $('findKeys').addEventListener('click', (ev) => {
    const k = ev.target.dataset.k;
    if (!k) return;
    if (k === 'clear') findDigits = '';
    else if (k === 'del') findDigits = findDigits.slice(0, -1);
    else if (findDigits.length < 3) findDigits += k;
    renderFind();
  });
  $('findResults').addEventListener('click', (ev) => {
    const btn = ev.target.closest('.find-hit');
    if (!btn) return;
    const n = Number(btn.dataset.spot);
    $('findSheet').hidden = true;
    highlightSpot(n);
    note(`${spotName(n)}번 자리 — ${session.entries[n].plate}`);
  });

  // ---- 일지 보관 ----
  $('btnLog').addEventListener('click', () => {
    primeAudio();
    $('logSaveNote').textContent = '';
    renderLogList();
    $('logSheet').hidden = false;
  });
  $('logClose').addEventListener('click', () => { $('logSheet').hidden = true; });
  $('logSave').addEventListener('click', doSaveLog);

  // 불러오기는 지금 입력을 덮어쓰므로 한 번 더 묻는다
  let loadArmed = null;
  $('logList').addEventListener('click', (ev) => {
    const del = ev.target.dataset.del;
    if (del) {
      deleteLog(del);
      renderLogList();
      return;
    }
    const date = ev.target.dataset.date;
    if (!date) return;
    if (loadArmed !== date) {
      renderLogList();
      loadArmed = date;
      const btn = $('logList').querySelector(`[data-date="${date}"]`);
      btn.textContent = '덮어씁니다. 한 번 더';
      btn.classList.add('armed');
      setTimeout(() => { if (loadArmed === date) { loadArmed = null; renderLogList(); } }, 4000);
      return;
    }
    loadArmed = null;
    doLoadLog(date);
  });

  // ---- 찾을 차량 ----
  let targetKindPick = 'cctv';
  $('kindPick').addEventListener('click', (ev) => {
    const btn = ev.target.closest('button');
    if (!btn) return;
    targetKindPick = btn.dataset.kind;
    $('kindPick').querySelectorAll('button').forEach((b) =>
      b.classList.toggle('on', b.dataset.kind === targetKindPick));
  });

  let targetDigits = '';
  const renderTargetPad = () => {
    document.querySelectorAll('#targetDisplay .slot').forEach((el, i) => {
      el.textContent = targetDigits[i] || '_';
      el.classList.toggle('set', Boolean(targetDigits[i]));
    });
  };
  $('btnTargets').addEventListener('click', () => {
    primeAudio();
    targetDigits = ''; renderTargetPad(); renderTargetList();
    $('targetSheet').hidden = false;
  });
  $('targetClose').addEventListener('click', () => { $('targetSheet').hidden = true; });
  $('targetKeys').addEventListener('click', (ev) => {
    const k = ev.target.dataset.k;
    if (!k) return;
    if (k === 'clear') { targetDigits = ''; renderTargetPad(); beep('back'); return; }
    if (k === 'del') { targetDigits = targetDigits.slice(0, -1); renderTargetPad(); beep('back'); return; }
    if (targetDigits.length >= 3) return;
    targetDigits += k;
    renderTargetPad();
    if (keyTtsOn) speakDigit(k, rate.digit);   // 여기서도 무엇을 눌렀는지 귀로 확인
    if (targetDigits.length === 3) {
      const plate = '1' + targetDigits;
      if (targets.length >= MAX_TARGETS) {
        note(`찾을 차량은 ${MAX_TARGETS}대까지입니다`, 'warn');
        beep('error');
      } else if (targets.some((t) => t.plate === plate)) {
        beep('warn');
      } else {
        targets.push({ plate, kind: targetKindPick });
        saveTargets();
        repaintAll();
        beep('ok');
      }
      targetDigits = ''; renderTargetPad(); renderTargetList();
    }
  });
  $('targetList').addEventListener('click', (ev) => {
    const plate = ev.target.dataset.plate;
    if (!plate) return;
    targets = targets.filter((t) => t.plate !== plate);
    saveTargets();
    renderTargetList();
    repaintAll();
  });

  $('printClose').addEventListener('click', () => { $('printSheet').hidden = true; });

  $('padClose').addEventListener('click', closePad);
  // 찾기·대상 시트도 같은 .pad-keys 를 쓰므로 반드시 이 시트 안으로 한정한다
  // click 은 손을 뗄 때 오고, 빨리 연달아 치면 사파리가 두 번 톡으로 묶어 삼키기도 한다.
  // 닿는 순간 받아야 한 자리도 빠지지 않는다.
  document.querySelectorAll('#padSheet .pad-keys button').forEach((b) =>
    b.addEventListener('pointerdown', (ev) => { ev.preventDefault(); padKey(b.dataset.k); }));

  $('spotClose').addEventListener('click', () => { $('spotSheet').hidden = true; });
  $('spotGoto').addEventListener('click', () => {
    cursor = sheetSpot; repaintAll(); renderHud();
    $('spotSheet').hidden = true;
    if (voice) voice.reset();
    note(`${spotName(cursor)}번 자리부터 입력합니다`);
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
    targets = [];              // 찾을 차량도 함께 비운다 — "전부"는 전부여야 한다
    saveTargets();
    cursor = 1;
    repaintAll();
    renderHud();
    $('diagClear').textContent = '오늘 입력·대상 전부 지우기';
    $('diagClear').classList.remove('armed');
    $('diagSheet').hidden = true;
    note(`입력과 찾을 차량을 전부 지웠습니다. ${spotName(1)}번 자리부터 시작합니다.`);
    beep('back');
  });
  $('diagBody').addEventListener('click', (ev) => {
    const row = ev.target.closest('.diag-row');
    if (!row || !row.dataset.act) return;
    primeAudio();

    // 속도는 바꾸는 즉시 그 속도로 들려준다 — 귀로 고르는 것이 빠르다
    if (row.dataset.act === 'tts') {
      ttsOn = !ttsOn;
      localStorage.setItem('busyard:tts', ttsOn ? '1' : '0');
      openDiag();
      if (ttsOn) speak('다음 자리를 읽어 드립니다', { rate: rate.say });
    } else if (row.dataset.act === 'padtts') {
      padTtsOn = !padTtsOn;
      localStorage.setItem('busyard:padtts', padTtsOn ? '1' : '0');
      openDiag();
      if (padTtsOn) speak(toKoreanSino('1734'), { rate: rate.read });
    } else if (row.dataset.act === 'keytts') {
      keyTtsOn = !keyTtsOn;
      localStorage.setItem('busyard:keytts', keyTtsOn ? '1' : '0');
      openDiag();
      if (keyTtsOn) speakDigit('7', rate.digit);
    } else if (row.dataset.act === 'sayrate') {
      openDiagAfter(() => speak(toKoreanSino('1734'), { rate: cycleRate('say') }));
    } else if (row.dataset.act === 'digitrate') {
      openDiagAfter(() => speakDigit('7', cycleRate('digit')));
    } else if (row.dataset.act === 'readrate') {
      openDiagAfter(() => speak(toKoreanSino('1734'), { rate: cycleRate('read') }));
    } else if (row.dataset.act === 'settle') {
      settleIdx = (settleIdx + 1) % SETTLE.length;
      localStorage.setItem('busyard:settlems', String(SETTLE[settleIdx].ms));
      if (voice) voice.setSettle(SETTLE[settleIdx].ms);
      openDiag();
    } else if (row.dataset.act === 'sync') {
      if (!getToken() || (syncState.detail || '').includes('토큰')) {
        const t = prompt('GitHub 토큰을 붙여 넣으세요 (PC 인쇄용 판 올리기)', '');
        if (t === null) return;
        setToken(t);
      }
      syncState = { state: 'idle' };
      openDiag();
      sync.flush();
    }
  });

  // 주머니에 넣느라 화면이 꺼지면 30초를 기다리지 않고 바로 올린다
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && sync.pending()) sync.flush();
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
