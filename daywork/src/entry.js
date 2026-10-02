// 말 한 마디 -> 카드 한 장. 번호와 특이사항을 받는 상태기계.
//
// 서류철 140여 개를 넘기면서 특이사항이 있는 것만 불러 주는 흐름이다.
//
//   [번호 대기]  "천백이십"        -> 1120 을 들고 [내용 대기] 로
//   [내용 대기]  "대차"            -> 카드 저장, 다시 [번호 대기]
//   한 호흡     "천백이십 대차"    -> 바로 카드 저장
//
// 지켜야 할 것: 기록이 조용히 사라지지 않는다.
//   - 내용을 기다리는 중에 숫자가 들리면 그건 특이사항이 아니라 다음 차다.
//     앞 차는 '내용 없음' 카드로 남겨 두고 넘어간다 (버리지 않는다).
//   - 명부에 없는 번호도 막지 않는다. 'unknown' 으로 표시만 한다.
//
// 브라우저 API를 쓰지 않는 순수 로직이라 테스트 페이지에서 그대로 검사한다.

import { extractSequence } from '../../src/plate.js?v=202610030056';
import { isKnown } from './roster.js?v=202610030056';
import { workDate } from './workdate.js?v=202610030056';

// 공백·쉼표는 extractSequence 가 지우고 본다. 같은 규칙으로 지워야 위치가 맞는다.
const SKIP_CHARS = /[\s,.\-·]/;

// 단위만으로 된 말("천", "천백")은 아직 번호가 아니다.
// 사파리가 말 중간을 확정해 버렸을 때 1000 이 들어가는 것을 막는다.
const UNIT_ONLY = /^[천백십]+$/;

/**
 * 지운 문자열의 위치 -> 원문 위치 대응표.
 * 번호 뒤에 남은 말을 **원문 그대로**(띄어쓰기 살려서) 떼어내기 위한 것.
 * "천백이십 브레이크 소음" 에서 "브레이크 소음" 을 얻어야 한다 — 붙여 버리면
 * 엑셀에 "브레이크소음" 으로 들어가 기존 기록과 모양이 달라진다.
 */
function stripMap(text) {
  let stripped = '';
  const at = [];
  for (let i = 0; i < text.length; i++) {
    if (SKIP_CHARS.test(text[i])) continue;
    stripped += text[i];
    at.push(i);
  }
  return { stripped, at };
}

/** 번호 뒤에 남은 말을 원문에서 떼어낸다 */
function restAfter(text, raw) {
  const { stripped, at } = stripMap(text);
  const i = stripped.indexOf(raw);
  if (i < 0) return '';
  const end = i + raw.length;
  if (end >= at.length) return '';
  return text.slice(at[end]).trim();
}

export function createState(date = workDate()) {
  return { date, phase: 'plate', pending: null, cards: [] };
}

function makeCard(plate, symptom, now) {
  const text = (symptom || '').trim();
  return {
    plate,
    symptom: text,
    status: !text ? 'nosymptom' : (isKnown(plate) ? 'ok' : 'unknown'),
    at: now.toISOString(),
  };
}

/**
 * 카드를 넣는다. 같은 차가 오늘 또 들어오면 덮어쓴다 —
 * PC 프로그램이 같은 차량번호를 다시 입력했을 때 기존 행을 고치는 것과 같은 규칙.
 */
function put(state, card) {
  const i = state.cards.findIndex((c) => c.plate === card.plate);
  if (i >= 0) {
    const before = state.cards[i].symptom;    // 변경 기록에 남길 '바뀌기 전'
    state.cards[i] = card;
    return { type: 'card', card, updated: true, before };
  }
  state.cards.push(card);
  return { type: 'card', card, updated: false };
}

/** 내용을 못 받은 채 넘어가는 차를 카드로 남긴다 */
function parkPending(state, now) {
  if (!state.pending) return null;
  const card = makeCard(state.pending.plate, '', now);
  const ev = put(state, card);
  state.pending = null;
  return ev;
}

