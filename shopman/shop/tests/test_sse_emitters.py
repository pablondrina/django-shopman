"""WP-AV-10 — SSE push emitter and partial endpoint tests.

Verifies:
1. Stockman/Offerman model changes fire ``send_event`` to every channel that
   lists the SKU, with the correct event type and payload shape.
2. Cache invalidation accompanies each emit so the next ``/api/v1/availability``
   call sees fresh data.
3. Every publish waits for the COMMIT (``transaction.on_commit``) — an event
   delivered before COMMIT would make the client's canonical refetch read
   stale state (ADR-016).

End-to-end tests against a live SSE consumer require a multi-process bridge
(Redis), which is documented as the production requirement; here we
mock ``send_event`` and assert on the call surface. Emits are deferred to
``on_commit``, so tests run the mutation inside
``django_capture_on_commit_callbacks(execute=True)``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.cache import cache
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Order
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
    mock_send, baguete, listings_for_baguete, django_capture_on_commit_callbacks,
):
    """``_emit_for_sku`` resolves channels via ListingItem and emits to each."""
    from shopman.shop.handlers._sse_emitters import _emit_for_sku

    with django_capture_on_commit_callbacks(execute=True):
        _emit_for_sku("BAGUETE", event_type="stock-update")

    channels_called = sorted(call.args[0] for call in mock_send.call_args_list)
    assert channels_called == ["stock-catalog", "stock-pdv", "stock-web"]
    for call in mock_send.call_args_list:
        assert call.args[1] == "stock-update"
        assert call.args[2] == {"sku": "BAGUETE"}


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_emit_waits_for_transaction_commit(
    mock_send, baguete, listings_for_baguete, django_capture_on_commit_callbacks,
):
    """No publish (nor cache invalidation) may happen before COMMIT (ADR-016)."""
    from shopman.shop.handlers._sse_emitters import _emit_for_sku

    cache.set("availability:BAGUETE:web", {"stale": True}, 30)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        _emit_for_sku("BAGUETE", event_type="stock-update")
        assert mock_send.call_count == 0
        assert cache.get("availability:BAGUETE:web") == {"stale": True}

    assert callbacks, "emit must be deferred via transaction.on_commit"
    for callback in callbacks:
        callback()
    assert mock_send.call_count > 0
    assert cache.get("availability:BAGUETE:web") is None


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_emit_falls_back_to_all_active_channels_when_sku_has_no_listing(
    mock_send, baguete, web_channel, pdv_channel, django_capture_on_commit_callbacks,
):
    """SKUs without Listing membership broadcast to every active channel."""
    from shopman.shop.handlers._sse_emitters import _emit_for_sku

    with django_capture_on_commit_callbacks(execute=True):
        _emit_for_sku("BAGUETE", event_type="stock-update")

    channels_called = sorted(call.args[0] for call in mock_send.call_args_list)
    assert channels_called == ["stock-catalog", "stock-pdv", "stock-web"]


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_emit_invalidates_per_channel_availability_cache(
    mock_send, baguete, listings_for_baguete, django_capture_on_commit_callbacks,
):
    """The cache used by ``/api/v1/availability/`` must be cleared on every emit."""
    from shopman.shop.handlers._sse_emitters import _emit_for_sku

    cache.set("availability:BAGUETE:web", {"stale": True}, 30)
    cache.set("availability:BAGUETE:pdv", {"stale": True}, 30)
    cache.set("availability:BAGUETE:default", {"stale": True}, 30)

    with django_capture_on_commit_callbacks(execute=True):
        _emit_for_sku("BAGUETE", event_type="stock-update")

    assert cache.get("availability:BAGUETE:web") is None
    assert cache.get("availability:BAGUETE:pdv") is None
    assert cache.get("availability:BAGUETE:default") is None


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_emit_carries_extra_payload_keys(
    mock_send, baguete, listings_for_baguete, django_capture_on_commit_callbacks,
):
    from shopman.shop.handlers._sse_emitters import _emit_for_sku

    with django_capture_on_commit_callbacks(execute=True):
        _emit_for_sku(
            "BAGUETE",
            event_type="product-paused",
            extra={"is_sellable": False},
        )

    payload = mock_send.call_args_list[0].args[2]
    assert payload == {"sku": "BAGUETE", "is_sellable": False}


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_payment_change_emits_order_and_backstage_updates(
    mock_send, web_channel, django_capture_on_commit_callbacks,
):
    from shopman.shop.handlers._sse_emitters import _on_payment_changed

    order = Order.objects.create(
        ref="PAY-SSE-1",
        channel_ref=web_channel.ref,
        status=Order.Status.NEW,
        total_q=1000,
    )

    class Intent:
        status = "captured"

    with django_capture_on_commit_callbacks(execute=True):
        _on_payment_changed(sender=None, intent=Intent(), order_ref=order.ref)

    assert any(
        call.args[0] == "order-PAY-SSE-1"
        and call.args[1] == "order-update"
        and call.args[2]["payment_status"] == "captured"
        for call in mock_send.call_args_list
    )
    assert any(
        call.args[0] == "backstage-orders-main"
        and call.args[1] == "backstage-orders-update"
        and call.args[2]["kind"] == "payment_changed"
        for call in mock_send.call_args_list
    )


# ── Signal-driven emits ─────────────────────────────────────────────


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_hold_save_emits_stock_update(
    mock_send, baguete, listings_for_baguete, django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True):
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
    mock_send, baguete, listings_for_baguete, django_capture_on_commit_callbacks,
):
    mock_send.reset_mock()  # ignore creation-time signals from fixtures

    with django_capture_on_commit_callbacks(execute=True):
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
    mock_send, baguete, listings_for_baguete, django_capture_on_commit_callbacks,
):
    mock_send.reset_mock()

    with django_capture_on_commit_callbacks(execute=True):
        baguete.name = "Baguete tradicional"
        baguete.save()

    pause_calls = [
        c for c in mock_send.call_args_list if c.args[1] == "product-paused"
    ]
    assert pause_calls == []


@pytest.mark.django_db
@patch("django_eventstream.send_event")
def test_listing_item_unpublish_emits_listing_changed(
    mock_send, baguete, listings_for_baguete, django_capture_on_commit_callbacks,
):
    mock_send.reset_mock()

    with django_capture_on_commit_callbacks(execute=True):
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
