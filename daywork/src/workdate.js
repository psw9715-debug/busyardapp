// 근무일 계산 — PC 의 daywork.py 와 **글자 그대로 같은 규칙**이어야 한다.
//
//   daywork.py:  if now.hour < 6 or (now.hour == 6 and now.minute <= 30): 전날
//
// 순회앱의 store.js 에도 workDate() 가 있지만 그쪽은 **오전 9시 기준**이다.
// 그걸 가져다 쓰면 06:30~09:00 사이에 넣은 기록이 하루 밀려 엉뚱한 시트로 간다.
// 자정·00:30·01시에 넣을 때는 두 규칙이 같은 답을 내서 한동안 멀쩡해 보이다가,
// 아침 7시에 한 번 몰아 넣는 날 조용히 틀린다. 그래서 따로 둔다.

/** 'YYYY-MM-DD' */
export function workDate(now = new Date()) {
  const d = new Date(now);
  const beforeCut = d.getHours() < 6 || (d.getHours() === 6 && d.getMinutes() <= 30);
  if (beforeCut) d.setDate(d.getDate() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** 엑셀 시트 이름 (MM.DD) — PC 가 쓰는 이름과 같아야 한다 */
export function sheetName(dateStr) {
  const [, m, d] = dateStr.split('-');
  return `${m}.${d}`;
}
