// 진입 안내 — 화면 조립
//
// 세 자리를 누르면 바로 자리가 정해지고 숫자가 화면을 꽉 채운다.
// 화면을 다시 누르면 키패드로 돌아온다. 확정 버튼은 없다.

import { assign, place, clear, laneOf, computeCutoff, DEFAULT_CUTOFF } from './assign.js?v=202609270058';
import { YARD12 } from './yard12-data.js?v=202609270058';
import { load, save, rows, toCsv, saveLog, listLogs, readLog, deleteLog }
  from './session.js?v=202609270058';
import { sourceDate, fetchSource } from './source.js?v=202609270058';
import { toKoreanSino } from '../plate.js?v=202609270058';
import { speak, beep, primeAudio } from '../voice.js?v=202609270058';
import { BUILD } from '../build.js?v=202609090547';

const Y1 = YARD12.yard1;
const Y2 = YARD12.yard2;
const $ = (id) => document.getElementById(id);

/** 순회할 때 도는 차례 — 종이에 그려진 순서(위 → 아래, 왼쪽 → 오른쪽).
 *  3차고지·한노도 들어 있다. 출근해서 한 바퀴 돌 때 같이 적으신다. */
const ALL_SPOTS = YARD12.print.cells
  .filter((c) => c.kind === 'spot')
  .map((c) => c.spot);

let S = load();
let typed = [];
let round = false;          // 순회 입력 모드
let cursor = null;          // 순회 커서
let last = null;            // 방금 넣은 자리 — 배치도에서 파랗게 짚어 준다
let pickAt = null;          // 배치도에서 자리를 먼저 고른 경우

// ---- 상태바 ------------------------------------------------------------
function renderBar() {
  const n1 = Object.keys(S.entries).filter((s) => s[0] === '1').length;
  const n2 = Object.keys(S.entries).filter((s) => s[0] === '2').length;
  const cars = S.cars ? Object.keys(S.cars).length : 0;
  $('barDate').textContent = cars ? `${S.sourceDate} 자료 ${cars}대` : '소스 없음';
  $('barCount').textContent = `1차 ${n1} · 2차 ${n2}`;
  $('btnRound').classList.toggle('on', round);
}

// ---- 입력 표시 ---------------------------------------------------------
function renderEntry() {
  const slots = $('slots').querySelectorAll('i');
  slots.forEach((el, i) => {
    el.textContent = typed[i] === undefined ? '_' : typed[i];
    el.classList.toggle('on', typed[i] !== undefined);
  });
  const target = pickAt || (round ? cursor : null);
  $('btnCarPark').disabled = !target;
  $('hint').innerHTML =
    pickAt ? `<b>${pickAt}</b> 에 넣습니다`
    : round ? `순회 · 다음 자리 <b>${cursor || '없음'}</b>`
    : '세 자리를 누르면 자리가 정해집니다';
}

// ---- 전체화면 숫자 -----------------------------------------------------
// 글자를 화면에 꽉 채운다. 서체나 기종이 바뀌어도 저절로 맞는다.
//
// `getBBox()` 는 글자 둘레의 여백까지 포함한 상자를 준다 — 그걸로 맞추면
// 위아래가 비고, 폭이 좁은 `1` 도 `2` 와 같은 크기로 그려진다.
// 캔버스로 획이 실제로 닿는 범위를 재서 그 범위를 화면에 맞춘다.
const FONT_FAMILY = '-apple-system, "Helvetica Neue", Arial, sans-serif';
const FONT_WEIGHT = 900;
const FONT_UNIT = 100;

function inkBox(ch) {
  const ctx = inkBox.ctx || (inkBox.ctx = document.createElement('canvas').getContext('2d'));
  ctx.font = `${FONT_WEIGHT} ${FONT_UNIT}px ${FONT_FAMILY}`;
  const m = ctx.measureText(ch);
  if (m.actualBoundingBoxAscent === undefined) return null;   // 아주 옛 브라우저
  return {
    x: -m.actualBoundingBoxLeft,
    y: -m.actualBoundingBoxAscent,
    w: m.actualBoundingBoxLeft + m.actualBoundingBoxRight,
    h: m.actualBoundingBoxAscent + m.actualBoundingBoxDescent,
  };
}

