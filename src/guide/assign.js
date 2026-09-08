// 1·2차고지 진입 안내 — 자리 배정
//
// 브라우저 API를 쓰지 않는 순수 로직이다. 화면 없이 테스트할 수 있어야
// 밤에 틀린 자리를 부르는 일이 없다.
//
// entries 는 `{ "1-1": { plate, rest, out }, … }` 꼴이고 키가 자리번호라
// 한 자리에 두 대가 들어가는 일이 구조적으로 생기지 않는다.

import { YARD12 } from './yard12-data.js?v=202609090606';

const Y1 = YARD12.yard1;
const Y2 = YARD12.yard2;

/** 이 시각 이후에 나가는 차는 사실상 안 나가는 것으로 본다 */
export const DAY_OUT = '09:00';

/** 2차고지에서 "늦은 차"를 가르는 기본값. 실측 4일 모두 이 값이 나왔다. */
export const DEFAULT_CUTOFF = '06:15';

/** 2열 정원 — 9칸 + 예비 2-27 */
const LANE2_ROOM = Y2.lanes[2].length + (Y2.spare[2] ? 1 : 0);

const num = (spot) => Number(spot.split('-')[1]);
const isOdd = (spot) => num(spot) % 2 === 1;
const firstFree = (entries, list) => list.find((s) => !entries[s]) || null;

/** 1004·1005번(2차고지)인지, 그 밖의 전부(1차고지)인지 */
export function yardOf(plate) {
  if (plate === 1015 || plate === 1016) return 1;   // 61번 — 범위보다 먼저 본다
  if (plate >= 1012 && plate <= 1031) return 2;
  if (plate >= 1732 && plate <= 1754) return 2;
  return 1;
}

/** 내일 아침에 안 나가는 차 — 휴차이거나 낮에 나간다 */
export function staysPut(car) {
  return Boolean(car.rest) || (Boolean(car.out) && car.out >= DAY_OUT);
}

/** 자리번호로 기사님께 보여줄 숫자를 정한다 */
export function laneOf(spot) {
  const n = num(spot);
  if (spot.startsWith('1-')) return n >= num(Y1.rear[0]) ? 3 : (n % 2 ? 1 : 2);
  if (Y2.spare[2] === spot) return 2;
  if (Y2.spare[3] === spot) return 3;
  for (const lane of [1, 2, 3]) {
    if (Y2.lanes[lane].includes(spot)) return lane;
  }
  return null;
}

/** 전용칸이 차 있을 때 가장 가까운 빈칸. 거리가 같으면 안쪽(작은 번호). */
function nearestFree(entries, target) {
  const t = num(target);
  const open = Y1.rear.filter((s) => !entries[s]);
  if (!open.length) return null;
  return open.reduce((best, s) => {
    const d = Math.abs(num(s) - t);
    const bd = Math.abs(num(best) - t);
    if (d !== bd) return d < bd ? s : best;
    return num(s) < num(best) ? s : best;
  });
}

function placeYard1(entries, car) {
  const own = Y1.reserved[car.plate];
  if (own) {
    if (!entries[own]) return { spot: own, reason: `${car.plate} 전용칸` };
    const near = nearestFree(entries, own);
    return near ? { spot: near, reason: `${own} 점유 → 최인접` } : null;
  }

  if (staysPut(car)) {
    // 맨 뒷열을 뒤에서부터 — 순번 넘침분은 앞에서 오므로 가운데서 만난다
    const back = firstFree(entries, [...Y1.rear].reverse());
    if (back) return { spot: back, reason: car.rest ? '휴차 → 맨 뒷열' : '낮 출차 → 맨 뒷열' };
    const front = firstFree(entries, Y1.seq.filter(isOdd));
    return front ? { spot: front, reason: '맨 뒷열 만차 → 앞줄' } : null;
  }

  const seq = firstFree(entries, Y1.seq);
  if (seq) return { spot: seq, reason: '순번' };
  const over = firstFree(entries, Y1.rear);
  return over ? { spot: over, reason: '순번행 만차 → 맨 뒷열' } : null;
}

function placeYard2(entries, car, cutoff) {
  const late = staysPut(car) || car.out >= cutoff;
  if (late) {
    const lane2 = firstFree(entries, Y2.lanes[2]);
    if (lane2) return { spot: lane2, reason: car.rest ? '휴차 → 2열' : `${cutoff} 이상 → 2열` };
    if (!entries[Y2.spare[2]]) return { spot: Y2.spare[2], reason: '2열 만차 → 예비' };
    return null;
  }

  const lane1 = firstFree(entries, Y2.lanes[1]);
  if (lane1) return { spot: lane1, reason: '1열' };
  const lane3 = firstFree(entries, Y2.lanes[3]);
  if (lane3) return { spot: lane3, reason: '1열 만차 → 3열' };
  if (!entries[Y2.spare[3]]) return { spot: Y2.spare[3], reason: '3열 만차 → 예비' };
  return null;
}

/**
 * 자리를 정한다. 상태를 바꾸지 않고 결과만 돌려준다.
 *
 * 성공 { ok:true, yard, spot, lane, reason }
 * 실패 { ok:false, kind }
 *   'move'      이미 다른 자리에 있는 차다. spot·from 을 함께 준다
 *   'need-time' 2차고지인데 휴차인지 몇 시에 나가는지 모른다
 *   'full'      빈 자리가 없다. 억지로 만들지 않는다
 */
export function assign(entries, car, { cutoff = DEFAULT_CUTOFF } = {}) {
  const from = Object.keys(entries).find((s) => entries[s].plate === car.plate) || null;
  const board = from ? { ...entries } : entries;
  if (from) delete board[from];

  const yard = yardOf(car.plate);
  if (yard === 2 && !car.rest && !car.out) return { ok: false, kind: 'need-time', yard };

  const put = yard === 1 ? placeYard1(board, car) : placeYard2(board, car, cutoff);
  if (!put) return { ok: false, kind: 'full', yard };

  const result = { ok: true, yard, spot: put.spot, lane: laneOf(put.spot), reason: put.reason };
  return from ? { ...result, ok: false, kind: 'move', from } : result;
}

/** 자리를 채운 새 판을 돌려준다. from 이 있으면 그 자리는 비운다. */
export function place(entries, car, spot, { from = null } = {}) {
  const next = { ...entries };
  if (from) delete next[from];
  next[spot] = { plate: car.plate, rest: Boolean(car.rest), out: car.out || null };
  return next;
}

export function clear(entries, spot) {
  const next = { ...entries };
  delete next[spot];
  return next;
}

/**
 * 그날 2차고지 대상으로 2열 정원(10대)에 맞는 컷오프를 뽑는다.
 *
 * 휴차는 무조건 2열이므로 먼저 자리를 빼고, 남은 칸만큼 늦은 차를 받는다.
 * 실측 4일 모두 06:15 가 나왔다.
 */
export function computeCutoff(cars) {
  const target = cars.filter((c) => yardOf(c.plate) === 2);
  const stay = target.filter(staysPut).length;
  const room = LANE2_ROOM - stay;
  if (room <= 0) return DEFAULT_CUTOFF;
  const outs = target.filter((c) => !staysPut(c)).map((c) => c.out).sort().reverse();
  return room <= outs.length ? outs[room - 1] : DEFAULT_CUTOFF;
}