/**
 * 확정된(사파리가 isFinal 로 준) 말 한 마디를 처리한다.
 *
 * complete 플래그는 보지 않는다. "천백이십" 은 "천백이십사" 가 될 수 있어
 * complete=false 로 오지만, 여기 들어왔다는 것은 이미 말이 멎었다는 뜻이다.
 * 말하는 중간에 섣불리 넣는 문제는 호출하는 쪽(음성 래퍼)이 막는다.
 */
export function handleUtterance(state, text, now = new Date()) {
  const raw = String(text || '');
  const tokens = extractSequence(raw);

  const plateTok = tokens.find((t) => t.type === 'plate' && !UNIT_ONLY.test(t.raw));
  const back = tokens.some((t) => t.type === 'back');
  const skip = tokens.some((t) => t.type === 'skip');

  // 1) 번호가 들렸다 — 새 차로 넘어간다
  if (plateTok) {
    const parked = state.pending && state.pending.plate !== plateTok.plate
      ? parkPending(state, now) : null;
    state.pending = null;

    const rest = restAfter(raw, plateTok.raw);
    const restTokens = extractSequence(rest);
    const restIsCommand = restTokens.some((t) => t.type === 'skip' || t.type === 'back');

    // "천백이십 없음" — 특이사항 없는 차. 적지 않고 넘어간다.
    if (restIsCommand) {
      state.phase = 'plate';
      return { type: 'skip', plate: plateTok.plate, parked };
    }

    // 한 호흡에 다 불렀다
    if (rest) {
      state.phase = 'plate';
      const ev = put(state, makeCard(plateTok.plate, rest, now));
      return { ...ev, parked };
    }

    // 번호만 불렀다 — 내용을 기다린다
    state.pending = { plate: plateTok.plate, known: isKnown(plateTok.plate) };
    state.phase = 'symptom';
    return { type: 'pending', plate: plateTok.plate, known: state.pending.known, parked };
  }

  // 2) 되돌리기
  if (back) {
    return undo(state);
  }

  // 3) 특이사항 없는 차로 넘기기
  if (skip) {
    const had = state.pending;
    state.pending = null;
    state.phase = 'plate';
    return { type: 'skip', plate: had ? had.plate : null, parked: null };
  }

  // 4) 그냥 말 — 내용을 기다리는 중이면 특이사항이다
  if (state.phase === 'symptom' && state.pending) {
    const plate = state.pending.plate;
    state.pending = null;
    state.phase = 'plate';
    return put(state, makeCard(plate, raw, now));
  }

  return { type: 'ignored', heard: raw };
}

/** 기다리는 번호가 있으면 그것을, 없으면 직전 카드를 되돌린다 */
export function undo(state) {
  if (state.pending) {
    const plate = state.pending.plate;
    state.pending = null;
    state.phase = 'plate';
    return { type: 'undo', plate, from: 'pending' };
  }
  const card = state.cards.pop();
  state.phase = 'plate';
  return card ? { type: 'undo', plate: card.plate, card, from: 'card' }
              : { type: 'undo', plate: null, from: 'none' };
}

/**
 * 키패드로 번호를 넣는다. 음성 파서를 거치지 않는다.
 * 앞자리 1은 고정이라 뒤 세 자리만 받는다.
 */
export function setPlate(state, plate, now = new Date()) {
  const parked = state.pending && state.pending.plate !== plate ? parkPending(state, now) : null;
  state.pending = { plate, known: isKnown(plate) };
  state.phase = 'symptom';
  return { type: 'pending', plate, known: state.pending.known, parked };
}

/** 카드 한 장을 지운다 (목록에서 손으로). 지운 카드를 돌려준다 — 기록에 남기려고. */
export function removeCard(state, plate) {
  const i = state.cards.findIndex((c) => c.plate === plate);
  if (i < 0) return null;
  return state.cards.splice(i, 1)[0];
}

/** PC 로 보낼 것만 추린다 — 내용 없는 카드는 보내지 않는다(엑셀에 빈 줄이 생기므로) */
export function sendable(state) {
  return state.cards.filter((c) => c.symptom);
}