function showBig(lane, tag) {
  const ch = String(lane);
  const t = $('bigText');
  t.textContent = ch;
  $('bigTag').textContent = tag;
  $('big').hidden = false;
  const b = inkBox(ch) || { x: -50, y: -75, w: 100, h: 100 };
  $('bigSvg').setAttribute('viewBox', `${b.x} ${b.y} ${b.w} ${b.h}`);
}
function hideBig() {
  $('big').hidden = true;
  show('Map');            // 배치도가 메인이다. 넣고 나면 늘 여기로 돌아온다
}

// ---- 시트 --------------------------------------------------------------
function sheet(title, body, buttons) {
  $('sheetTitle').textContent = title;
  $('sheetBody').textContent = body;
  const box = $('sheetBtns');
  box.innerHTML = '';
  for (const [label, cls, fn] of buttons) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = label;
    if (cls) b.className = cls;
    b.onclick = () => { $('sheet').hidden = true; fn && fn(); };
    box.append(b);
  }
  $('sheet').hidden = false;
}

// ---- 한 대 넣기 --------------------------------------------------------
function commit(plate) {
  const known = (S.cars || {})[plate];
  // 소스가 있으면 알아서 채운다. `휴차` 키를 눌렀으면 그쪽이 이긴다.
  const car = known
    ? { plate, rest: known.rest, out: known.out, band: known.band }
    : { plate, rest: false, out: null };

  if (round) return putRound(car);
  if (pickAt) return putAt(car, pickAt, '수동 지정');

  const r = assign(S.entries, car, { cutoff: S.cutoff || DEFAULT_CUTOFF });

  if (r.ok) return putAt(car, r.spot, r.reason);

  if (r.kind === 'move') {
    const where = S.entries[r.from] ? r.from : '어딘가';
    if (r.from === r.spot) {
      return sheet(`${plate}`, `이미 ${r.from} 에 있습니다.`, [['확인', 'go', null]]);
    }
    return sheet(`${plate} 는 ${where} 에 있습니다`, `${r.spot} 로 옮길까요?`, [
      [`${r.spot} 로 옮기기`, 'go', () => putAt(car, r.spot, r.reason, r.from)],
      ['그대로 두기', '', null],
    ]);
  }

  beep('warn');
  sheet(`${plate} — 자리가 없습니다`, `${r.yard}차고지가 다 찼습니다. 배치도에서 직접 고르세요.`, [
    ['배치도 열기', 'go', () => show('Map')],
    ['취소', 'warn', null],
  ]);
}

function putAt(car, spot, reason, from = null) {
  S.entries = place(S.entries, car, spot, { from });
  S.entries[spot].reason = reason;
  if (car.band) S.entries[spot].band = car.band;
  save(S);
  last = spot;
  pickAt = null;
  typed = [];
  const lane = laneOf(spot);
  const tail = car.rest ? '휴차' : (car.band || car.out || '');
  if (lane) {
    showBig(lane, `${car.plate} · ${spot}${tail ? ' · ' + tail : ''}`);
    if (S.voice) speak(`${toKoreanSino(car.plate)}, ${lane}열`);
  } else {
    beep('ok');           // 3·4차고지는 안내 대상이 아니다. 적어만 둔다
    show('Map');
  }
  renderBar(); renderEntry(); renderMap(); renderLog();
}

/** 순회 입력 — 커서 자리에 넣고 다음 빈 자리로 */
function putRound(car) {
  if (!cursor) { beep('warn'); return; }
  S.entries = place(S.entries, car, cursor);
  S.entries[cursor].reason = '순회';
  save(S);
  last = cursor;
  beep('ok');
  typed = [];
  nextCursor();
  renderBar(); renderEntry(); renderMap(); renderLog();
}

