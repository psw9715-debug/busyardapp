// 최신 버전 받기
//
// 사파리는 옛 파일을 꽤 오래 붙잡고 있어서 새로고침만으로는 풀리지 않는다.
// version.json 만 캐시를 건너뛰고 받아와 지금 돌고 있는 것과 비교한다.
//
// 순회앱과 다른 점 — **자기 것만 지운다.**
//   순회앱의 forceUpdate 는 이 도메인의 캐시를 전부 지우고 서비스 워커를 모두
//   해제한다. 세 앱이 한 도메인에 올라가 있으므로, 그대로 따라 하면 이 앱이
//   갱신될 때 순회앱의 오프라인 캐시와 워커까지 날아간다. 그래서 여기서는
//   'daywork-' 캐시와 scope 가 /daywork/ 인 워커만 건드린다.

import { BUILD } from './build.js?v=202610080038';

const TRIED_KEY = 'daywork:triedBuild';

/** 올라온 버전. 확인할 수 없으면 null */
export async function latestBuild() {
  try {
    const res = await fetch(`./version.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) return null;
    return (await res.json()).build || null;
  } catch (_) {
    return null;    // 전파가 없으면 그냥 지금 것으로 쓴다
  }
}

/**
 * 새 것이 있으면 한 번은 알아서 받아 온다.
 * 같은 버전으로 두 번 새로 받는 일이 없도록 시도한 것은 기억해 둔다.
 * 돌려주는 값: 'current' | 'updating' | 'stuck' | 'unknown'
 */
export async function checkForUpdate() {
  const remote = await latestBuild();
  if (!remote) return 'unknown';
  if (remote === BUILD) return 'current';

  if (sessionStorage.getItem(TRIED_KEY) === remote) {
    // 이미 받아봤는데도 그대로다. 무한 새로고침 대신 알리기만 한다.
    return 'stuck';
  }
  try { sessionStorage.setItem(TRIED_KEY, remote); } catch (_) {}
  await forceUpdate();
  return 'updating';
}

/**
 * 이 앱의 캐시와 워커만 지우고 다시 받는다.
 * 받아 둔 카드(localStorage)는 건드리지 않는다.
 */
export async function forceUpdate() {
  try {
    if ('serviceWorker' in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs
        .filter((r) => r.scope.endsWith('/daywork/'))      // 순회앱 워커는 두고 간다
        .map((r) => r.unregister()));
    }
    if (window.caches) {
      const keys = await caches.keys();
      await Promise.all(keys
        .filter((k) => k.startsWith('daywork-'))           // 남의 캐시는 건드리지 않는다
        .map((k) => caches.delete(k)));
    }
  } catch (_) { /* 지우기에 실패해도 아래 재요청은 해본다 */ }

  const url = new URL(location.href);
  url.searchParams.set('v', Date.now().toString(36));
  location.replace(url.toString());
}

export { BUILD };
