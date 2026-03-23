"""Tests for PWA views: manifest, service worker, offline page."""
from __future__ import annotations

import json

import pytest
from django.test import Client


@pytest.fixture
def client_db(db):
    """A Django test client with database access."""
    return Client()


# ── OfflineView ──────────────────────────────────────────────────────


class TestOfflineView:
    def test_get_returns_200(self, client_db):
        resp = client_db.get("/offline/")
        assert resp.status_code == 200

    def test_contains_offline_message(self, client_db):
        resp = client_db.get("/offline/")
        content = resp.content.decode()
        assert "Sem conexão" in content

    def test_contains_retry_button(self, client_db):
        resp = client_db.get("/offline/")
        content = resp.content.decode()
        assert "Tentar novamente" in content
        assert "window.location.reload()" in content

    def test_contains_brand_name(self, client_db):
        resp = client_db.get("/offline/")
        content = resp.content.decode()
        assert "Nelson Boulangerie" in content


# ── ManifestView ─────────────────────────────────────────────────────


class TestManifestView:
    def test_content_type(self, client_db):
        resp = client_db.get("/manifest.json")
        assert resp["Content-Type"] == "application/manifest+json"

    def test_required_fields(self, client_db):
        resp = client_db.get("/manifest.json")
        data = json.loads(resp.content)
        assert data["name"] == "Nelson Boulangerie"
        assert data["short_name"] == "Nelson"
        assert data["start_url"] == "/menu/"
        assert data["display"] == "standalone"

    def test_icons_are_png(self, client_db):
        resp = client_db.get("/manifest.json")
        data = json.loads(resp.content)
        icons = data["icons"]
        assert len(icons) == 3
        for icon in icons:
            assert icon["type"] == "image/png"
            assert icon["src"].endswith(".png")

    def test_has_maskable_icon(self, client_db):
        resp = client_db.get("/manifest.json")
        data = json.loads(resp.content)
        maskable = [i for i in data["icons"] if i.get("purpose") == "maskable"]
        assert len(maskable) == 1

    def test_enriched_fields(self, client_db):
        resp = client_db.get("/manifest.json")
        data = json.loads(resp.content)
        assert data["lang"] == "pt-BR"
        assert data["dir"] == "ltr"
        assert data["orientation"] == "portrait"
        assert data["scope"] == "/"
        assert "food" in data["categories"]
        assert data["prefer_related_applications"] is False

    def test_description_from_tagline(self, client_db):
        resp = client_db.get("/manifest.json")
        data = json.loads(resp.content)
        assert data["description"] == "Padaria Artesanal"


# ── ServiceWorkerView ────────────────────────────────────────────────


class TestServiceWorkerView:
    def test_content_type(self, client_db):
        resp = client_db.get("/sw.js")
        assert resp["Content-Type"] == "application/javascript"

    def test_contains_cache_name(self, client_db):
        resp = client_db.get("/sw.js")
        content = resp.content.decode()
        assert "CACHE_NAME = 'nelson-v2'" in content

    def test_precaches_offline_url(self, client_db):
        resp = client_db.get("/sw.js")
        content = resp.content.decode()
        assert "'/offline/'" in content

    def test_offline_fallback_in_fetch(self, client_db):
        resp = client_db.get("/sw.js")
        content = resp.content.decode()
        assert "caches.match(OFFLINE_URL)" in content

    def test_stale_while_revalidate_routes(self, client_db):
        resp = client_db.get("/sw.js")
        content = resp.content.decode()
        assert "STALE_WHILE_REVALIDATE" in content
        assert "'/menu/'" in content
        assert "'/produto/'" in content

    def test_network_only_routes(self, client_db):
        resp = client_db.get("/sw.js")
        content = resp.content.decode()
        assert "NETWORK_ONLY" in content
        assert "'/checkout/'" in content
        assert "'/pagamento/'" in content
        assert "'/api/'" in content

    def test_network_only_not_cached(self, client_db):
        """Network-only routes should return early without caching."""
        resp = client_db.get("/sw.js")
        content = resp.content.decode()
        # The NETWORK_ONLY block just returns (browser default fetch)
        assert "if (matchesAny(pathname, NETWORK_ONLY)) return;" in content

    def test_push_listener_stub(self, client_db):
        resp = client_db.get("/sw.js")
        content = resp.content.decode()
        assert "self.addEventListener('push'" in content
        assert "showNotification" in content

    def test_notification_click_listener(self, client_db):
        resp = client_db.get("/sw.js")
        content = resp.content.decode()
        assert "self.addEventListener('notificationclick'" in content
        assert "openWindow" in content

    def test_precaches_menu(self, client_db):
        resp = client_db.get("/sw.js")
        content = resp.content.decode()
        assert "'/menu/'" in content

    def test_precaches_png_icon(self, client_db):
        resp = client_db.get("/sw.js")
        content = resp.content.decode()
        assert "icon-192.png" in content
