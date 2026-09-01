// 순회 데이터 저장 — localStorage
//
// 자리 109개 × 짧은 문자열이라 용량이 아주 작다. 매 입력마다 통째로 다시 쓴다.
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
