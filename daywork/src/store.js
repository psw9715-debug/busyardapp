// 받아쓴 카드 저장 — localStorage
//
// 순회앱과 같은 도메인에 올라가므로 저장 공간을 공유한다.
// 키 앞에 'daywork:' 를 붙여 완전히 갈라 두고, 순회앱의 'busyard:' 키는
// 토큰 하나만 **읽기만** 한다 (폰에 이미 넣어 둔 것을 다시 넣지 않게).

import { workDate } from './workdate.js?v=202610090511';

const PREFIX = 'daywork:v1';
const key = (date) => `${PREFIX}:${date}`;

// GitHub 토큰.
//
// 처음에는 순회앱에 넣어 둔 것을 읽어 쓰면 된다고 보았는데 그렇지 않았다 —
// iOS 는 홈화면에 추가한 웹앱마다 저장 공간을 따로 준다. 같은 주소라도 순회앱
// 아이콘과 이 앱 아이콘은 서로의 저장소를 보지 못한다. 그래서 이 앱도 자기 것을
// 가질 수 있어야 한다. 순회앱 것이 보이면(사파리로 열었을 때 등) 그대로 쓴다.
const TOKEN_KEY = 'daywork:ghtoken';
const YARD_TOKEN_KEY = 'busyard:ghtoken';

const read = (key) => {
  try { return localStorage.getItem(key) || ''; } catch (_) { return ''; }
};

export const getToken = () => read(TOKEN_KEY) || read(YARD_TOKEN_KEY);

/** 토큰이 어디서 왔는지 — 진단에서 보여 준다 */
export const tokenSource = () => {
  if (read(TOKEN_KEY)) return '이 앱에 넣은 것';
  if (read(YARD_TOKEN_KEY)) return '순회앱 것을 읽음';
  return '';
};

export function setToken(t) {
  try {
    if (t && t.trim()) localStorage.setItem(TOKEN_KEY, t.trim());
    else localStorage.removeItem(TOKEN_KEY);
  } catch (err) {
    console.warn('토큰을 저장하지 못했다', err);
  }
}

const listeners = [];
export function onSave(fn) { listeners.push(fn); }

/**
 * 그날 판을 읽는다. 없으면 빈 판.
 * phase·pending 은 저장하지 않는다 — 앱을 다시 켰으면 번호를 기다리는 자리에서
 * 시작하는 것이 맞다. 내용을 기다리던 번호는 저장할 때 이미 '내용 없음' 카드로
 * 남겨 두므로 잃지 않는다.
 */
export function loadSession(date = workDate()) {
  const empty = { date, phase: 'plate', pending: null, cards: [] };
  try {
    const raw = localStorage.getItem(key(date));
    if (!raw) return empty;
    const saved = JSON.parse(raw);
    return { ...empty, cards: Array.isArray(saved.cards) ? saved.cards : [] };
  } catch (err) {
    console.warn('저장된 판을 읽지 못했다', err);
    return empty;
  }
}

export function saveSession(session) {
  try {
    localStorage.setItem(key(session.date), JSON.stringify({
      date: session.date,
      cards: session.cards,
      updatedAt: new Date().toISOString(),
    }));
  } catch (err) {
    console.warn('판을 저장하지 못했다', err);
  }
  for (const fn of listeners) {
    try { fn(session); } catch (_) {}
  }
}

export function clearSession(session) {
  session.cards.length = 0;
  session.pending = null;
  session.phase = 'plate';
  saveSession(session);
}

/** 지난 날짜 목록 (최신 먼저) */
export function listDays() {
  const out = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (!k || !k.startsWith(`${PREFIX}:`)) continue;
      const date = k.slice(PREFIX.length + 1);
      let count = 0;
      try { count = (JSON.parse(localStorage.getItem(k)).cards || []).length; } catch (_) {}
      out.push({ date, count });
    }
  } catch (_) {}
  return out.sort((a, b) => (a.date < b.date ? 1 : -1));
}

export function removeDay(date) {
  try { localStorage.removeItem(key(date)); } catch (_) {}
}
