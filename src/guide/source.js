// 그날 소스 불러오기
//
// 사무실 PC 가 `tools/push_source.py` 로 만들어 올려둔 파일을 받아 온다.
// 한 번 받으면 폰 안에 남으므로 차고지에서 전파가 없어도 그날 내내 돈다.

import { workDate } from '../store.js?v=202609090606';

/** 읽을 날짜 = 근무일 + 1일. 밤에 들어오는 차는 다음날 아침 나가는 차다. */
export function sourceDate(date = workDate()) {
  const d = new Date(date + 'T12:00:00');
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** 못 받으면 null. 오류가 아니라 "아직 안 올라옴" 이다. */
export async function fetchSource(date) {
  try {
    const r = await fetch(`data/${date}.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!r.ok) return null;
    const j = await r.json();
    return j && j.cars ? j : null;
  } catch (_) {
    return null;
  }
}
