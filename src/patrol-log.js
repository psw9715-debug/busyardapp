// 차고지·회차별 **첫 입력** 시각 (2026-11-03).
//
// 앱을 켜기만 한 것은 치지 않는다 — 1회차는 첫 칸을 적은 때, 2회차는 첫 확인이나 첫 입력.
// 따로 보내지 않고 엑셀 넣기·종이 인쇄를 부탁할 때 함께 실어 보낸다 (PC 가 순찰 로그에 적는다).

/** {date, 기록: {old: {1: iso, 2: iso}, new: {...}}} 에 그 차고지·회차의 첫 시각을 넣는다 (이미 있으면 그대로) */
export function markFirst(v, date, yard, round, at) {
  const 지금 = v && v.date === date ? v : { date, 기록: {} };
  if (지금.기록[yard] && 지금.기록[yard][round]) return 지금;
  return { date, 기록: { ...지금.기록, [yard]: { ...(지금.기록[yard] || {}), [round]: at } } };
}
