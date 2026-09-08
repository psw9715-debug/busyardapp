// 진입 안내 — 화면 조립
//
// 세 자리를 누르면 바로 자리가 정해지고 숫자가 화면을 꽉 채운다.
// 화면을 다시 누르면 키패드로 돌아온다. 확정 버튼은 없다.

import { assign, place, clear, laneOf, computeCutoff, DEFAULT_CUTOFF } from './assign.js?v=202609090547';
import { YARD12 } from './yard12-data.js?v=202609090547';
import { load, save, rows, toCsv, COLORS } from './session.js?v=202609090547';
import { sourceDate, fetchSource } from './source.js?v=202609090547';
import { toKoreanSino } from '../plate.js?v=202609090547';
import { speak, beep, primeAudio } from '../voice.js?v=202609090547';

const Y1 = YARD12.yard1;
const Y2 = YARD12.yard2;
const $ = (id) => document.getElementById(id);

/** 순회할 때 도는 차례 — 자리번호 순 */
const ALL_SPOTS = [
  ...Y1.seq, ...Y1.rear,
  ...Y2.lanes[1], ...Y2.lanes[2], ...Y2.lanes[3], Y2.spare[2], Y2.spare[3],
];

let S = load();
let typed = [];
let restOn = false;
let round = false;          // 순회 입력 모드
let cursor = null;          // 순회 커서
let last = null;            // 직전에 넣은 자리 (직전 취소용)
let pickAt = null;          // 배치도에서 자리를 먼저 고른 경우

// ---- 상태바 ------------------------------------------------------------
function renderBar() {
  const n1 = Object.keys(S.entries).filter((s) => s[0] === '1').length;
  const n2 = Object.keys(S.entries).filter((s) => s[0] === '2').length;
  const cars = S.cars ? Object.keys(S.cars).length : 0;
  $('barDate').textContent = cars ? `${S.sourceDate} 자료 ${cars}대` : '소스 없음';
  $('barCount').textContent = `1차 ${n1} · 2차 ${n2}`;
  $('btnRound').classList.toggle('on', round);
  $('btnVoice').classList.toggle('on', S.voice);
}

