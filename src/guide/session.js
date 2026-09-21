// 진입 안내 — 그날 판 저장 (localStorage)
//
// 순회 앱과 같은 오전 9시 기준 날짜 전환을 쓴다. 새벽 00:40 에 넣어도 같은 날 근무다.

import { workDate } from '../store.js?v=202609212237';

const PREFIX = 'busyard:guide:v1';
const key = (date) => `${PREFIX}:${date}`;

export const COLORS = ['wr', 'bw', 'wb'];   // 흰/빨강 · 검정/흰 · 흰/검정

export function load(date = workDate()) {
  const raw = localStorage.getItem(key(date));
  if (raw) {
    try {
      const s = JSON.parse(raw);
      return { color: COLORS[0], voice: true, entries: {}, ...s, date };
    } catch (_) { /* 깨졌으면 새로 시작 */ }
  }
  return { date, cutoff: null, color: COLORS[0], voice: true, entries: {}, updatedAt: null };
}

export function save(session) {
  session.updatedAt = new Date().toISOString();
  localStorage.setItem(key(session.date), JSON.stringify(session));
  return session;
}

/** 자리순으로 정렬한 목록. 엑셀에 옮겨적을 때 쓴다. */
export function rows(entries) {
  return Object.keys(entries)
    .sort((a, b) => {
      const [ay, an] = a.split('-').map(Number);
      const [by, bn] = b.split('-').map(Number);
      return ay - by || an - bn;
    })
    .map((spot) => ({ spot, ...entries[spot] }));
}

// ---- 보관 -------------------------------------------------------------
// 그날 판을 날짜별로 남긴다. 나중에 불러와서 인쇄할 수 있다.

const LOG = `${PREFIX}:log`;

export function saveLog(session) {
  const rec = {
    date: session.date,
    savedAt: new Date().toISOString(),
    sourceDate: session.sourceDate || null,
    cutoff: session.cutoff || null,
    entries: session.entries,
  };
  localStorage.setItem(`${LOG}:${session.date}`, JSON.stringify(rec));
  return rec;
}

export function listLogs() {
  const out = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (!k || !k.startsWith(LOG + ':')) continue;
    try {
      const r = JSON.parse(localStorage.getItem(k));
      out.push({ date: r.date, savedAt: r.savedAt, count: Object.keys(r.entries || {}).length });
    } catch (_) { /* 깨진 것은 건너뛴다 */ }
  }
  return out.sort((a, b) => (a.date < b.date ? 1 : -1));
}

export function readLog(date) {
  try { return JSON.parse(localStorage.getItem(`${LOG}:${date}`)); } catch (_) { return null; }
}

export function deleteLog(date) {
  localStorage.removeItem(`${LOG}:${date}`);
}

export function toCsv(entries) {
  const head = '자리,차량번호,출차,비고';
  const body = rows(entries).map((r) =>
    [r.spot, r.car ? '승용차' : r.plate,
     r.car ? '' : (r.rest ? '휴차' : (r.band || r.out || '')), r.reason || ''].join(','));
  return [head, ...body].join('\n');
}
