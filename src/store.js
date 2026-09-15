// 순회 데이터 저장 — localStorage
//
// 자리마다 짧은 문자열 하나뿐이라 용량이 아주 작다. 매 입력마다 통째로 다시 쓴다.
// 회차(round)와 차고지(yard) 를 키에 넣어 두었으므로 나중에 2회차·구차고지를
// 추가할 때 이 파일은 손대지 않아도 된다.

const PREFIX = 'busyard:v1';

/** 야간 근무라 자정을 넘겨도 같은 날 순회로 묶는다 (오전 9시 기준으로 날짜 전환) */
export function workDate(now = new Date()) {
  const d = new Date(now);
  if (d.getHours() < 9) d.setDate(d.getDate() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

const key = (yard, date, round) => `${PREFIX}:${yard}:${date}:${round}`;

// ---- 배치도 번호 바꿈 -------------------------------------------------
// 예전에는 자리를 순회 순번(1~184)으로만 불렀고, 지금은 엑셀의 "구역-번호" 칸을
// 걷는 순서대로 센다. 같은 순번이라도 가리키는 칸이 달라졌으므로, 예전에 적은
// 기록은 엑셀 칸 위치를 거쳐 지금 번호로 옮긴다. 아래는 예전 순번 1~184 의 칸.
export const LAYOUT = 2;
const LEGACY_XL = (
  'N3 N6 N9 N12 N15 N18 N21 N24 N27 N30 N33 N36 N39 N42 N45 N48 N51 N54 N57 N60 ' +
  'E60 E57 E54 E51 E48 E45 E42 E39 E36 E33 E30 E27 E24 E21 E18 E15 E12 E9 C3 C6 ' +
  'D3 D6 E3 F3 G3 F6 F9 F12 D60 D57 D54 D51 D48 D45 D42 D39 D36 D33 D30 D27 ' +
  'D24 C24 C27 C30 C33 C36 A51 A48 A45 A42 A39 A33 A30 A27 A24 A21 A18 A15 A12 A9 ' +
  'A6 A3 H6 I6 H9 I9 H12 I12 H15 I15 H18 I18 H21 I21 H24 I24 H27 I27 H30 I30 ' +
  'H33 I33 M21 M18 M15 M12 M9 M6 M3 H39 I39 J39 K39 H42 I42 J42 K42 H45 I45 J45 ' +
  'K45 H48 I48 J48 K48 H51 I51 J51 K51 H54 I54 J54 K54 H57 I57 J57 K57 H60 I60 J60 ' +
  'K60 J6 J9 J12 J15 J18 J21 J24 J27 J30 J33 K6 K9 K12 K15 K18 K21 K24 K27 K30 ' +
  'K33 C9 C12 C15 C18 C21 D9 D12 D15 D18 D21 L24 L27 L30 L33 L36 L39 L42 L45 L48 ' +
  'L51 L54 L57 L60'
).split(' ');

/** 예전 순번으로 적힌 기록을 지금 번호로 옮긴다. 순회에서 빠진 칸의 기록은 버린다. */
function migrateEntries(entries, spotByXl) {
  const out = {};
  for (const [n, e] of Object.entries(entries || {})) {
    const to = spotByXl[LEGACY_XL[Number(n) - 1]];
    if (to) out[to] = e;
  }
  return out;
}

/** 예전 번호로 저장된 오늘 순회를 한 번만 옮긴다 */
export function upgradeSession(session, spotByXl) {
  if (session.layout === LAYOUT) return session;
  session.entries = migrateEntries(session.entries, spotByXl);
  session.layout = LAYOUT;
  saveSession(session);
  return session;
}

export function loadSession(yard, date = workDate(), round = 1) {
  const raw = localStorage.getItem(key(yard, date, round));
  if (raw) {
    try { return JSON.parse(raw); } catch (_) { /* 깨졌으면 새로 시작 */ }
  }
  return { yard, date, round, layout: LAYOUT, entries: {}, updatedAt: null };
}

export function saveSession(session) {
  session.updatedAt = new Date().toISOString();
  localStorage.setItem(key(session.yard, session.date, session.round), JSON.stringify(session));
}

/** entries[spot] = { plate, status, confidence, method, at } */
export function setEntry(session, spot, entry) {
  if (entry === null) delete session.entries[spot];
  else session.entries[spot] = { ...entry, at: Date.now() };
  saveSession(session);
  return session;
}

export function countFilled(session) {
  return Object.keys(session.entries).length;
}

/** 이 회차에 입력한 차량번호를 전부 지운다 */
export function clearSession(session) {
  session.entries = {};
  saveSession(session);
  return session;
}

// ---- 일지 보관 --------------------------------------------------------
// 그날 순회를 마치고 "저장"을 누르면 그 시점의 배치와 찾을 차량 목록을 통째로
// 남긴다. 매일 하나씩 쌓이고, 나중에 그날 것을 그대로 불러올 수 있다.

const LOG = `${PREFIX}:log`;

export const ROUNDS = [1, 2];

/**
 * 그날 순회를 통째로 남긴다.
 *
 * 회차는 자리마다 따로 저장하는 것이 아니라 각 입력에 표시로 붙어 있다.
 * 2회차는 1회차에 비어 있던 자리를 채우러 가는 것이라, 한 판을 이어 쓴다.
 */
export function saveLog(session, targets, date = workDate()) {
  const record = {
    date,
    yard: session.yard,
    savedAt: new Date().toISOString(),
    layout: LAYOUT,
    entries: session.entries,
    targets,
  };
  localStorage.setItem(`${LOG}:${date}`, JSON.stringify(record));
  return record;
}

/** 예전 일지는 회차별로 나뉘어 있었다. 한 판으로 합쳐서 읽는다. */
function logEntries(rec) {
  if (!rec) return {};
  if (rec.entries) return rec.entries;
  const out = {};
  for (const r of ROUNDS) {
    for (const [n, e] of Object.entries((rec.rounds || {})[r] || {})) {
      out[n] = { ...e, round: e.round || r };
    }
  }
  return out;
}

export function countRound(entries, round) {
  return Object.values(entries || {}).filter((e) => (e.round || 1) === round).length;
}

/** 저장해 둔 일지를 지금 순회로 되돌려 놓는다 */
export function restoreLog(rec, session, spotByXl) {
  const entries = logEntries(rec);
  session.entries = rec.layout === LAYOUT ? entries : migrateEntries(entries, spotByXl);
  session.layout = LAYOUT;
  saveSession(session);
  return session;
}

/**
 * 예전 버전은 2회차를 별도 판에 저장했다. 그 판이 남아 있으면 한 판으로 합친다.
 * 합치고 나면 그 키는 지운다 (한 번만 일어나는 일).
 */
export function mergeLegacyRound2(session) {
  const key = `${PREFIX}:${session.yard}:${session.date}:2`;
  const raw = localStorage.getItem(key);
  if (!raw) return session;
  try {
    const old = JSON.parse(raw);
    for (const [n, e] of Object.entries(old.entries || {})) {
      if (!session.entries[n]) session.entries[n] = { ...e, round: 2 };
    }
    saveSession(session);
  } catch (_) { /* 깨졌으면 버린다 */ }
  localStorage.removeItem(key);
  return session;
}

export function listLogs() {
  const out = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (!k || !k.startsWith(LOG + ':')) continue;
    try {
      const r = JSON.parse(localStorage.getItem(k));
      const entries = logEntries(r);
      out.push({
        date: r.date,
        savedAt: r.savedAt,
        counts: ROUNDS.map((n) => countRound(entries, n)),
        targets: (r.targets || []).length,
      });
    } catch (_) { /* 깨진 것은 건너뛴다 */ }
  }
  return out.sort((a, b) => (a.date < b.date ? 1 : -1));
}

export function readLog(date) {
  try {
    return JSON.parse(localStorage.getItem(`${LOG}:${date}`));
  } catch (_) { return null; }
}

export function deleteLog(date) {
  localStorage.removeItem(`${LOG}:${date}`);
}

export function listSessions() {
  const out = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (!k || !k.startsWith(PREFIX + ':')) continue;
    const [, , yard, date, round] = k.split(':');
    out.push({ key: k, yard, date, round: Number(round) });
  }
  return out.sort((a, b) => (a.date < b.date ? 1 : -1));
}
