// 그날 소스 불러오기
//
// 사무실 PC 가 `tools/push_source.py` 로 만들어 올려둔 파일을 받아 온다.
// 한 번 받으면 폰 안에 남으므로 차고지에서 전파가 없어도 그날 내내 돈다.

import { workDate } from '../store.js?v=202609212214';

/** 읽을 날짜 = 근무일 + 1일. 밤에 들어오는 차는 다음날 아침 나가는 차다. */
export function sourceDate(date = workDate()) {
  const d = new Date(date + 'T12:00:00');
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/**
 * 자리를 정하는 데 필요한 세 가지를 한 글자로 받는다.
 * 출차시각은 올리지 않는다 — 저장소가 공개라 시각표가 남지 않게 한 것이다.
 *
 *   r  휴차 · 낮에 나가는 차     l  늦은 차     e  빠른 차
 */
const BAND = {
  r: { rest: true, out: null, band: '휴차' },
  l: { rest: false, out: 'late', band: '늦음' },
  e: { rest: false, out: 'early', band: '빠름' },
};

/** 못 받으면 null. 오류가 아니라 "아직 안 올라옴" 이다. */
export async function fetchSource(date) {
  try {
    const r = await fetch(`data/${date}.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!r.ok) return null;
    const j = await r.json();
    if (!j || !j.bands) return null;
    const cars = {};
    for (const [plate, b] of Object.entries(j.bands)) {
      if (BAND[b]) cars[plate] = BAND[b];
    }
    return Object.keys(cars).length ? { date: j.date, cars } : null;
  } catch (_) {
    return null;
  }
}
