export default defineEventHandler((event) => {
  setResponseHeader(event, 'Content-Type', 'application/javascript; charset=utf-8')
  setResponseHeader(event, 'Cache-Control', 'no-store')
  return `
const CACHE_NAME = 'shopman-nuxt-pwa-v2'
const OFFLINE_URL = '/offline'
const PRECACHE_URLS = ['/offline', '/manifest.json', '/pwa/icon-192.png', '/pwa/icon-512.png', '/pwa/icon-maskable-512.png']
const SAFE_NAVIGATION_PATHS = ['/', '/menu', '/como-funciona', '/offline']
const SAFE_NAVIGATION_PREFIXES = ['/produto/']
const CACHE_FIRST_PREFIXES = ['/_nuxt/', '/_fonts/', '/pwa/']
const NETWORK_ONLY_PREFIXES = [
  '/api/',
  '/auth/',
  '/cart',
  '/checkout',
  '/login',
  '/logout',
  '/sair',
  '/conta',
  '/account',
  '/bem-vindo',
  '/welcome',
  '/pedido/',
  '/order/',
  '/tracking/'
]

function matchesAny(pathname, prefixes) {
  return prefixes.some((prefix) => pathname === prefix || pathname.startsWith(prefix))
}

function isSafeNavigation(pathname) {
  return SAFE_NAVIGATION_PATHS.includes(pathname) || matchesAny(pathname, SAFE_NAVIGATION_PREFIXES)
}

function isCacheableResponse(response) {
  return response && response.ok && response.type === 'basic'
}

async function precachePublicAssets() {
  const cache = await caches.open(CACHE_NAME)
  await Promise.all(PRECACHE_URLS.map(async (url) => {
    const response = await fetch(new Request(url, { credentials: 'omit' }))
    if (isCacheableResponse(response)) await cache.put(url, response)
  }))
}

self.addEventListener('install', (event) => {
  event.waitUntil(precachePublicAssets().then(() => self.skipWaiting()))
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  if (matchesAny(url.pathname, NETWORK_ONLY_PREFIXES)) {
    event.respondWith(fetch(request))
    return
  }

  if (request.mode === 'navigate') {
    if (!isSafeNavigation(url.pathname)) {
      event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)))
      return
    }

    event.respondWith(
      fetch(request)
        .catch(() => caches.match(OFFLINE_URL))
    )
    return
  }

  if (matchesAny(url.pathname, CACHE_FIRST_PREFIXES)) {
    event.respondWith(
      caches.match(request)
        .then((cached) => cached || fetch(request).then((response) => {
          if (isCacheableResponse(response)) {
            const clone = response.clone()
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone))
          }
          return response
        }))
    )
  }
})
`
})
