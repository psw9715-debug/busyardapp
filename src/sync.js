// 그날 판을 GitHub 저장소의 inbox 가지에 올려 둔다. 사무실 PC(tools/inbox.py, sctc-copy 안에서
// 돈다)가 받아간다. [인쇄] 를 누르면 인쇄 요청도 함께 올리고, PC 가 남긴 결과를 읽어 온다.
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
    // 승용차는 전화번호가 알맹이다 — 이것이 빠지면 인쇄물에 아무것도 안 나온다
    if (e.phone) entries[n].phone = e.phone;
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
 * onStatus({ state: 'ok'|'fail'|'notoken', at, detail }) — 판 자동 올리기 결과
 */
export function createSync({ getSession, onStatus }) {
  let timer = null;
  const shaByName = {};   // 같은 파일을 덮어쓰려면 지금 파일의 sha 가 필요하다

  const headers = () => ({ Authorization: `Bearer ${getToken()}`, Accept: 'application/vnd.github+json' });

  async function currentSha(name) {
    const res = await fetch(`${API}/${name}?ref=${BRANCH}`, { headers: headers(), cache: 'no-store' });
    if (res.status === 404) return undefined;
    if (!res.ok) throw new Error(res.status === 401 ? '토큰이 맞지 않음' : `확인 실패 ${res.status}`);
    return (await res.json()).sha;
  }

  /** inbox/<name> 에 obj 를 JSON 으로 쓴다 */
  async function put(name, obj, message) {
    if (!getToken()) throw new Error('토큰 없음');
    const body = (sha) => JSON.stringify({
      message, branch: BRANCH, content: toBase64(JSON.stringify(obj)), ...(sha ? { sha } : {}),
    });
    if (!(name in shaByName)) shaByName[name] = await currentSha(name);
    let res = await fetch(`${API}/${name}`, { method: 'PUT', headers: headers(), body: body(shaByName[name]) });
    if (res.status === 409 || res.status === 422) {
      // 다른 곳(PC)에서 먼저 바뀌었다 — 지금 sha 로 한 번만 다시
      shaByName[name] = await currentSha(name);
      res = await fetch(`${API}/${name}`, { method: 'PUT', headers: headers(), body: body(shaByName[name]) });
    }
    if (!res.ok) throw new Error(res.status === 401 ? '토큰이 맞지 않음' : `올리기 실패 ${res.status}`);
    shaByName[name] = (await res.json()).content.sha;
  }

  // 차고지마다 판이 따로다. 이름에 차고지를 넣지 않으면 서로 덮어쓴다.
  const boardName = (session) => `${session.date}-${session.yard}.json`;

  async function putBoard() {
    const session = getSession();
    await put(boardName(session), boardPayload(session), `${session.date} ${session.yard} 순회판`);
  }

  async function upload() {
    timer = null;
    if (!getToken()) { onStatus({ state: 'notoken' }); return; }
    try {
      await putBoard();
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

    /**
     * 지금 판을 올리고 PC 에 부탁한다. what 은 'paper'(종이 인쇄) 또는 'excel'(운영관리 엑셀).
     * 요청 id 를 돌려준다. 실패하면 throw.
     */
    async requestPrint(what) {
      clearTimeout(timer);
      timer = null;
      await putBoard();
      onStatus({ state: 'ok', at: new Date() });
      const session = getSession();
      const id = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
      await put('print.json', { id, date: session.date, at: new Date().toISOString(), what, yard: session.yard },
        `${session.date} ${{ excel: '엑셀 입력', pull: '가져오기' }[what] || '인쇄'} 요청`);
      return id;
    },

    /** PC 가 엑셀에서 읽어 올려 둔 판 {id, yard, date, entries}. 아직 없으면 null */
    async readPulled() {
      const res = await fetch(`${API}/pulled.json?ref=${BRANCH}`, {
        headers: { ...headers(), Accept: 'application/vnd.github.raw+json' }, cache: 'no-store',
      });
      if (res.status === 404) return null;
      if (!res.ok) throw new Error(`가져오기 확인 실패 ${res.status}`);
      return res.json();
    },

    /** PC 가 남긴 인쇄 결과 {id, state, msg, at}. 아직 없으면 null */
    async readStatus() {
      const res = await fetch(`${API}/status.json?ref=${BRANCH}`, {
        headers: { ...headers(), Accept: 'application/vnd.github.raw+json' }, cache: 'no-store',
      });
      if (res.status === 404) return null;
      if (!res.ok) throw new Error(`결과 확인 실패 ${res.status}`);
      return res.json();
    },
  };
}
