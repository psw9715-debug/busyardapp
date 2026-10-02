// 변경 기록 — 무엇이 언제 어떻게 바뀌었는지 남긴다.
//
// 왜 필요한가
//   말로 받아 적는 일이라 잘못 들어가는 일이 반드시 생긴다. 카드 목록은 "지금 모습"
//   만 보여 주므로, 덮어쓰거나 지운 순간 **그 전에 무엇이 있었는지** 알 길이 없다.
//   여기에 바뀌기 전 값을 함께 남겨 두면 나중에 되짚을 수 있다.
//
// 어디에 쌓이는가
//   daywork:log:<근무일>  — 그날의 변경 기록 (최근 것이 뒤)
//   날짜별로 갈라 두어 하루치만 꺼내 보거나 지울 수 있다.

const PREFIX = 'daywork:log';
const key = (date) => `${PREFIX}:${date}`;

// 하루치 상한. 넘으면 오래된 것부터 버린다 (localStorage 는 5MB 안팎이다)
const MAX_PER_DAY = 600;
// 이보다 오래된 날은 켤 때 치운다
const KEEP_DAYS = 90;

export function read(date) {
  try {
    const raw = localStorage.getItem(key(date));
    return raw ? JSON.parse(raw) : [];
  } catch (_) {
    return [];
  }
}

/**
 * 한 줄 남긴다.
 *   kind  add | update | delete | skip | undo | clear | send
 *   plate 차량번호 (없을 수도 있다)
 *   from  바뀌기 전 내용 — 이것이 '수정본' 의 알맹이다
 *   to    바뀐 뒤 내용
 *   heard 그때 실제로 들린 말 (음성이 아니면 비운다)
 */
export function append(date, entry) {
  try {
    const rows = read(date);
    rows.push({ at: new Date().toISOString(), ...entry });
    localStorage.setItem(key(date), JSON.stringify(rows.slice(-MAX_PER_DAY)));
  } catch (err) {
    console.warn('변경 기록을 남기지 못했다', err);
  }
}

export function clear(date) {
  try { localStorage.removeItem(key(date)); } catch (_) {}
}

/** 기록이 있는 날짜 (최신 먼저) */
export function days() {
  const out = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(`${PREFIX}:`)) out.push(k.slice(PREFIX.length + 1));
    }
  } catch (_) {}
  return out.sort().reverse();
}

/** 오래된 날의 기록을 치운다. 켤 때 한 번 부른다. */
export function prune(today, keepDays = KEEP_DAYS) {
  const limit = new Date(`${today}T00:00:00`);
  limit.setDate(limit.getDate() - keepDays);
  const edge = limit.toISOString().slice(0, 10);
  let removed = 0;
  for (const d of days()) {
    if (d < edge) { clear(d); removed++; }
  }
  return removed;
}

/** 사람이 읽는 한 줄 */
export function describe(row) {
  const time = String(row.at || '').slice(11, 19);
  const what = {
    add: '입력', update: '수정', delete: '지움',
    skip: '건너뜀', undo: '되돌림', clear: '전체 지움', send: 'PC로 보냄',
  }[row.kind] || row.kind;

  let detail = row.plate || '';
  if (row.kind === 'update') detail += `  ${row.from || '(없음)'} → ${row.to || '(없음)'}`;
  else if (row.kind === 'delete') detail += `  ${row.from || ''}`;
  else if (row.to) detail += `  ${row.to}`;
  if (row.kind === 'send') detail = `${row.count || 0}건`;

  return `${time}  ${what}  ${detail}`.trimEnd();
}