function nextCursor(from = cursor) {
  const i = ALL_SPOTS.indexOf(from);
  cursor = ALL_SPOTS.slice(i + 1).find((s) => !S.entries[s])
        || ALL_SPOTS.find((s) => !S.entries[s]) || null;
}

// ---- 키패드 ------------------------------------------------------------
function key(k) {
  primeAudio();
  if (k === 'del') { typed.pop(); return renderEntry(); }
  if (typed.length >= 3) return;
  typed.push(k);
  renderEntry();
  if (typed.length === 3) commit(Number('1' + typed.join('')));
}

// ---- 배치도 — 사무실에서 내다보는 그대로 -------------------------------
// 엑셀에서 읽어 둔 격자를 그대로 쓴다. 위에서부터 3열·2열·1열이고
// 한 줄은 가로로 한 줄이다. 1차고지는 왼쪽부터, 2차고지는 오른쪽부터 찬다.

function cellEl(c) {
  const spot = c.spot;
  const e = S.entries[spot];
  const d = document.createElement('div');
  d.className = 'mc'
    + (e ? (e.car ? ' car' : (e.rest ? ' rest' : ' fill')) : '')
    + (Y1.reserved[e && e.plate] === spot ? ' own' : '')
    + (spot === cursor && round ? ' cursor' : '')
    + (spot === last ? ' just' : '');
  d.style.gridColumn = `${c.col} / span ${c.colspan}`;
  d.style.gridRow = `${c.row} / span ${c.rowspan}`;
  d.innerHTML = `<span class="n">${spot}</span>`
    + (e ? `<span class="p">${e.car ? '승용차' : e.plate}</span>` : '');
  d.onclick = () => tapCell(spot);
  return d;
}

function renderMap() {
  const board = $('board');
  board.innerHTML = '';
  board.style.gridTemplateRows = `repeat(${YARD12.print.rows}, minmax(0, 1fr))`;
  for (const c of YARD12.print.cells) {
    if (c.kind === 'spot') { board.append(cellEl(c)); continue; }
    if (c.kind !== 'label') continue;
    const d = document.createElement('div');
    d.className = 'mlab';
    d.style.gridColumn = `${c.col} / span ${Math.max(c.colspan, 3)}`;
    d.style.gridRow = `${c.row} / span ${c.rowspan}`;
    d.textContent = c.text;
    board.append(d);
  }
}

function tapCell(spot) {
  const e = S.entries[spot];
  if (round) { cursor = spot; show('Pad'); renderMap(); renderEntry(); return; }
  if (e) {
    return sheet(`${spot} · ${e.car ? '승용차' : e.plate}`,
      e.car ? '버스 자리에 선 승용차' : (e.rest ? '휴차' : (e.band || e.out || '')), [
      ['비우기', 'warn', () => {
        S.entries = clear(S.entries, spot);
        if (last === spot) last = null;
        save(S); renderBar(); renderMap(); renderLog();
      }],
      ['닫기', '', null],
    ]);
  }
  // 빈 자리는 묻지 않는다. 바로 그 자리에 넣을 번호를 받는다.
  pickAt = spot;
  show('Pad');
  renderEntry();
}

// ---- 배치도 확대 -------------------------------------------------------
// 두 손가락으로 벌리면 커진다. 커진 만큼 스크롤이 따라오므로 가운데 칸도 짚을 수 있다.

let zoom = 1;
let baseW = 0, baseH = 0;
const ZOOM_MAX = 5;

/** 배치도가 화면을 위아래·좌우로 꽉 채우게 한다 */
function fitBoard() {
  const m = $('map');
  if (!m.clientWidth) return;
  baseW = m.clientWidth - 12;
  baseH = Math.max(m.clientHeight - 12, 300);
  $('board').style.width = `${baseW}px`;
  $('board').style.height = `${baseH}px`;
  applyZoom(zoom);
}

