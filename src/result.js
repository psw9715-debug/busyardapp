// PC 가 돌려준 결과(inbox/status.json)를 읽고, 귀로 들을 한 줄을 만든다.
//
// ★ [2026-11-03] status.json 은 한 장이라 엑셀 넣기와 종이 인쇄를 연달아 누르면
//    뒤 결과가 앞 결과를 덮었다. PC 가 '최근' 에 열 개까지 함께 실어 주므로
//    폰은 제 요청 id 로 거기서 찾는다.

/** 그 요청의 결과 {id, state, msg}. 아직 없으면 null */
export function findStatus(st, id) {
  if (!st) return null;
  if (st.id === id) return st;
  return (st.최근 || []).find((x) => x.id === id) || null;
}

/** 예전엔 보낸 것을 한 건만 적어 두었다 — 그 꼴도 읽는다 */
export function pendingList(v) {
  if (!v) return [];
  return Array.isArray(v) ? v : [v];
}

const 이름 = { excel: '엑셀', final: '엑셀', paper: '종이 인쇄' };

/** 결과를 말로 — 짧게, 꼭 알아야 할 것만 (대수 · 인쇄 못 함 · 차찾아) */
export function resultSpeech(what, st) {
  const msg = st.msg || '';
  if (st.state !== 'done') return `${이름[what] || '종이 인쇄'} 실패. ${msg}`.trim();
  const 대수 = (msg.match(/(\d+)대 적음/) || msg.match(/(\d+)대/) || [])[1];
  const 말 = [];
  if (what === 'paper') 말.push('종이 인쇄했습니다');
  else if (msg.includes('인쇄까지 함')) 말.push('엑셀에 넣고 인쇄했습니다');
  else 말.push('엑셀에 넣었습니다');
  if (대수) 말.push(`${대수}대`);
  if (msg.includes('인쇄 못 함')) 말.push('인쇄는 못 했습니다');
  const 찾아 = msg.match(/차찾아 (\d+)대/);
  if (찾아) 말.push(`차찾아 ${찾아[1]}대`);
  return 말.join('. ');
}
