from __future__ import annotations

import json

from django.http import HttpRequest, HttpResponse
from django.views import View

from ..models import StorefrontConfig


class ManifestView(View):
    """Serve manifest.json with branding from StorefrontConfig."""

    def get(self, request: HttpRequest) -> HttpResponse:
        config = StorefrontConfig.load()
        manifest = {
            "name": config.brand_name,
            "short_name": config.short_name,
            "start_url": "/menu/",
            "display": "standalone",
            "background_color": config.background_color,
            "theme_color": config.theme_color,
            "icons": [
                {"src": "/static/storefront/icon-192.svg", "sizes": "192x192", "type": "image/svg+xml"},
                {"src": "/static/storefront/icon-512.svg", "sizes": "512x512", "type": "image/svg+xml"},
            ],
        }
        return HttpResponse(
            json.dumps(manifest),
            content_type="application/manifest+json",
        )


class ServiceWorkerView(View):
    """Serve sw.js with parameterized cache name from StorefrontConfig."""

    def get(self, request: HttpRequest) -> HttpResponse:
        config = StorefrontConfig.load()
        slug = config.short_name.lower().replace(" ", "-")
        cache_name = f"{slug}-v1"

        js = f"""\
const CACHE_NAME = '{cache_name}';
const STATIC_ASSETS = ['/menu/', '/manifest.json', '/static/storefront/icon-192.svg'];
self.addEventListener('install', (event) => {{ event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))); self.skipWaiting(); }});
self.addEventListener('activate', (event) => {{ event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))); self.clients.claim(); }});
self.addEventListener('fetch', (event) => {{
  const {{ request }} = event;
  if (request.method !== 'GET') return;
  if (request.headers.get('accept')?.includes('text/html')) {{
    event.respondWith(fetch(request).then((response) => {{ const clone = response.clone(); caches.open(CACHE_NAME).then((cache) => cache.put(request, clone)); return response; }}).catch(() => caches.match(request)));
    return;
  }}
  if (request.url.includes('/static/')) {{ event.respondWith(caches.match(request).then((cached) => cached || fetch(request))); return; }}
}});"""

        return HttpResponse(js, content_type="application/javascript")