function applyZoom(next) {
  zoom = Math.min(ZOOM_MAX, Math.max(1, next));
  $('board').style.transform = `scale(${zoom})`;
  // 늘어난 만큼 스크롤할 자리를 만들어 준다 (transform 은 크기를 안 바꾼다)
  $('zoomWrap').style.width = `${baseW * zoom}px`;
  $('zoomWrap').style.height = `${baseH * zoom}px`;
}

(function setupZoom() {
  const m = $('map');
  let start = 0, base = 1, cx = 0, cy = 0;
  const dist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);

  m.addEventListener('touchstart', (ev) => {
    if (ev.touches.length !== 2) return;
    start = dist(ev.touches);
    base = zoom;
    const r = m.getBoundingClientRect();
    cx = (ev.touches[0].clientX + ev.touches[1].clientX) / 2 - r.left + m.scrollLeft;
    cy = (ev.touches[0].clientY + ev.touches[1].clientY) / 2 - r.top + m.scrollTop;
  }, { passive: true });

  m.addEventListener('touchmove', (ev) => {
    if (ev.touches.length !== 2 || !start) return;
    ev.preventDefault();
    const before = zoom;
    applyZoom(base * (dist(ev.touches) / start));
    const k = zoom / before;
    m.scrollLeft = cx * k - (cx - m.scrollLeft);
    m.scrollTop = cy * k - (cy - m.scrollTop);
  }, { passive: false });

  m.addEventListener('touchend', (ev) => { if (ev.touches.length < 2) start = 0; }, { passive: true });
})();

// ---- 기록 --------------------------------------------------------------
function renderLog() {
  const box = $('log');
  box.innerHTML = '';
  for (const r of rows(S.entries)) {
    const d = document.createElement('div');
    d.className = 'lrow';
    d.innerHTML = `<span class="s">${r.spot}</span><span class="v">${r.car ? '승용차' : r.plate}</span>`
      + `<span class="o">${r.car ? '' : (r.rest ? '휴차' : (r.band || r.out || ''))}</span>`
      + `<span class="w">${r.reason || ''}</span>`;
    d.onclick = () => tapCell(r.spot);
    box.append(d);
  }
}

// ---- 인쇄 --------------------------------------------------------------
// 엑셀에서 읽어 둔 병합·색·테두리를 그대로 입혀 종이와 같은 모양으로 그린다.
// 안 넣은 칸은 빈 칸이라 3·4차고지는 지금처럼 볼펜으로 적으면 된다.

const EDGE = [0, '.2pt', '.5pt', '1.2pt'];   // 엑셀 테두리 굵기 → 인쇄 선 굵기

function renderPaper() {
  const P = YARD12.print;
  const map = $('pMap');
  map.innerHTML = '';
  for (const c of P.cells) {
    const d = document.createElement('div');
    d.className = 'pc' + (c.kind === 'void' ? ' void' : '');
    d.style.gridColumn = `${c.col} / span ${c.colspan}`;
    d.style.gridRow = `${c.row} / span ${c.rowspan}`;
    if (c.bg) d.style.background = c.bg;
    if (c.b) {
      const [t, r, b, l] = c.b;
      d.style.borderTop = t ? `${EDGE[t]} solid #666` : '0';
      d.style.borderRight = r ? `${EDGE[r]} solid #666` : '0';
      d.style.borderBottom = b ? `${EDGE[b]} solid #666` : '0';
      d.style.borderLeft = l ? `${EDGE[l]} solid #666` : '0';
    }
    if (c.kind === 'label') {
      d.innerHTML = `<span class="lab">${c.text}</span>`;
    } else if (c.kind === 'spot') {
      const e = S.entries[c.spot];
      if (e) d.innerHTML = `<span class="plate">${e.plate}</span>`;
    }
    map.append(d);
  }
  const n1 = Object.keys(S.entries).filter((s) => s[0] === '1').length;
  const n2 = Object.keys(S.entries).filter((s) => s[0] === '2').length;
  $('pMeta').textContent =
    `${S.date} 근무 · ${S.sourceDate || '소스 없음'} 자료 · 컷오프 ${S.cutoff || DEFAULT_CUTOFF}`
    + ` · 1차고지 ${n1} · 2차고지 ${n2}`;
}

