// 오프라인 캐싱 — 차고지에서 전파가 약해도 앱 자체는 뜨게 한다.
// 버전을 올리면 다음 실행 때 새 파일을 받아간다.

const CACHE = 'busyard-202609020012';
const ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './src/app.css',
  './src/app.js',
  './src/plate.js',
  './src/voice.js',
  './src/store.js',
  './src/yard-data.js',
  './src/build.js',
  './icons/icon-180.png',
  './icons/icon-192.png',
  './icons/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// 네트워크 우선, 실패하면 캐시 (배포 직후 새 버전을 바로 받도록)
self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
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
