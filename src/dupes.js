// 같은 번호가 두 자리 이상에 들어갔는가 (2026-11-08 — 신차고지 1회차에 B5 와 B2 에 1351).
// 인쇄·엑셀 넣기를 누를 때 보내기 전에 긴급하게 알린다.

/** [{plate, spots: [자리이름…]}] — 번호가 있는 칸만 본다 (공차·승용차 칸은 번호가 없다) */
export function findDuplicates(entries, spotName) {
  const where = new Map();
  for (const [spot, e] of Object.entries(entries || {})) {
    if (!e || !e.plate) continue;
    if (!where.has(e.plate)) where.set(e.plate, []);
    where.get(e.plate).push(spotName(Number(spot)));
  }
  return [...where].filter(([, spots]) => spots.length > 1).map(([plate, spots]) => ({ plate, spots }));
}

/** 같은 중복을 두 번째 누를 때 알아보는 표시 */
export const dupKey = (dups) => dups.map((d) => `${d.plate}:${d.spots.join(',')}`).join('|');
