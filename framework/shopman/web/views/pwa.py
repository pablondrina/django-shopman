from __future__ import annotations

import json

from django.http import HttpRequest, HttpResponse
from django.views import View
from django.views.generic import TemplateView

from shopman.models import Shop


class OfflineView(TemplateView):
    """Offline fallback page shown when network is unavailable."""

    template_name = "storefront/offline.html"


class ManifestView(View):
    """Serve manifest.json with branding from Shop."""

    def get(self, request: HttpRequest) -> HttpResponse:
        config = Shop.load() or Shop()
        manifest = {
            "name": config.brand_name,
            "short_name": config.short_name,
            "description": config.tagline or config.description[:100],
            "start_url": "/menu/",
            "scope": "/",
            "display": "standalone",
            "orientation": "portrait",
            "background_color": config.background_color,
            "theme_color": config.theme_color,
            "lang": "pt-BR",
            "dir": "ltr",
            "categories": ["food", "shopping"],
            "prefer_related_applications": False,
            "icons": [
                {
                    "src": "/static/storefront/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                },
                {
                    "src": "/static/storefront/icon-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                },
                {
                    "src": "/static/storefront/icon-maskable-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable",
                },
            ],
        }
        return HttpResponse(
            json.dumps(manifest),
            content_type="application/manifest+json",
        )


class ServiceWorkerView(View):
    """Serve sw.js with route-based caching, offline fallback, and push stubs."""

    def get(self, request: HttpRequest) -> HttpResponse:
        config = Shop.load() or Shop()
        slug = config.short_name.lower().replace(" ", "-")
        cache_name = f"{slug}-v2"

        js = f"""\
// {config.brand_name} — Service Worker
const CACHE_NAME = '{cache_name}';
const OFFLINE_URL = '/offline/';
const PRECACHE_URLS = [
  '/menu/',
  '/offline/',
  '/manifest.json',
  '/static/storefront/icon-192.png',
];

// --- Route matching ---
const STALE_WHILE_REVALIDATE = ['/menu/', '/produto/'];
const NETWORK_ONLY = ['/checkout/', '/cart/', '/pagamento/', '/api/'];
const CACHE_FIRST_PREFIXES = ['/static/'];

function matchesAny(pathname, prefixes) {{
  return prefixes.some((p) => pathname.startsWith(p));
}}

// --- Install: precache essential assets ---
self.addEventListener('install', (event) => {{
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
}});

// --- Activate: clean old caches ---
self.addEventListener('activate', (event) => {{
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
}});

// --- Fetch: route-based caching strategies ---
self.addEventListener('fetch', (event) => {{
  const {{ request }} = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  const pathname = url.pathname;

  // Network-only: checkout, payment, API — never serve stale
  if (matchesAny(pathname, NETWORK_ONLY)) return;

  // Cache-first: static assets (versioned, immutable)
  if (matchesAny(pathname, CACHE_FIRST_PREFIXES)) {{
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((response) => {{
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        return response;
      }}))
    );
    return;
  }}

  // Stale-while-revalidate: menu, product pages
  if (matchesAny(pathname, STALE_WHILE_REVALIDATE)) {{
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) =>
        cache.match(request).then((cached) => {{
          const fetched = fetch(request).then((response) => {{
            cache.put(request, response.clone());
            return response;
          }}).catch(() => cached);
          return cached || fetched;
        }})
      )
    );
    return;
  }}

  // Default (HTML): network-first, fallback to cache, then offline page
  if (request.headers.get('accept')?.includes('text/html')) {{
    event.respondWith(
      fetch(request)
        .then((response) => {{
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return response;
        }})
        .catch(() => caches.match(request).then((cached) => cached || caches.match(OFFLINE_URL)))
    );
    return;
  }}
}});

// --- Push notifications (stub — activate when backend supports push) ---
self.addEventListener('push', (event) => {{
  if (!event.data) return;
  const data = event.data.json();
  const title = data.title || '{config.brand_name}';
  const options = {{
    body: data.body || '',
    icon: '/static/storefront/icon-192.png',
    badge: '/static/storefront/icon-192.png',
    data: {{ url: data.url || '/menu/' }},
  }};
  event.waitUntil(self.registration.showNotification(title, options));
}});

self.addEventListener('notificationclick', (event) => {{
  event.notification.close();
  const url = event.notification.data?.url || '/menu/';
  event.waitUntil(
    self.clients.matchAll({{ type: 'window' }}).then((clients) => {{
      for (const client of clients) {{
        if (client.url.includes(url) && 'focus' in client) return client.focus();
      }}
      return self.clients.openWindow(url);
    }})
  );
}});"""

        return HttpResponse(js, content_type="application/javascript")