// ---- 관리 --------------------------------------------------------------
// 새 버전을 못 받는 일이 제일 곤란하다. 순회 앱과 같은 방법으로,
// 서비스 워커와 캐시를 지우고 주소에 표를 붙여 확실히 다시 받게 한다.

async function forceUpdate() {
  const b = $('btnUpdate');
  b.textContent = '받는 중…';
  b.disabled = true;
  try {
    if ('serviceWorker' in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.unregister()));
    }
    if (window.caches) {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    }
  } catch (_) { /* 못 지워도 아래 재요청은 해본다 */ }
  const url = new URL(location.href);
  url.searchParams.set('v', Date.now().toString(36));
  location.replace(url.toString());
}

function renderAdmin() {
  const cars = S.cars ? Object.keys(S.cars).length : 0;
  $('admBuild').textContent = BUILD;
  $('admSource').textContent = cars ? `${S.sourceDate} · ${cars}대` : '아직 안 올라옴';
  $('admCutoff').textContent = S.cutoff || DEFAULT_CUTOFF;
  $('btnVoice2').textContent = S.voice ? '안내 음성 — 켜짐' : '안내 음성 — 꺼짐';
}

// ---- 보관 --------------------------------------------------------------
function renderSaves() {
  const box = $('saves');
  box.innerHTML = '';
  for (const r of listLogs()) {
    const d = document.createElement('div');
    d.className = 'srow';
    d.innerHTML = `<span class="d">${r.date}</span><span class="c">${r.count}대</span>`;
    const open = document.createElement('button');
    open.type = 'button';
    open.textContent = '불러오기';
    open.onclick = () => {
      const rec = readLog(r.date);
      if (!rec) return;
      S.entries = rec.entries;
      last = null;
      save(S);
      renderBar(); renderMap(); renderLog(); renderAdmin();
      show('Map');
    };
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'del';
    del.textContent = '지움';
    del.onclick = () => { deleteLog(r.date); renderSaves(); };
    d.append(open, del);
    box.append(d);
  }
  if (!box.children.length) {
    box.innerHTML = '<p class="ahint">아직 저장한 날이 없다.</p>';
  }
}

// ---- 화면 전환 ---------------------------------------------------------
function show(name) {
  for (const v of ['Pad', 'Map', 'Log', 'Admin']) $('view' + v).hidden = v !== name;
  if (name === 'Admin') { renderAdmin(); renderSaves(); }
  if (name === 'Map') fitBoard();
  document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('on', b.dataset.v === name));
}

// ---- 붙이기 ------------------------------------------------------------
$('pad').addEventListener('click', (ev) => {
  const k = ev.target.closest('button') && ev.target.closest('button').dataset.k;
  if (k) key(k);
});
$('btnClearKey').onclick = () => { typed = []; renderEntry(); };