// ---- 입력 표시 ---------------------------------------------------------
function renderEntry() {
  const slots = $('slots').querySelectorAll('i');
  slots.forEach((el, i) => {
    el.textContent = typed[i] === undefined ? '_' : typed[i];
    el.classList.toggle('on', typed[i] !== undefined);
  });
  $('btnRest').classList.toggle('on', restOn);
  $('btnSkip').disabled = !round;
  $('hint').innerHTML =
    pickAt ? `<b>${pickAt}</b> 에 넣습니다`
    : round ? `순회 · 다음 자리 <b>${cursor || '없음'}</b>`
    : restOn ? '<b>휴차</b> 로 넣습니다'
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
  $('big').className = S.color;
  $('big').hidden = false;
  const b = inkBox(ch) || { x: -50, y: -75, w: 100, h: 100 };
  $('bigSvg').setAttribute('viewBox', `${b.x} ${b.y} ${b.w} ${b.h}`);
}
function hideBig() {
  $('big').hidden = true;
  save(S);                       // 그 색에서 나갔으면 그 색을 고른 것이다
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
  // 소스가 있으면 휴차·출차시각을 알아서 채운다. `휴차` 키를 눌렀으면 그쪽이 이긴다.
  const car = known
    ? { plate, rest: restOn || known.rest, out: restOn ? null : known.out }
    : { plate, rest: restOn, out: null };

  if (round) return putRound(car);
  if (pickAt) return putAt(car, pickAt, '수동 지정');

  const r = assign(S.entries, car, { cutoff: S.cutoff || DEFAULT_CUTOFF });

  if (r.ok) return putAt(car, r.spot, r.reason);

  if (r.kind === 'need-time') {
    return sheet(`${plate} — 2차고지`, '몇 시에 나가는 차인가요?', [
      ['5시대 — 빠른 차', 'go', () => retry({ ...car, out: '05:00' })],
      ['6시 15분 이후 — 늦은 차', '', () => retry({ ...car, out: '07:00' })],
      ['휴차', '', () => retry({ ...car, rest: true })],
      ['취소', 'warn', null],
    ]);
  }

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

function retry(car) {
  const r = assign(S.entries, car, { cutoff: S.cutoff || DEFAULT_CUTOFF });
  if (r.ok) return putAt(car, r.spot, r.reason);
  beep('warn');
  sheet('자리가 없습니다', '배치도에서 직접 고르세요.', [['배치도 열기', 'go', () => show('Map')]]);
}

function putAt(car, spot, reason, from = null) {
  S.entries = place(S.entries, car, spot, { from });
  S.entries[spot].reason = reason;
  save(S);
  last = spot;
  pickAt = null;
  restOn = false;
  typed = [];
  const lane = laneOf(spot);
  const tail = car.rest ? '휴차' : (car.out || '');
  showBig(lane, `${car.plate} · ${spot}${tail ? ' · ' + tail : ''}`);
  if (S.voice) speak(`${toKoreanSino(car.plate)}, ${lane}열`);
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
  restOn = false;
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

// ---- 배치도 ------------------------------------------------------------
const chunk = (list, n) => list.reduce(
  (acc, v, i) => (i % n ? acc[acc.length - 1].push(v) : acc.push([v]), acc), []);

function cellEl(spot) {
  const e = S.entries[spot];
  const d = document.createElement('div');
  d.className = 'cell'
    + (e ? (e.rest ? ' rest' : ' fill') : '')
    + (Y1.reserved[e && e.plate] === spot ? ' own' : '')
    + (spot === cursor && round ? ' cursor' : '');
  d.innerHTML = `<span class="n">${spot}</span>` + (e ? `<span class="p">${e.plate}</span>` : '');
  d.onclick = () => tapCell(spot);
  return d;
}

function block(label, list, per) {
  const out = [document.createElement('div')];
  out[0].className = 'lbl';
  out[0].textContent = label;
  for (const part of chunk(list, per)) {
    const row = document.createElement('div');
    row.className = 'row';
    part.forEach((s) => row.append(cellEl(s)));
    for (let i = part.length; i < per; i++) {
      const pad = document.createElement('div');
      pad.className = 'cell void';
      row.append(pad);
    }
    out.push(row);
  }
  return out;
}

function renderMap() {
  const m = $('map');
  m.innerHTML = '';
  const odd = Y1.seq.filter((s) => Number(s.split('-')[1]) % 2);
  const even = Y1.seq.filter((s) => !(Number(s.split('-')[1]) % 2));
  // 한 줄에 7칸씩. 종이와 같은 모양은 인쇄가 맡고, 화면은 손가락으로 짚을 수 있어야 한다.
  m.append(
    ...block('1차고지 · 맨 뒷열 (휴차 · 전용칸)', Y1.rear, 7),
    ...block('1차고지 · 뒷줄 (짝수)', even, 7),
    ...block('1차고지 · 앞줄 (홀수)', odd, 8),
    ...block('2차고지 · 3열', [...Y2.lanes[3], Y2.spare[3]], 7),
    ...block('2차고지 · 2열 (늦은 차)', [...Y2.lanes[2], Y2.spare[2]], 7),
    ...block('2차고지 · 1열', Y2.lanes[1], 7),
  );
}

function tapCell(spot) {
  const e = S.entries[spot];
  if (round) { cursor = spot; show('Pad'); renderMap(); renderEntry(); return; }
  if (e) {
    return sheet(`${spot} · ${e.plate}`, e.rest ? '휴차' : (e.out || ''), [
      ['비우기', 'warn', () => { S.entries = clear(S.entries, spot); save(S); renderBar(); renderMap(); renderLog(); }],
      ['닫기', '', null],
    ]);
  }
  sheet(`${spot} — 빈 자리`, '이 자리에 넣을까요?', [
    ['여기에 넣기', 'go', () => { pickAt = spot; show('Pad'); renderEntry(); }],
    ['닫기', '', null],
  ]);
}

// ---- 기록 --------------------------------------------------------------
function renderLog() {
  const box = $('log');
  box.innerHTML = '';
  for (const r of rows(S.entries)) {
    const d = document.createElement('div');
    d.className = 'lrow';
    d.innerHTML = `<span class="s">${r.spot}</span><span class="v">${r.plate}</span>`
      + `<span class="o">${r.rest ? '휴차' : (r.out || '')}</span>`
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

// ---- 화면 전환 ---------------------------------------------------------
function show(name) {
  for (const v of ['Pad', 'Map', 'Log']) $('view' + v).hidden = v !== name;
  document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('on', b.dataset.v === name));
}

// ---- 붙이기 ------------------------------------------------------------
$('pad').addEventListener('click', (ev) => {
  const k = ev.target.closest('button') && ev.target.closest('button').dataset.k;
  if (k) key(k);
});
$('btnRest').onclick = () => { restOn = !restOn; renderEntry(); };
$('btnClearKey').onclick = () => { typed = []; renderEntry(); };
$('btnSkip').onclick = () => { nextCursor(); renderEntry(); renderMap(); };
$('btnLast').onclick = () => {
  if (!last) return beep('warn');
  const spot = last;
  sheet(`직전 취소`, `${spot} 의 ${S.entries[spot] ? S.entries[spot].plate : ''} 를 지웁니다.`, [
    ['지우기', 'warn', () => {
      S.entries = clear(S.entries, spot);
      if (round) cursor = spot;
      last = null;
      save(S); renderBar(); renderEntry(); renderMap(); renderLog();
    }],
    ['취소', '', null],
  ]);
};
$('btnRound').onclick = () => {
  round = !round;
  if (round && !cursor) nextCursor(ALL_SPOTS[0] === cursor ? cursor : '1-0');
  show('Pad'); renderBar(); renderEntry(); renderMap();
};
$('btnToMap').onclick = () => show('Map');
$('btnVoice').onclick = () => { S.voice = !S.voice; save(S); renderBar(); };
$('big').onclick = hideBig;
$('swap').onclick = (ev) => {
  ev.stopPropagation();
  S.color = COLORS[(COLORS.indexOf(S.color) + 1) % COLORS.length];
  $('big').className = S.color;
};
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
$('btnPrint').onclick = () => { renderPaper(); window.print(); };
$('sheet').onclick = (ev) => { if (ev.target === $('sheet')) $('sheet').hidden = true; };

// 순회 커서는 첫 빈 자리에서 시작한다
cursor = ALL_SPOTS.find((s) => !S.entries[s]) || null;
renderBar(); renderEntry(); renderMap(); renderLog();

// 소스는 켤 때 한 번 받아서 폰에 남긴다. 못 받아도 수동으로 그대로 쓴다.
(async () => {
  const date = sourceDate(S.date);
  const src = await fetchSource(date);
  if (!src) return;
  S.cars = src.cars;
  S.sourceDate = date;
  S.cutoff = computeCutoff(
    Object.entries(src.cars).map(([plate, c]) => ({ plate: Number(plate), ...c })));
  save(S);
  renderBar();
})();

if ('serviceWorker' in navigator) navigator.serviceWorker.register('../sw.js').catch(() => {});
