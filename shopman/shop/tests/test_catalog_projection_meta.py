"""
Meta Catalog Projection adapter (Arc E) — payload, batching, retract, 429, dry-run.

All offline: ``requests.post`` is mocked and ``meta_auth`` yields a fake Bearer, so
the suite runs green without any Meta credential. Live is gated behind
``META_CATALOG_PROJECTION=1`` + real ``SHOPMAN_META``; the adapter is off by default.
"""

from __future__ import annotations

from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.test import override_settings
from shopman.offerman.protocols.projection import ProjectedItem

from shopman.shop.adapters import catalog_projection_meta as meta
from shopman.shop.adapters.catalog_projection_meta import (
    MetaCatalogProjection,
    MetaRateLimitError,
    build_batch_requests,
    build_retract_requests,
)

_META_CFG = {
    "catalog_id": "cat-123",
    "access_token": "tok-xyz",
    "api_version": "v21.0",
    "api_base": "https://graph.mock.test",
    "currency": "BRL",
    "store_url": "https://loja.test",
    "default_brand": "Nelson",
    "batch_size": 5000,
    "timeout": 10,
}


def _item(**over) -> ProjectedItem:
    base = {
        "sku": "PAO",
        "name": "Pão Francês",
        "description": "Crocante",
        "unit": "un",
        "price_q": 350,
        "is_published": True,
        "is_sellable": True,
        "image_url": "https://cdn.test/pao.jpg",
        "category": "paes",
        "metadata": {"social": {"brand": "Nelson", "google_product_category": "Bakery", "gtin": ""}},
    }
    base.update(over)
    return ProjectedItem(**base)


class _Resp:
    def __init__(self, status: int = 200, headers: dict | None = None):
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def fake_headers():
    with mock.patch.object(
        meta.meta_auth, "authorized_headers", return_value={"Authorization": "Bearer tok"}
    ):
        yield


# ── inert without credentials ──────────────────────────────────────────────────


@override_settings(SHOPMAN_META=dict(_META_CFG, access_token="", catalog_id=""))
def test_project_inert_without_credentials():
    with mock.patch.object(meta.requests, "post") as post:
        result = MetaCatalogProjection().project([_item()], channel="meta")
    assert result.success is False
    assert "não configurado" in result.errors[0]
    post.assert_not_called()


# ── project payload ─────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_META=_META_CFG)
def test_project_posts_expected_batch(fake_headers):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp(200)

    with mock.patch.object(meta.requests, "post", fake_post):
        result = MetaCatalogProjection().project([_item()], channel="meta")

    assert result.success is True
    assert result.projected == 1
    assert captured["url"] == "https://graph.mock.test/v21.0/cat-123/items_batch"
    body = captured["json"]
    assert body["item_type"] == "PRODUCT_ITEM"
    assert body["allow_upsert"] is True
    req = body["requests"][0]
    assert req["method"] == "UPDATE"
    assert req["retailer_id"] == "PAO"
    data = req["data"]
    assert data["title"] == "Pão Francês"
    assert data["availability"] == "in stock"
    assert data["condition"] == "new"
    assert data["link"] == "https://loja.test/PAO"
    assert data["image_link"] == "https://cdn.test/pao.jpg"
    assert data["brand"] == "Nelson"
    assert data["google_product_category"] == "Bakery"
    assert data["custom_label_0"] == "paes"


@override_settings(SHOPMAN_META=_META_CFG)
def test_price_is_integer_cents_plus_currency(fake_headers):
    reqs = build_batch_requests([_item(price_q=1299)], _META_CFG)
    data = reqs[0]["data"]
    assert data["price"] == 1299  # inteiro em centavos, não string "12.99 BRL"
    assert isinstance(data["price"], int)
    assert data["currency"] == "BRL"


@override_settings(SHOPMAN_META=_META_CFG)
def test_out_of_stock_when_not_sellable():
    reqs = build_batch_requests([_item(is_sellable=False)], _META_CFG)
    assert reqs[0]["data"]["availability"] == "out of stock"


@override_settings(SHOPMAN_META=_META_CFG)
def test_default_brand_when_pim_has_none():
    reqs = build_batch_requests([_item(metadata={"social": {}})], _META_CFG)
    assert reqs[0]["data"]["brand"] == "Nelson"  # cai no default_brand da config


