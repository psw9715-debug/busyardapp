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

export function loadSession(yard, date = workDate(), round = 1) {
  const raw = localStorage.getItem(key(yard, date, round));
  if (raw) {
    try { return JSON.parse(raw); } catch (_) { /* 깨졌으면 새로 시작 */ }
  }
  return { yard, date, round, entries: {}, updatedAt: null };
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
export function restoreLog(rec, session) {
  session.entries = logEntries(rec);
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