// 기사님이 버스 자리에 승용차를 대 놓는 일이 있다. 그 칸은 비워 두고 지나가야 한다.
$('btnCarPark').onclick = () => {
  const spot = pickAt || (round ? cursor : null);
  if (!spot) return beep('warn');
  S.entries = { ...S.entries, [spot]: { plate: null, car: true, rest: false, out: null, reason: '승용차' } };
  save(S);
  last = spot;
  typed = [];
  pickAt = null;
  if (round) nextCursor(spot); else show('Map');
  beep('ok');
  renderBar(); renderEntry(); renderMap(); renderLog();
};
$('btnRound').onclick = () => {
  round = !round;
  if (round && !cursor) nextCursor('1-0');
  show(round ? 'Pad' : 'Map');
  renderBar(); renderEntry(); renderMap();
};
$('big').onclick = hideBig;
$('tabs').addEventListener('click', (ev) => {
  const b = ev.target.closest('button');
  if (b) show(b.dataset.v);
});
$('btnCsv').onclick = async () => {
  const text = toCsv(S.entries);
  try {
    await navigator.clipboard.writeText(text);
    sheet('복사했습니다', '엑셀에 붙여넣으세요.', [['확인', 'go', null]]);
  } catch (_) {
    sheet('복사가 막혔습니다', text, [['확인', 'go', null]]);
  }
};
// 인쇄는 사무실 PC 가 원본 엑셀에 적어서 기본 프린터로 뽑는 것이 제일 정확하다.
// 폰에서는 그 내용을 복사해 PC 로 보낸다 (PC 에서 인쇄.bat 실행).
$('btnPrint').onclick = () => sheet('인쇄', 'PC 에서 인쇄.bat 을 실행하면 구차고지 엑셀 그대로 나온다.', [
  ['PC 로 보낼 내용 복사', 'go', async () => {
    try { await navigator.clipboard.writeText(toCsv(S.entries)); beep('ok'); }
    catch (_) { sheet('복사가 막혔습니다', toCsv(S.entries), [['확인', 'go', null]]); }
  }],
  ['폰에서 바로 인쇄', '', () => { renderPaper(); window.print(); }],
  ['닫기', '', null],
]);
$('btnUpdate').onclick = forceUpdate;
$('btnSave').onclick = () => {
  saveLog(S);
  renderSaves();
  $('btnSave').textContent = '저장했습니다';
  setTimeout(() => { $('btnSave').textContent = '오늘 판 저장'; }, 2000);
};
$('btnVoice2').onclick = () => { S.voice = !S.voice; save(S); renderBar(); renderAdmin(); };
$('btnReload').onclick = async () => {
  const b = $('btnReload');
  b.textContent = '받는 중…';
  const ok = await loadSource();
  b.textContent = ok ? '그날 자료 다시 받기' : '아직 안 올라왔습니다';
  renderAdmin();
};
let wipeArmed = false;
$('btnWipe').onclick = () => {
  if (!wipeArmed) {
    wipeArmed = true;
    $('btnWipe').textContent = '정말 지웁니다 — 한 번 더';
    setTimeout(() => { wipeArmed = false; $('btnWipe').textContent = '오늘 입력 전부 지우기'; }, 4000);
    return;
  }
  wipeArmed = false;
  $('btnWipe').textContent = '오늘 입력 전부 지우기';
  S.entries = {};
  last = null;
  cursor = ALL_SPOTS[0];
  save(S);
  renderBar(); renderEntry(); renderMap(); renderLog(); renderAdmin();
};
$('sheet').onclick = (ev) => { if (ev.target === $('sheet')) $('sheet').hidden = true; };

// 순회 커서는 첫 빈 자리에서 시작한다
cursor = ALL_SPOTS.find((s) => !S.entries[s]) || null;
renderBar(); renderEntry(); renderMap(); renderLog();
fitBoard();
window.addEventListener('resize', fitBoard);

// 소스는 켤 때 한 번 받아서 폰에 남긴다. 못 받아도 수동으로 그대로 쓴다.
async function loadSource() {
  const date = sourceDate(S.date);
  const src = await fetchSource(date);
  if (!src) return false;
  S.cars = src.cars;
  S.sourceDate = date;
  S.cutoff = computeCutoff(
    Object.entries(src.cars).map(([plate, c]) => ({ plate: Number(plate), ...c })));
  save(S);
  renderBar();
  return true;
}
loadSource();

if ('serviceWorker' in navigator) navigator.serviceWorker.register('../sw.js').catch(() => {});