@override_settings(SHOPMAN_META=_META_CFG)
def test_gallery_becomes_additional_image_link():
    reqs = build_batch_requests(
        [_item(metadata={"gallery": ["https://cdn.test/pao.jpg", "https://cdn.test/2.jpg", "https://cdn.test/3.jpg"]})],
        _META_CFG,
    )
    # a imagem principal é filtrada; só as extras entram, separadas por vírgula
    assert reqs[0]["data"]["additional_image_link"] == "https://cdn.test/2.jpg,https://cdn.test/3.jpg"


# ── batching ────────────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_META=dict(_META_CFG, batch_size=2))
def test_batching_chunks_requests(fake_headers):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(len(json["requests"]))
        return _Resp(200)

    items = [_item(sku=f"P{i}") for i in range(5)]
    with mock.patch.object(meta.requests, "post", fake_post):
        result = MetaCatalogProjection().project(items, channel="meta")

    assert result.projected == 5
    assert calls == [2, 2, 1]  # 5 itens / batch 2 → 3 chamadas


# ── retract ─────────────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_META=_META_CFG)
def test_retract_updates_availability_out_of_stock(fake_headers):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return _Resp(200)

    with mock.patch.object(meta.requests, "post", fake_post):
        result = MetaCatalogProjection().retract(["PAO", "BOLO"], channel="meta")

    assert result.success is True
    assert result.projected == 2
    reqs = captured["json"]["requests"]
    assert [r["retailer_id"] for r in reqs] == ["PAO", "BOLO"]
    assert all(r["method"] == "UPDATE" for r in reqs)
    assert all(r["data"] == {"availability": "out of stock"} for r in reqs)


def test_build_retract_requests_pure():
    reqs = build_retract_requests(["A", "B"])
    assert reqs == [
        {"method": "UPDATE", "retailer_id": "A", "data": {"availability": "out of stock"}},
        {"method": "UPDATE", "retailer_id": "B", "data": {"availability": "out of stock"}},
    ]


# ── rate limit ──────────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_META=_META_CFG)
def test_rate_limit_raises_with_retry_after(fake_headers):
    def fake_post(url, json=None, headers=None, timeout=None):
        return _Resp(429, headers={"Retry-After": "42"})

    with mock.patch.object(meta.requests, "post", fake_post):
        with pytest.raises(MetaRateLimitError) as exc:
            MetaCatalogProjection().project([_item()], channel="meta")
    assert exc.value.retry_after == 42


@override_settings(SHOPMAN_META=_META_CFG)
def test_http_error_degrades_to_result_error(fake_headers):
    def fake_post(url, json=None, headers=None, timeout=None):
        return _Resp(500)

    with mock.patch.object(meta.requests, "post", fake_post):
        result = MetaCatalogProjection().project([_item()], channel="meta")
    assert result.success is False
    assert "PAO" in result.errors[0]


# ── dry-run command ─────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_META=_META_CFG)
def test_dry_run_command_emits_batch_json():
    out = StringIO()
    with mock.patch(
        "shopman.offerman.service.CatalogService.get_projection_items",
        return_value=[_item()],
    ):
        call_command("sync_catalog_meta", "--dry-run", stdout=out)
    output = out.getvalue()
    assert "Dry run — 1 item(s)" in output
    assert '"retailer_id": "PAO"' in output
    assert '"availability": "in stock"' in output
    assert "No changes sent to Meta (dry run)." in output


def test_dry_run_command_empty_listing():
    out = StringIO()
    with mock.patch(
        "shopman.offerman.service.CatalogService.get_projection_items",
        return_value=[],
    ):
        call_command("sync_catalog_meta", "--dry-run", stdout=out)
    assert "Nothing to sync" in out.getvalue()


# ── auth service ────────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_META=dict(_META_CFG, access_token="", catalog_id=""))
def test_meta_auth_inert_without_credentials():
    from shopman.shop.services import meta_auth

    assert meta_auth.is_configured() is False
    assert meta_auth.authorized_headers() is None


@override_settings(SHOPMAN_META=_META_CFG)
def test_meta_auth_bearer_header():
    from shopman.shop.services import meta_auth

    assert meta_auth.is_configured() is True
    headers = meta_auth.authorized_headers({"Content-Type": "application/json"})
    assert headers["Authorization"] == "Bearer tok-xyz"
    assert headers["Content-Type"] == "application/json"
    assert headers["User-Agent"] == meta_auth.USER_AGENT
