// 오프라인 캐싱 — 서류철 있는 방에 전파가 약해도 앱은 뜨게 한다.
//
// 순회앱과 캐시를 **따로** 쓴다. 같은 도메인이라 캐시 저장소를 공유하므로,
// 이름 앞에 'daywork-' 를 붙이고 지울 때도 그 앞가지만 지운다.
// (루트 sw.js 가 'busyard-' 아닌 것을 모두 지우던 것을 함께 고쳐 두었다.
//  그러지 않으면 순회앱이 갱신될 때마다 이 앱의 캐시가 말없이 날아간다.)
//
// 주소(scope)가 /daywork/ 라서 이 앱의 페이지는 루트 워커가 아니라 이 워커가 맡는다.

const CACHE = 'daywork-202610072204';
const ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './src/app.css',
  './src/app.js',
  './src/entry.js',
  './src/roster.js',
  './src/workdate.js',
  './src/listen.js',
  './src/store.js',
  './src/sync.js',
  './src/log.js',
  './src/update.js',
  './src/build.js',
  './version.json',
  // 순회앱과 함께 쓰는 것 — 고치지 않고 가져다 쓴다
  '../src/plate.js',
  '../src/voice.js',
  '../icons/icon-180.png',
  '../icons/icon-192.png',
  '../icons/icon-512.png',
];

self.addEventListener('install', (e) => {
  // 하나가 404 여도 나머지는 담는다 (공용 파일 주소에 ?v= 가 붙는 날이 있다)
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => Promise.all(ASSETS.map((a) => c.add(a).catch(() => {}))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k.startsWith('daywork-') && k !== CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// 네트워크 우선, 실패하면 캐시 (배포 직후 새 버전을 바로 받도록)
self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  if (new URL(e.request.url).origin !== self.location.origin) return;   // GitHub 올리기는 건드리지 않는다
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(e.request).then((r) => r || caches.match('./index.html')))
  );
});
