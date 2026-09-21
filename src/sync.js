// 그날 판을 GitHub 저장소의 inbox 가지에 올려 둔다. 사무실 PC(tools/inbox.py)가
// 인쇄할 때 받아간다.
//
// 폰(LTE)과 PC(사내 유선)는 서로 직접 닿을 수 없어서, 둘 다 닿는 GitHub 에 놓고 간다.
// 앱이 배포되는 main 이 아니라 inbox 가지에 쓰므로 올려도 앱이 다시 배포되지 않는다.
// 쓰기에는 토큰이 필요하다. 저장소가 공개라 코드에 넣지 않고 폰에만 둔다.

const API = 'https://api.github.com/repos/psw9715-debug/busyardapp/contents/inbox';
const BRANCH = 'inbox';
const TOKEN_KEY = 'busyard:ghtoken';
const WAIT_MS = 30000;   // 입력이 멎고 이만큼 지나면 올린다

export const getToken = () => localStorage.getItem(TOKEN_KEY) || '';
export function setToken(t) {
  if (t) localStorage.setItem(TOKEN_KEY, t.trim());
  else localStorage.removeItem(TOKEN_KEY);
}

/** 인쇄에 쓰는 것만 추린다 */
export function boardPayload(session) {
  const entries = {};
  for (const [n, e] of Object.entries(session.entries)) {
    entries[n] = { plate: e.plate, status: e.status, round: e.round || 1 };
  }
  return { date: session.date, yard: session.yard, layout: session.layout, updatedAt: session.updatedAt, entries };
}

/** GitHub 은 파일 내용을 base64 로 받는다. btoa 는 한글을 못 받으므로 UTF-8 바이트로 바꿔서 */
export function toBase64(text) {
  let bin = '';
  for (const b of new TextEncoder().encode(text)) bin += String.fromCharCode(b);
  return btoa(bin);
}

/**
 * getSession: 올릴 판을 돌려주는 함수
 * onStatus({ state: 'ok'|'fail'|'notoken', at, detail })
 */
export function createSync({ getSession, onStatus }) {
  let timer = null;
  const shaByDate = {};   // 같은 파일을 덮어쓰려면 지금 파일의 sha 가 필요하다

  async function currentSha(date, headers) {
    const res = await fetch(`${API}/${date}.json?ref=${BRANCH}`, { headers, cache: 'no-store' });
    if (res.status === 404) return undefined;
    if (!res.ok) throw new Error(`확인 실패 ${res.status}`);
    return (await res.json()).sha;
  }

  async function upload() {
    timer = null;
    const token = getToken();
    if (!token) { onStatus({ state: 'notoken' }); return; }
    const session = getSession();
    const date = session.date;
    const headers = { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' };
    const body = (sha) => JSON.stringify({
      message: `${date} 순회판`,
      content: toBase64(JSON.stringify(boardPayload(session))),
      branch: BRANCH,
      ...(sha ? { sha } : {}),
    });
    try {
      if (!(date in shaByDate)) shaByDate[date] = await currentSha(date, headers);
      let res = await fetch(`${API}/${date}.json`, { method: 'PUT', headers, body: body(shaByDate[date]) });
      if (res.status === 409 || res.status === 422) {
        // 다른 곳에서 먼저 바뀌었다 — 지금 sha 로 한 번만 다시
        shaByDate[date] = await currentSha(date, headers);
        res = await fetch(`${API}/${date}.json`, { method: 'PUT', headers, body: body(shaByDate[date]) });
      }
      if (!res.ok) throw new Error(res.status === 401 ? '토큰이 맞지 않음' : `올리기 실패 ${res.status}`);
      shaByDate[date] = (await res.json()).content.sha;
      onStatus({ state: 'ok', at: new Date() });
    } catch (err) {
      onStatus({ state: 'fail', detail: err.message || String(err) });
    }
  }

  return {
    /** 입력이 있을 때마다 부른다. 멎고 30초 뒤 한 번 올린다. */
    schedule() {
      clearTimeout(timer);
      timer = setTimeout(upload, WAIT_MS);
    },
    /** 기다리지 않고 바로 올린다 */
    flush() {
      clearTimeout(timer);
      return upload();
    },
    /** 올릴 것이 남아 있는가 (앱이 가려질 때 바로 올리려고) */
    pending: () => timer !== null,
  };
}
