// 1·2차고지 진입 안내 — 자리 배정
//
// 브라우저 API를 쓰지 않는 순수 로직이다. 화면 없이 테스트할 수 있어야
// 밤에 틀린 자리를 부르는 일이 없다.
//
// entries 는 `{ "1-1": { plate, rest, out }, … }` 꼴이고 키가 자리번호라
// 한 자리에 두 대가 들어가는 일이 구조적으로 생기지 않는다.

import { YARD12 } from './yard12-data.js?v=202609260048';

const Y1 = YARD12.yard1;
const Y2 = YARD12.yard2;

/** 이 시각 이후에 나가는 차는 사실상 안 나가는 것으로 본다 */
export const DAY_OUT = '09:00';

/** 2차고지에서 "늦은 차"를 가르는 기준. 1열은 6시까지, 2열은 6시 15분 이후다.
 *  실측 4일 모두 이 값이 2열 정원과 맞았다. */
export const DEFAULT_CUTOFF = '06:15';

/** 2열 정원 — 9칸 + 예비 2-27 */
const LANE2_ROOM = Y2.lanes[2].length + (Y2.spare[2] ? 1 : 0);

/**
 * 1차고지 끝의 회차 공간. 차들이 여기서 돌아 나가야 해서 채우면 복잡해진다.
 * 다른 자리가 다 찼을 때만 마지막으로 쓴다.
 */
const TURN_AREA = ['1-27', '1-28', '1-29'];
const notTurn = (spot) => !TURN_AREA.includes(spot);

/** 61번 전용칸 — 다른 차로 먼저 메우지 않는다 */
const RESERVED_SPOTS = Object.values(Y1.reserved);

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
  if (car.rest) return true;
  if (car.out === 'early' || car.out === 'late') return false;   // 소스가 이미 갈라 놓았다
  return Boolean(car.out) && car.out >= DAY_OUT;
}

/** 늦은 차인가 — 시각이 있으면 컷오프로, 소스가 갈라 놓았으면 그대로 */
function isLate(car, cutoff) {
  if (car.out === 'late') return true;
  if (car.out === 'early') return false;
  return car.out >= cutoff;
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
    // 맨 뒷열을 왼쪽(1-30)부터. 전용칸은 비켜 두고, 순번 넘침분은 오른쪽에서
    // 오므로 가운데서 만난다.
    const back = firstFree(entries, Y1.rear.filter((s) => !RESERVED_SPOTS.includes(s)));
    if (back) return { spot: back, reason: car.rest ? '휴차 → 맨 뒷열' : '낮 출차 → 맨 뒷열' };
    const front = firstFree(entries, Y1.seq.filter(isOdd).filter(notTurn));
    if (front) return { spot: front, reason: '맨 뒷열 만차 → 앞줄' };
    const rest = firstFree(entries, [...Y1.rear, ...TURN_AREA]);
    return rest ? { spot: rest, reason: '다 차서 남은 자리로' } : null;
  }

  const seq = firstFree(entries, Y1.seq.filter(notTurn));
  if (seq) return { spot: seq, reason: '순번' };
  const over = firstFree(entries, [...Y1.rear].reverse().filter((s) => !RESERVED_SPOTS.includes(s)));
  if (over) return { spot: over, reason: '순번행 만차 → 맨 뒷열' };
  const turn = firstFree(entries, [...TURN_AREA, ...Y1.rear]);
  return turn ? { spot: turn, reason: '다 차서 회차 공간까지' } : null;
}

/**
 * 2차고지.
 *
 *   1열  6시까지 나가는 차
 *   2열  6시 15분 이후에 나가는 늦은 차 · 휴차
 *   3열  1열과 같은 빠른 차, 또는 2열에 못 넣은 늦은 차
 *
 * 가운데(2열)에 늦은 차가 오면 아침에 편하지만 꼭 그래야 하는 것은 아니다.
 * 앞에서부터 차례로 빠져도 되고, 뒤에서부터 후진으로 빠져도 된다.
 * 그래서 자리가 없으면 옆 줄로 넘길 뿐 멈추지 않는다.
 *
 * **출차시각을 모르면 묻지 않는다.** 1열 → 2열 → 3열 순서로 채운다.
 * 그렇게만 넣어도 아침에 빠져나가는 데 문제가 없다.
 */
function placeYard2(entries, car, cutoff) {
  const lane = (n) => firstFree(entries, Y2.lanes[n]);
  const spare = (n) => (Y2.spare[n] && !entries[Y2.spare[n]] ? Y2.spare[n] : null);
  const first = (...picks) => picks.find((p) => p && p[0]) || null;

  if (!car.rest && !car.out) {
    const seq = first([lane(1), '순서대로 1열'], [lane(2), '1열 만차 → 2열'],
                      [lane(3), '2열 만차 → 3열'],
                      [spare(2), '예비'], [spare(3), '예비']);
    return seq && { spot: seq[0], reason: seq[1] };
  }

  if (staysPut(car) || isLate(car, cutoff)) {
    const late = first([lane(2), car.rest ? '휴차 → 2열' : `${cutoff} 이후 → 2열`],
                       [spare(2), '2열 만차 → 예비'],
                       [lane(3), '2열 만차 → 3열'], [spare(3), '예비']);
    return late && { spot: late[0], reason: late[1] };
  }

  const early = first([lane(1), '1열'], [lane(3), '1열 만차 → 3열'],
                      [spare(3), '3열 만차 → 예비'],
                      [lane(2), '1·3열 만차 → 2열'], [spare(2), '예비']);
  return early && { spot: early[0], reason: early[1] };
}

/**
 * 자리를 정한다. 상태를 바꾸지 않고 결과만 돌려준다.
 *
 * 성공 { ok:true, yard, spot, lane, reason }
 * 실패 { ok:false, kind }
 *   'move'      이미 다른 자리에 있는 차다. spot·from 을 함께 준다
 *   'full'      빈 자리가 없다. 억지로 만들지 않는다
 */
export function assign(entries, car, { cutoff = DEFAULT_CUTOFF } = {}) {
  const from = Object.keys(entries).find((s) => entries[s].plate === car.plate) || null;   // 승용차는 plate 가 없어 안 걸린다
  const board = from ? { ...entries } : entries;
  if (from) delete board[from];

  const yard = yardOf(car.plate);
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
  const outs = target
    .filter((c) => !staysPut(c) && c.out !== 'early' && c.out !== 'late')
    .map((c) => c.out).sort().reverse();
  return room <= outs.length ? outs[room - 1] : DEFAULT_CUTOFF;
}
