"""WP-AV-10 — SSE push emitter and partial endpoint tests.

Verifies:
1. Stockman/Offerman model changes fire ``send_event`` to every channel that
   lists the SKU, with the correct event type and payload shape.
2. Cache invalidation accompanies each emit so the next ``/api/v1/availability``
   call sees fresh data.
3. ``/storefront/sku/<sku>/state/`` returns the badge HTML and a parseable
   ``HX-Trigger`` header carrying the canonical state.

End-to-end tests against a live SSE consumer require a multi-process bridge
(Redis), which is documented as the production requirement; here we
mock ``send_event`` and assert on the call surface.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.urls import reverse
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.stockman.models import Hold

from shopman.shop.models import Channel, Shop


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _shop(db):
    Shop.objects.get_or_create(name="Test Shop")


@pytest.fixture
def web_channel(db):
    return Channel.objects.create(ref="web", name="Web", is_active=True)


@pytest.fixture
def pdv_channel(db):
    return Channel.objects.create(ref="pdv", name="Balcão", is_active=True)


@pytest.fixture
def baguete(db):
    return Product.objects.create(
        sku="BAGUETE",
        name="Baguete",
        base_price_q=500,
        is_published=True,
        is_sellable=True,
    )


@pytest.fixture
def listings_for_baguete(baguete, web_channel, pdv_channel):
    """BAGUETE is listed on both 'web' and 'pdv'."""
    web_listing = Listing.objects.create(ref="web", name="Web", is_active=True)
    pdv_listing = Listing.objects.create(
        ref="pdv", name="Balcão", is_active=True,
    )
    ListingItem.objects.create(
        listing=web_listing, product=baguete, price_q=500,
        is_published=True, is_sellable=True,
    )
    ListingItem.objects.create(
        listing=pdv_listing, product=baguete, price_q=500,
        is_published=True, is_sellable=True,
    )
    return [web_listing, pdv_listing]


# ── Emit helper unit tests ──────────────────────────────────────────


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_emit_targets_every_channel_listing_the_sku(
    mock_send, baguete, listings_for_baguete,
):
    """``_emit_for_sku`` resolves channels via ListingItem and emits to each."""
    from shopman.shop.handlers._sse_emitters import _emit_for_sku

    _emit_for_sku("BAGUETE", event_type="stock-update")

    channels_called = sorted(call.args[0] for call in mock_send.call_args_list)
    assert channels_called == ["stock-pdv", "stock-web"]
    for call in mock_send.call_args_list:
        assert call.args[1] == "stock-update"
        assert call.args[2] == {"sku": "BAGUETE"}


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_emit_falls_back_to_all_active_channels_when_sku_has_no_listing(
    mock_send, baguete, web_channel, pdv_channel,
):
    """SKUs without Listing membership broadcast to every active channel."""
    from shopman.shop.handlers._sse_emitters import _emit_for_sku

    _emit_for_sku("BAGUETE", event_type="stock-update")

    channels_called = sorted(call.args[0] for call in mock_send.call_args_list)
    assert channels_called == ["stock-pdv", "stock-web"]


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_emit_invalidates_per_channel_availability_cache(
    mock_send, baguete, listings_for_baguete,
):
    """The cache used by ``/api/v1/availability/`` must be cleared on every emit."""
    from shopman.shop.handlers._sse_emitters import _emit_for_sku

    cache.set("availability:BAGUETE:web", {"stale": True}, 30)
    cache.set("availability:BAGUETE:pdv", {"stale": True}, 30)
    cache.set("availability:BAGUETE:default", {"stale": True}, 30)

    _emit_for_sku("BAGUETE", event_type="stock-update")

    assert cache.get("availability:BAGUETE:web") is None
    assert cache.get("availability:BAGUETE:pdv") is None
    assert cache.get("availability:BAGUETE:default") is None


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_emit_carries_extra_payload_keys(
    mock_send, baguete, listings_for_baguete,
):
    from shopman.shop.handlers._sse_emitters import _emit_for_sku

    _emit_for_sku(
        "BAGUETE",
        event_type="product-paused",
        extra={"is_sellable": False},
    )

    payload = mock_send.call_args_list[0].args[2]
    assert payload == {"sku": "BAGUETE", "is_sellable": False}


# ── Signal-driven emits ─────────────────────────────────────────────


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_hold_save_emits_stock_update(
    mock_send, baguete, listings_for_baguete,
):
    Hold.objects.create(
        sku="BAGUETE",
        quantity=Decimal("1"),
        status="pending",
        target_date=date.today(),
    )
    types = {call.args[1] for call in mock_send.call_args_list}
    skus = {call.args[2]["sku"] for call in mock_send.call_args_list}
    assert "stock-update" in types
    assert "BAGUETE" in skus


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_product_pause_emits_product_paused(
    mock_send, baguete, listings_for_baguete,
):
    mock_send.reset_mock()  # ignore creation-time signals from fixtures

    baguete.is_sellable = False
    baguete.save()

    pause_calls = [
        c for c in mock_send.call_args_list if c.args[1] == "product-paused"
    ]
    assert pause_calls, "expected at least one product-paused emit"
    assert pause_calls[0].args[2] == {"sku": "BAGUETE", "is_sellable": False}


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_product_save_without_sellable_change_skips_emit(
    mock_send, baguete, listings_for_baguete,
):
    mock_send.reset_mock()

    baguete.name = "Baguete tradicional"
    baguete.save()

    pause_calls = [
        c for c in mock_send.call_args_list if c.args[1] == "product-paused"
    ]
    assert pause_calls == []


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_listing_item_unpublish_emits_listing_changed(
    mock_send, baguete, listings_for_baguete,
):
    mock_send.reset_mock()

    item = ListingItem.objects.filter(
        listing__ref="web", product=baguete,
    ).first()
    item.is_published = False
    item.save()

    listing_calls = [
        c for c in mock_send.call_args_list if c.args[1] == "listing-changed"
    ]
    assert listing_calls, "expected listing-changed emit"
    assert listing_calls[0].args[2] == {"sku": "BAGUETE"}


# ── Endpoint test ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_sku_state_endpoint_returns_badge_and_hx_trigger(
    client, baguete, listings_for_baguete,
):
    url = reverse("storefront:sku_state", kwargs={"sku": "BAGUETE"})
    response = client.get(f"{url}?channel_ref=web")

    assert response.status_code == 200
    assert "HX-Trigger" in response.headers

    payload = json.loads(response.headers["HX-Trigger"])
    assert "sku-state" in payload
    detail = payload["sku-state"]
    assert detail["sku"] == "BAGUETE"
    assert detail["channel_ref"] == "web"
    assert "availability" in detail
    assert "can_add_to_cart" in detail


@pytest.mark.django_db
def test_sku_state_endpoint_404_for_unknown_sku(client):
    url = reverse("storefront:sku_state", kwargs={"sku": "NOPE"})
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_sku_state_endpoint_marks_paused_product_unavailable(
    client, baguete, listings_for_baguete,
):
    Product.objects.filter(sku="BAGUETE").update(is_sellable=False)

    url = reverse("storefront:sku_state", kwargs={"sku": "BAGUETE"})
    response = client.get(f"{url}?channel_ref=web")

    detail = json.loads(response.headers["HX-Trigger"])["sku-state"]
    assert detail["availability"] == "unavailable"
    assert detail["can_add_to_cart"] is False
    assert b"Indispon" in response.content
