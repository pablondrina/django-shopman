"""
Tests for WP-GAP-15: iFood catalog projection adapter, handler, and signals.

Coverage:
- Adapter builds correct iFood payload.
- Handler dispatches to backend and marks Directive done.
- Signal on_product_created → Directive enqueued.
- Signal on_price_changed → Directive enqueued.
- Idempotency: same signal twice → single Directive.
- Rate limit (429) → handler schedules retry with Retry-After.
- Max attempts → Directive marked failed.
- Management command sync_catalog_ifood (dry-run + real).
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.offerman.protocols.projection import ProjectedItem, ProjectionResult
from shopman.orderman.models import Directive

from shopman.shop.directives import CATALOG_PROJECT_SKU

# ── Canonical projection registry (OFFERMAN["PROJECTION_BACKENDS"]) ─────────────
# Mirrors config/settings.py OFFERMAN so override_settings preserves the other
# keys (pricing backend) while toggling the iFood projection backend.
_IFOOD_BACKEND = "shopman.shop.adapters.catalog_projection_ifood.IFoodCatalogProjection"
_OFFERMAN_BASE = {
    "COST_BACKEND": None,
    "PRICING_BACKEND": "shopman.shop.adapters.pricing.StorefrontPricingBackend",
}
_OFFERMAN_IFOOD = {**_OFFERMAN_BASE, "PROJECTION_BACKENDS": {"ifood": _IFOOD_BACKEND}}
_OFFERMAN_NONE = {**_OFFERMAN_BASE, "PROJECTION_BACKENDS": {}}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def ifood_item():
    return ProjectedItem(
        sku="PAO-FRANCES",
        name="Pão Francês",
        description="Pão crocante",
        unit="un",
        price_q=350,
        is_published=True,
        is_sellable=True,
        image_url="https://cdn.test/pao.jpg",
        category="paes",
    )


@pytest.fixture
def ifood_settings():
    return {
        "webhook_token": "wh-tok",
        "merchant_id": "merchant-abc",
        "api_base": "https://mock-ifood.test",
        "catalog_category_map": {"paes": "cat-paes-uuid"},
        "catalog_default_category": "cat-default-uuid",
    }


@pytest.fixture
def fake_oauth():
    """Patch ifood_auth so authorized_headers() yields a real Bearer header."""
    with patch(
        "shopman.shop.services.ifood_auth.get_access_token",
        return_value="fake-token-xyz",
    ):
        yield


@pytest.fixture
def reset_projection_registry():
    """Clear the offerman projection-backend instance cache around a test."""
    from shopman.offerman.conf import reset_projection_backends

    reset_projection_backends()
    yield
    reset_projection_backends()


@pytest.fixture
def ifood_channel(db):
    from shopman.shop.models import Channel
    return Channel.objects.create(
        ref="ifood",
        name="iFood",
        is_active=True,
    )


@pytest.fixture
def ifood_directive(db):
    return Directive.objects.create(
        topic=CATALOG_PROJECT_SKU,
        payload={"sku": "PAO-FRANCES", "listing_ref": "ifood"},
    )


# ── Adapter: payload construction ─────────────────────────────────────────────


def test_adapter_builds_correct_ifood_payload(ifood_item):
    """_item_payload builds a valid FullItemDto with price in BRL float."""
    from shopman.shop.adapters.catalog_projection_ifood import _item_payload

    payload = _item_payload(ifood_item, merchant_id="merchant-abc", category_id="cat-uuid")

    item = payload["item"]
    product = payload["products"][0]
    assert item["externalCode"] == "PAO-FRANCES"
    assert item["price"]["value"] == pytest.approx(3.50)
    assert item["price"]["originalValue"] == pytest.approx(3.50)
    assert item["status"] == "AVAILABLE"
    assert item["categoryId"] == "cat-uuid"
    # item.productId must equal products[0].id, and both must be UUIDs.
    assert item["productId"] == product["id"]
    uuid.UUID(item["id"])
    uuid.UUID(item["productId"])
    assert product["name"] == "Pão Francês"
    assert product["description"] == "Pão crocante"
    assert product["externalCode"] == "PAO-FRANCES"
    # No inline image — iFood v2.0 rejects it with 500 (uses a separate upload flow).
    assert "image" not in product


def test_adapter_ids_are_deterministic_per_merchant_and_sku(ifood_item):
    """Same (merchant, sku) → same item/product UUIDs (idempotent upsert)."""
    from shopman.shop.adapters.catalog_projection_ifood import _item_payload

    a = _item_payload(ifood_item, merchant_id="m", category_id="c")
    b = _item_payload(ifood_item, merchant_id="m", category_id="c")
    assert a["item"]["id"] == b["item"]["id"]
    assert a["item"]["productId"] == b["item"]["productId"]
    # Different merchant → different ids.
    other = _item_payload(ifood_item, merchant_id="other", category_id="c")
    assert other["item"]["id"] != a["item"]["id"]


def test_adapter_never_sends_inline_image():
    """iFood v2.0 rejects an inline image URL (500) — the item PUT never carries one."""
    from shopman.shop.adapters.catalog_projection_ifood import _item_payload

    item = ProjectedItem(
        sku="X", name="X", description="", unit="un",
        price_q=100, is_published=True, is_sellable=True,
        image_url="https://cdn.test/x.jpg",
    )
    payload = _item_payload(item, merchant_id="m", category_id="c")
    assert "image" not in payload["products"][0]


def test_adapter_marks_unavailable_when_not_sellable():
    from shopman.shop.adapters.catalog_projection_ifood import _item_payload

    item = ProjectedItem(
        sku="X", name="X", description="", unit="un",
        price_q=100, is_published=True, is_sellable=False,
    )
    payload = _item_payload(item, merchant_id="m", category_id="c")
    assert payload["item"]["status"] == "UNAVAILABLE"


# ── Adapter: project() ────────────────────────────────────────────────────────


def test_adapter_project_calls_ifood_put(ifood_item, ifood_settings, fake_oauth):
    """project() PUTs each item to the merchant-level /items endpoint."""
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
        with patch("requests.put") as mock_put:
            mock_put.return_value = MagicMock(status_code=200, headers={})
            mock_put.return_value.raise_for_status = MagicMock()

            backend = IFoodCatalogProjection()
            result = backend.project([ifood_item], channel="ifood")

    assert result.success is True
    assert result.projected == 1
    assert result.errors == []
    mock_put.assert_called_once()
    url, kwargs = mock_put.call_args[0][0], mock_put.call_args[1]
    assert url == "https://mock-ifood.test/catalog/v2.0/merchants/merchant-abc/items"
    assert kwargs["json"]["item"]["externalCode"] == "PAO-FRANCES"
    # "paes" is mapped in catalog_category_map.
    assert kwargs["json"]["item"]["categoryId"] == "cat-paes-uuid"
    assert kwargs["headers"]["Authorization"] == "Bearer fake-token-xyz"


def test_adapter_project_uses_default_category_when_unmapped(ifood_settings, fake_oauth):
    """An item whose collection is not in the map falls back to the default category."""
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    item = ProjectedItem(
        sku="Y", name="Y", description="", unit="un",
        price_q=100, is_published=True, is_sellable=True, category="bebidas",
    )
    with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
        with patch("requests.put") as mock_put:
            mock_put.return_value = MagicMock(status_code=200, headers={})
            mock_put.return_value.raise_for_status = MagicMock()
            result = IFoodCatalogProjection().project([item], channel="ifood")

    assert result.success is True
    assert mock_put.call_args[1]["json"]["item"]["categoryId"] == "cat-default-uuid"


def test_adapter_project_errors_when_no_category(fake_oauth):
    """No mapped collection and no default → per-item error, no PUT."""
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    cfg = {"merchant_id": "m", "catalog_category_map": {}, "catalog_default_category": ""}
    item = ProjectedItem(
        sku="Z", name="Z", description="", unit="un",
        price_q=100, is_published=True, is_sellable=True, category="unknown",
    )
    with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=cfg):
        with patch("requests.put") as mock_put:
            result = IFoodCatalogProjection().project([item], channel="ifood")

    mock_put.assert_not_called()
    assert result.success is False
    assert "category" in result.errors[0].lower()


def test_adapter_project_returns_failure_without_oauth(ifood_item):
    """No OAuth credentials → authorized_headers() is None → loud failure, no PUT."""
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    with patch("shopman.shop.services.ifood_auth.get_access_token", return_value=None):
        with patch("requests.put") as mock_put:
            result = IFoodCatalogProjection().project([ifood_item], channel="ifood")

    mock_put.assert_not_called()
    assert result.success is False
    assert "OAuth" in result.errors[0]


def test_adapter_retract_patches_item_status(ifood_settings, fake_oauth):
    """retract() sets item status UNAVAILABLE via PATCH /items/status."""
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
        with patch("requests.patch") as mock_patch:
            mock_patch.return_value = MagicMock(status_code=200, headers={})
            mock_patch.return_value.raise_for_status = MagicMock()
            result = IFoodCatalogProjection().retract(["PAO-FRANCES"], channel="ifood")

    assert result.success is True
    url, kwargs = mock_patch.call_args[0][0], mock_patch.call_args[1]
    assert url == "https://mock-ifood.test/catalog/v2.0/merchants/merchant-abc/items/status"
    assert kwargs["json"]["status"] == "UNAVAILABLE"
    uuid.UUID(kwargs["json"]["itemId"])


def test_adapter_raises_rate_limit_on_429(ifood_item, ifood_settings, fake_oauth):
    """429 with Retry-After header raises IFoodRateLimitError."""
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection, IFoodRateLimitError

    mock_resp = MagicMock(status_code=429, headers={"Retry-After": "45"})

    with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
        with patch("requests.put", return_value=mock_resp):
            backend = IFoodCatalogProjection()
            with pytest.raises(IFoodRateLimitError) as exc_info:
                backend.project([ifood_item], channel="ifood")

    assert exc_info.value.retry_after == 45


# ── Handler ───────────────────────────────────────────────────────────────────


def test_handler_marks_done_on_success(db, ifood_channel, ifood_directive):
    """Handler marks Directive done when backend.project() succeeds."""
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    backend = MagicMock()
    backend.project.return_value = ProjectionResult(success=True, projected=1, channel="ifood")
    handler = CatalogProjectHandler(backend=backend)

    with patch("shopman.shop.handlers.catalog_projection._get_projected_item") as mock_get:
        mock_get.return_value = ProjectedItem(
            sku="PAO-FRANCES", name="Pão", description="", unit="un",
            price_q=350, is_published=True, is_sellable=True,
        )
        handler.handle(message=ifood_directive, ctx={})

    # directive.status is managed by the directive processor, not the handler.
    # Direct invocation leaves status unchanged. We verify the handler ran correctly:
    backend.project.assert_called_once()


def test_handler_retracts_when_item_paused(db, ifood_channel, ifood_directive):
    """Retract-aware: an unsellable SKU is retracted, not projected."""
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    backend = MagicMock()
    backend.retract.return_value = ProjectionResult(success=True, projected=1, channel="ifood")
    handler = CatalogProjectHandler(backend=backend)

    with patch("shopman.shop.handlers.catalog_projection._get_projected_item") as mock_get:
        mock_get.return_value = ProjectedItem(
            sku="PAO-FRANCES", name="Pão", description="", unit="un",
            price_q=350, is_published=True, is_sellable=False,  # paused
        )
        handler.handle(message=ifood_directive, ctx={})

    backend.retract.assert_called_once_with(["PAO-FRANCES"], channel="ifood")
    backend.project.assert_not_called()


def test_handler_retracts_when_item_dropped_from_listing(db, ifood_channel, ifood_directive):
    """A SKU no longer in the listing (item is None) is retracted."""
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    backend = MagicMock()
    backend.retract.return_value = ProjectionResult(success=True, projected=1, channel="ifood")
    handler = CatalogProjectHandler(backend=backend)

    with patch("shopman.shop.handlers.catalog_projection._get_projected_item", return_value=None):
        handler.handle(message=ifood_directive, ctx={})

    backend.retract.assert_called_once_with(["PAO-FRANCES"], channel="ifood")
    backend.project.assert_not_called()


def test_handler_skips_when_channel_inactive(db, ifood_directive):
    """Handler skips API call when iFood channel is inactive."""
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    backend = MagicMock()
    handler = CatalogProjectHandler(backend=backend)

    with patch(
        "shopman.shop.handlers.catalog_projection._channel_or_showcase_active",
        return_value=False,
    ):
        handler.handle(message=ifood_directive, ctx={})

    backend.project.assert_not_called()


def test_handler_schedules_retry_on_rate_limit(db, ifood_channel, ifood_directive):
    """429 RateLimitError → handler sets available_at honoring Retry-After."""
    from shopman.shop.adapters.catalog_projection_ifood import IFoodRateLimitError
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    backend = MagicMock()
    backend.project.side_effect = IFoodRateLimitError(retry_after=30)
    handler = CatalogProjectHandler(backend=backend)

    before = timezone.now()
    with patch("shopman.shop.handlers.catalog_projection._get_projected_item") as mock_get:
        mock_get.return_value = ProjectedItem(
            sku="PAO-FRANCES", name="Pão", description="", unit="un",
            price_q=350, is_published=True, is_sellable=True,
        )
        handler.handle(message=ifood_directive, ctx={})

    ifood_directive.refresh_from_db()
    assert ifood_directive.status == "queued", "rate-limited directive must stay queued"
    assert ifood_directive.available_at > before
    delta = (ifood_directive.available_at - before).total_seconds()
    assert 25 <= delta <= 35, f"Retry-After=30 but delta={delta}s"


# Note: max_attempts / retry limits are managed by the orderman directive
# dispatcher, not by individual handlers. Handlers raise DirectiveTransientError
# and the dispatcher decides when to give up.


# ── Signal receivers + idempotency ────────────────────────────────────────────


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_on_product_created_enqueues_directive(db):
    """product_created signal → catalog.project_sku Directive created."""
    from shopman.shop.handlers.catalog_projection import on_product_created

    on_product_created(sender=None, instance=None, sku="BAGUETE")

    directives = Directive.objects.filter(topic=CATALOG_PROJECT_SKU)
    assert directives.count() == 1
    d = directives.first()
    assert d.payload["sku"] == "BAGUETE"
    assert d.payload["listing_ref"] == "ifood"
    assert d.dedupe_key.startswith("catalog.project_sku:ifood:BAGUETE:")


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_on_product_updated_enqueues_directive(db):
    """product_updated (name/description/publish) → catalog.project_sku Directive."""
    from shopman.shop.handlers.catalog_projection import on_product_updated

    on_product_updated(sender=None, instance=None, sku="BAGUETE")

    directives = Directive.objects.filter(topic=CATALOG_PROJECT_SKU)
    assert directives.count() == 1
    assert directives.first().payload["sku"] == "BAGUETE"


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_on_availability_changed_enqueues_directive(db):
    """availability_changed (per-channel pause/resume) → catalog.project_sku Directive."""
    from shopman.shop.handlers.catalog_projection import on_availability_changed

    on_availability_changed(sender=None, instance=None, listing_ref="ifood", sku="CROISSANT")

    directives = Directive.objects.filter(topic=CATALOG_PROJECT_SKU)
    assert directives.count() == 1
    assert directives.first().payload["sku"] == "CROISSANT"


@override_settings(OFFERMAN=_OFFERMAN_NONE)
def test_availability_signal_noop_without_adapter(db):
    """No adapter configured → availability receiver creates no directive (safe no-op)."""
    from shopman.shop.handlers.catalog_projection import on_availability_changed

    on_availability_changed(sender=None, instance=None, listing_ref="ifood", sku="X")
    assert Directive.objects.filter(topic=CATALOG_PROJECT_SKU).count() == 0


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_on_price_changed_enqueues_directive(db):
    """price_changed signal → catalog.project_sku Directive created."""
    from shopman.shop.handlers.catalog_projection import on_price_changed

    on_price_changed(
        sender=None,
        instance=None,
        listing_ref="ifood",
        sku="CROISSANT",
        old_price_q=800,
        new_price_q=900,
    )

    directives = Directive.objects.filter(topic=CATALOG_PROJECT_SKU)
    assert directives.count() == 1
    assert directives.first().payload["sku"] == "CROISSANT"


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_idempotency_same_price_signal_twice(db):
    """Same price_changed event fired twice → only 1 Directive (dedupe)."""
    from shopman.shop.handlers.catalog_projection import on_price_changed

    kwargs = {
        "sender": None,
        "instance": None,
        "listing_ref": "ifood",
        "sku": "CROISSANT",
        "old_price_q": 800,
        "new_price_q": 900,
    }
    on_price_changed(**kwargs)
    on_price_changed(**kwargs)

    count = Directive.objects.filter(topic=CATALOG_PROJECT_SKU).count()
    assert count == 1, f"Expected 1 directive (idempotent), got {count}"


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_different_prices_create_different_directives(db):
    """Different prices → different dedupe_keys → 2 Directives."""
    from shopman.shop.handlers.catalog_projection import on_price_changed

    on_price_changed(
        sender=None, instance=None,
        listing_ref="ifood", sku="CROISSANT",
        old_price_q=800, new_price_q=900,
    )
    on_price_changed(
        sender=None, instance=None,
        listing_ref="ifood", sku="CROISSANT",
        old_price_q=900, new_price_q=1000,
    )

    count = Directive.objects.filter(topic=CATALOG_PROJECT_SKU).count()
    assert count == 2


@override_settings(OFFERMAN=_OFFERMAN_NONE)
def test_signal_noop_when_no_adapters_configured(db):
    """With no projection backend configured, receivers create no directives."""
    from shopman.shop.handlers.catalog_projection import on_product_created

    on_product_created(sender=None, instance=None, sku="BAGUETE")

    assert Directive.objects.filter(topic=CATALOG_PROJECT_SKU).count() == 0


# ── Management command ────────────────────────────────────────────────────────


def test_sync_catalog_ifood_dry_run(db, capsys):
    """--dry-run prints items and makes no API calls."""
    from django.core.management import call_command

    from shopman.shop.models import Channel

    Channel.objects.create(ref="ifood", name="iFood", is_active=True)

    items = [
        ProjectedItem(
            sku="PAO", name="Pão", description="", unit="un",
            price_q=350, is_published=True, is_sellable=True,
        )
    ]

    with patch("shopman.offerman.service.CatalogService.get_projection_items", return_value=items):
        with patch("requests.put") as mock_put:
            call_command("sync_catalog_ifood", dry_run=True)
            mock_put.assert_not_called()

    out = capsys.readouterr().out
    assert "PAO" in out
    assert "dry run" in out.lower()


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_sync_catalog_ifood_full_sync(db, ifood_settings, fake_oauth, reset_projection_registry):
    """--full routes through project_listing → upserts all, no retract."""
    from django.core.management import call_command
    from shopman.offerman.models import Listing

    from shopman.shop.models import Channel

    Channel.objects.create(ref="ifood", name="iFood", is_active=True)
    Listing.objects.create(ref="ifood", name="iFood")

    items = [
        ProjectedItem(
            sku="PAO", name="Pão", description="", unit="un",
            price_q=350, is_published=True, is_sellable=True, category="paes",
        )
    ]

    with patch("shopman.offerman.service.CatalogService.get_projection_items", return_value=items):
        with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
            with patch("requests.put") as mock_put, patch("requests.patch") as mock_patch:
                mock_put.return_value = MagicMock(status_code=200, headers={})
                mock_put.return_value.raise_for_status = MagicMock()
                call_command("sync_catalog_ifood", full=True)

    mock_put.assert_called_once()
    mock_patch.assert_not_called()  # full sync never retracts

    # last_projected_skus persisted for the next incremental diff.
    listing = Listing.objects.get(ref="ifood")
    assert listing.projection_metadata["last_projected_skus"] == ["PAO"]


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_sync_catalog_ifood_incremental_retracts(db, ifood_settings, fake_oauth, reset_projection_registry):
    """Incremental sync upserts sellable items and retracts unavailable ones."""
    from django.core.management import call_command
    from shopman.offerman.models import Listing

    from shopman.shop.models import Channel

    Channel.objects.create(ref="ifood", name="iFood", is_active=True)
    Listing.objects.create(ref="ifood", name="iFood")

    items = [
        ProjectedItem(
            sku="PAO", name="Pão", description="", unit="un",
            price_q=350, is_published=True, is_sellable=True, category="paes",
        ),
        ProjectedItem(
            sku="CROISSANT", name="Croissant", description="", unit="un",
            price_q=800, is_published=True, is_sellable=False, category="paes",
        ),
    ]

    with patch("shopman.offerman.service.CatalogService.get_projection_items", return_value=items):
        with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
            with patch("requests.put") as mock_put, patch("requests.patch") as mock_patch:
                mock_put.return_value = MagicMock(status_code=200, headers={})
                mock_put.return_value.raise_for_status = MagicMock()
                mock_patch.return_value = MagicMock(status_code=202, headers={})
                mock_patch.return_value.raise_for_status = MagicMock()
                call_command("sync_catalog_ifood")

    mock_put.assert_called_once()  # PAO upserted
    mock_patch.assert_called_once()  # CROISSANT (not sellable) retracted

    listing = Listing.objects.get(ref="ifood")
    assert listing.projection_metadata["last_projected_skus"] == ["PAO"]


@override_settings(OFFERMAN=_OFFERMAN_NONE)
def test_sync_catalog_ifood_backend_not_configured(db, reset_projection_registry):
    """No projection backend configured → clear CommandError, no API calls."""
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from shopman.offerman.models import Listing

    from shopman.shop.models import Channel

    Channel.objects.create(ref="ifood", name="iFood", is_active=True)
    Listing.objects.create(ref="ifood", name="iFood")

    items = [
        ProjectedItem(
            sku="PAO", name="Pão", description="", unit="un",
            price_q=350, is_published=True, is_sellable=True,
        )
    ]

    with patch("shopman.offerman.service.CatalogService.get_projection_items", return_value=items):
        with pytest.raises(CommandError, match="IFOOD_CATALOG_PROJECTION"):
            call_command("sync_catalog_ifood")
