// 받아쓴 것을 PC 로 보낸다.
//
// 폰(LTE)과 사무실 PC(사내망)는 서로 직접 닿을 수 없다. 그래서 순회앱과 똑같이
// GitHub 저장소의 inbox 가지를 우편함으로 쓴다. 앱이 배포되는 main 이 아니라
// inbox 가지라서, 올려도 앱이 다시 배포되지 않는다.
//
// 파일 이름을 'daywork-' 로 시작하게 해 순회앱이 쓰는 판과 섞이지 않게 한다.
// 토큰은 순회앱에 이미 넣어 둔 것을 **읽기만** 한다 (폰에 다시 넣을 필요가 없다).

import { getToken } from './store.js?v=202610030404';

const API = 'https://api.github.com/repos/psw9715-debug/busyardapp/contents/inbox';
const BRANCH = 'inbox';

const shaByName = {};   // 같은 파일을 덮어쓰려면 지금 파일의 sha 가 필요하다

const headers = () => ({
  Authorization: `Bearer ${getToken()}`,
  Accept: 'application/vnd.github+json',
});

/** GitHub 은 내용을 base64 로 받는다. btoa 는 한글을 못 받으므로 UTF-8 바이트로 */
export function toBase64(text) {
  let bin = '';
  for (const b of new TextEncoder().encode(text)) bin += String.fromCharCode(b);
  return btoa(bin);
}

/** PC 가 받아 적을 것만 추린다 — 내용 없는 카드는 보내지 않는다 */
export function payload(session) {
  return {
    app: 'daywork',
    date: session.date,
    updatedAt: new Date().toISOString(),
    entries: session.cards
      .filter((c) => c.symptom)
      .map((c) => ({ plate: c.plate, issue: c.symptom, at: c.at, known: c.status !== 'unknown' })),
  };
}

async function currentSha(name) {
  const res = await fetch(`${API}/${name}?ref=${BRANCH}`, { headers: headers(), cache: 'no-store' });
  if (res.status === 404) return undefined;
  if (!res.ok) throw new Error(res.status === 401 ? '토큰이 맞지 않음' : `확인 실패 ${res.status}`);
  return (await res.json()).sha;
}

/**
 * 그날 판을 우편함에 올린다. 보낸 건수를 돌려준다.
 * 같은 날 다시 보내면 덮어쓴다 — PC 는 (날짜, 차량번호) 로 적으므로 여러 번 보내도 안전하다.
 */
export async function send(session) {
  if (!getToken()) throw new Error('토큰 없음 — 순회앱에서 먼저 넣어 주세요');

  const name = `daywork-${session.date}.json`;
  const obj = payload(session);
  const body = (sha) => JSON.stringify({
    message: `${session.date} 특이사항 ${obj.entries.length}건`,
    branch: BRANCH,
    content: toBase64(JSON.stringify(obj)),
    ...(sha ? { sha } : {}),
  });

  if (!(name in shaByName)) shaByName[name] = await currentSha(name);
  let res = await fetch(`${API}/${name}`, { method: 'PUT', headers: headers(), body: body(shaByName[name]) });
  if (res.status === 409 || res.status === 422) {
    // 다른 곳에서 먼저 바뀌었다 — 지금 sha 로 한 번만 다시
    shaByName[name] = await currentSha(name);
    res = await fetch(`${API}/${name}`, { method: 'PUT', headers: headers(), body: body(shaByName[name]) });
  }
  if (!res.ok) throw new Error(res.status === 401 ? '토큰이 맞지 않음' : `보내기 실패 ${res.status}`);

  shaByName[name] = (await res.json()).content.sha;
  return obj.entries.length;
}
