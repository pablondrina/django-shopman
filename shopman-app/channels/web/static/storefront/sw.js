const CACHE_NAME = 'nelson-v1';
const STATIC_ASSETS = ['/menu/', '/static/storefront/manifest.json', '/static/storefront/icon-192.svg'];
self.addEventListener('install', (event) => { event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))); self.skipWaiting(); });
self.addEventListener('activate', (event) => { event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))); self.clients.claim(); });
self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  if (request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(fetch(request).then((response) => { const clone = response.clone(); caches.open(CACHE_NAME).then((cache) => cache.put(request, clone)); return response; }).catch(() => caches.match(request)));
    return;
  }
  if (request.url.includes('/static/')) { event.respondWith(caches.match(request).then((cached) => cached || fetch(request))); return; }
});