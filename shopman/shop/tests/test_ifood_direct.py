"""Tests for the iFood DIRECT integration — order fetch/map (WP-3), event
polling (WP-2), and status callbacks (WP-4).

Contracts are verified live in the integration plan; here we lock the mapping
and orchestration logic with mocks + a realistic iFood v1.0 order fixture.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

IFOOD_CFG = {
    "client_id": "cid",
    "client_secret": "csecret",
    "merchant_id": "merchant-abc",
    "api_base": "https://mock-ifood.test",
}


@pytest.fixture
def fake_headers():
    with patch(
        "shopman.shop.services.ifood_auth.get_access_token",
        return_value="fake-token",
    ):
        yield


@pytest.fixture
def ifood_order():
    """A realistic iFood Order Module v1.0 order (documented schema)."""
    return {
        "id": "ifd-order-uuid-1",
        "displayId": "1234",
        "orderType": "DELIVERY",
        "createdAt": "2026-06-30T12:00:00Z",
        "merchant": {"id": "merchant-abc", "name": "Nelson"},
        "customer": {
            "name": "Cliente iFood",
            "phone": {"number": "+55melhorada", "localizer": "9988"},
            "documentNumber": "12345678900",
        },
        "items": [
            {
                "id": "line-1",
                "name": "Pão Francês",
                "externalCode": "PAO-001",
                "quantity": 3,
                "unitPrice": 2.50,
                "totalPrice": 7.50,
                "observations": "bem assado",
                "options": [
                    {"name": "Manteiga", "quantity": 1, "unitPrice": 1.00},
                ],
            },
            {
                "id": "line-2",
                "name": "Café",
                "externalCode": "CAFE-001",
                "quantity": 1,
                "unitPrice": 5.00,
                "totalPrice": 5.00,
            },
        ],
        "delivery": {
            "deliveryDateTime": "2026-06-30T12:45:00Z",
            "deliveryAddress": {
                "formattedAddress": "Rua das Flores, 100 - Centro",
                "streetName": "Rua das Flores",
                "streetNumber": "100",
                "neighborhood": "Centro",
                "city": "Londrina",
                "state": "PR",
                "postalCode": "86010-000",
                "complement": "Apto 2",
                "reference": "portão azul",
            },
        },
    }


# ── WP-3: mapping ──────────────────────────────────────────────────────────────


def test_map_order_maps_items_to_centavos(ifood_order):
    from shopman.shop.services import ifood_orders

    payload = ifood_orders.map_order(ifood_order)

    assert payload["order_code"] == "ifd-order-uuid-1"
    assert payload["merchant_id"] == "merchant-abc"
    assert payload["display_id"] == "1234"
    assert len(payload["items"]) == 2
    pao = payload["items"][0]
    assert pao["sku"] == "PAO-001"
    assert pao["name"] == "Pão Francês"
    assert pao["qty"] == 3
    assert pao["unit_price_q"] == 250  # 2.50 → centavos
    assert pao["meta"]["observations"] == "bem assado"
    assert pao["meta"]["options"][0]["unit_price_q"] == 100


def test_map_order_maps_delivery_and_customer(ifood_order):
    from shopman.shop.services import ifood_orders

    payload = ifood_orders.map_order(ifood_order)

    assert payload["delivery"]["type"] == "DELIVERY"
    assert payload["delivery"]["address"] == "Rua das Flores, 100 - Centro"
    assert payload["delivery"]["complement"] == "Apto 2"
    assert payload["customer"]["name"] == "Cliente iFood"
    assert payload["customer"]["phone_localizer"] == "9988"
    assert payload["customer"]["document"] == "12345678900"


def test_map_order_composes_address_without_formatted():
    from shopman.shop.services import ifood_orders

    order = {
        "id": "x",
        "orderType": "TAKEOUT",
        "delivery": {"deliveryAddress": {
            "streetName": "Rua A", "streetNumber": "5", "city": "Londrina",
        }},
        "items": [],
    }
    payload = ifood_orders.map_order(order)
    assert payload["delivery"]["type"] == "TAKEOUT"
    assert payload["delivery"]["address"] == "Rua A, 5, Londrina"


def test_map_order_passes_through_indoor_type():
    from shopman.shop.services import ifood_orders

    payload = ifood_orders.map_order({"id": "x", "orderType": "INDOOR", "items": []})
    assert payload["delivery"]["type"] == "INDOOR"


def test_map_order_against_real_captured_order():
    """Lock the mapping against a REAL Developer-Portal test order (captured live
    2026-07-01). This is the schema validation WP-3 needed and mocks can't give.
    """
    import json
    from pathlib import Path

    from shopman.shop.services import ifood_orders

    raw = json.loads(
        (Path(__file__).parent / "fixtures" / "ifood_order_real.json").read_text()
    )
    payload = ifood_orders.map_order(raw)

    assert payload["order_code"] == "12e51038-0f2a-4ff0-8608-48733a861489"
    assert payload["display_id"] == "5800"
    assert payload["is_test"] is True
    assert payload["order_timing"] == "IMMEDIATE"

    # Combo pricing: line total must include options + customizations.
    simple, combo = payload["items"]
    assert simple["sku"] == "4994"
    assert simple["unit_price_q"] == 500
    assert simple["line_total_q"] == 500
    assert combo["sku"] == "1437"
    assert combo["unit_price_q"] == 500        # base unitPrice
    assert combo["line_total_q"] == 1600       # totalPrice (incl. options+customizations)
    assert combo["meta"]["item_type"] == "COMBO_V2"
    # 3rd-level customizations captured under the MAIN option.
    main_opt = next(o for o in combo["meta"]["options"] if o["group"] == "Meu sanduíche favorito")
    assert len(main_opt["customizations"]) == 3

    # Financial breakdown preserved (centavos).
    assert payload["totals"]["order_amount_q"] == 2700
    assert payload["totals"]["delivery_fee_q"] == 500
    assert payload["totals"]["additional_fees_q"] == 100
    assert payload["payments"]["prepaid_q"] == 2700
    assert len(payload["payments"]["methods"]) == 2

    # Delivery / customer specifics.
    assert payload["delivery"]["pickup_code"] == "4157"
    assert payload["customer"]["phone_localizer"] == "89338721"
    assert "gerado automaticamente" in payload["notes"]


def test_map_order_handles_string_phone_and_missing_external_code():
    from shopman.shop.services import ifood_orders

    order = {
        "id": "x",
        "customer": {"name": "A", "phone": "+554399"},
        "items": [{"id": "line-9", "name": "Item", "quantity": 1, "unitPrice": 1.0}],
    }
    payload = ifood_orders.map_order(order)
    assert payload["customer"]["phone"] == "+554399"
    # No externalCode → falls back to the line id so ingest still has a sku.
    assert payload["items"][0]["sku"] == "line-9"


def test_ingest_real_order_uses_order_amount_as_total(db):
    """End-to-end: mapping + ingest of the real order → total_q == orderAmount
    (grand total: subtotal 21,00 + entrega 5,00 + taxa 1,00 = 27,00).
    """
    import json
    from pathlib import Path

    from shopman.shop.models import Channel
    from shopman.shop.services import ifood_ingest, ifood_orders

    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood", "is_active": True})
    raw = json.loads(
        (Path(__file__).parent / "fixtures" / "ifood_order_real.json").read_text()
    )
    order = ifood_ingest.ingest(ifood_orders.map_order(raw))

    assert order.total_q == 2700  # orderAmount, not the 2100 items subtotal
    assert order.data["ifood"]["is_test"] is True
    assert order.data["ifood"]["totals"]["order_amount_q"] == 2700
    assert order.data["ifood"]["pickup_code"] == "4157"


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_fetch_order_success(fake_headers):
    from shopman.shop.services import ifood_orders

    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = {"id": "abc"}
        result = ifood_orders.fetch_order("abc")

    assert result == {"id": "abc"}
    url = mock_get.call_args[0][0]
    assert url == "https://mock-ifood.test/order/v1.0/orders/abc"


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_fetch_order_404_raises(fake_headers):
    from shopman.shop.services import ifood_orders

    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=404, text="OrderNotFound")
        with pytest.raises(ifood_orders.IFoodOrderFetchError):
            ifood_orders.fetch_order("nope")


def test_fetch_order_without_oauth_raises():
    from shopman.shop.services import ifood_orders

    with patch("shopman.shop.services.ifood_auth.get_access_token", return_value=None):
        with pytest.raises(ifood_orders.IFoodOrderFetchError):
            ifood_orders.fetch_order("abc")


# ── WP-2: polling + ack ─────────────────────────────────────────────────────────


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_poll_204_returns_empty(fake_headers):
    from shopman.shop.services import ifood_events

    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=204)
        assert ifood_events.poll() == []
        # x-polling-merchants header scopes the poll to our merchant.
        assert mock_get.call_args[1]["headers"]["x-polling-merchants"] == "merchant-abc"


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_poll_200_returns_events(fake_headers):
    from shopman.shop.services import ifood_events

    events = [{"id": "e1", "code": "PLC", "orderId": "o1"}]
    with patch("requests.get") as mock_get:
        resp = MagicMock(status_code=200)
        resp.json.return_value = events
        mock_get.return_value = resp
        assert ifood_events.poll() == events


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_acknowledge_posts_event_ids(fake_headers):
    from shopman.shop.services import ifood_events

    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=202)
        assert ifood_events.acknowledge(["e1", "e2"]) is True
        body = mock_post.call_args[1]["json"]
        assert body == [{"id": "e1"}, {"id": "e2"}]
        assert mock_post.call_args[0][0].endswith("/order/v1.0/events/acknowledgment")


def test_acknowledge_empty_is_noop():
    from shopman.shop.services import ifood_events

    with patch("requests.post") as mock_post:
        assert ifood_events.acknowledge([]) is True
        mock_post.assert_not_called()


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_process_events_ingests_placed_and_acks(db, fake_headers, ifood_order):
    from shopman.shop.models import Channel
    from shopman.shop.services import ifood_events

    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood", "is_active": True})
    events = [{"id": "evt-1", "fullCode": "PLACED", "orderId": "ifd-order-uuid-1"}]

    with patch("shopman.shop.services.ifood_orders.fetch_order", return_value=ifood_order):
        with patch("shopman.shop.services.ifood_events.acknowledge", return_value=True) as mock_ack:
            summary = ifood_events.process_events(events)

    assert summary["ingested"] == 1
    assert summary["failed"] == 0
    mock_ack.assert_called_once_with(["evt-1"])
    from shopman.orderman.models import Order
    assert Order.objects.filter(channel_ref="ifood", external_ref="ifd-order-uuid-1").exists()


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_process_events_dedupes_existing_order(db, fake_headers, ifood_order):
    from shopman.shop.models import Channel
    from shopman.shop.services import ifood_events, ifood_ingest, ifood_orders

    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood", "is_active": True})
    ifood_ingest.ingest(ifood_orders.map_order(ifood_order))
    events = [{"id": "evt-2", "fullCode": "PLACED", "orderId": "ifd-order-uuid-1"}]

    with patch("shopman.shop.services.ifood_orders.fetch_order") as mock_fetch:
        with patch("shopman.shop.services.ifood_events.acknowledge", return_value=True):
            summary = ifood_events.process_events(events)

    assert summary["deduped"] == 1
    assert summary["ingested"] == 0
    mock_fetch.assert_not_called()  # existing order → no refetch


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_process_events_ignores_non_placed_codes(db, fake_headers):
    from shopman.shop.services import ifood_events

    events = [{"id": "evt-3", "fullCode": "CONFIRMED", "orderId": "o9"}]
    with patch("shopman.shop.services.ifood_events.acknowledge", return_value=True) as mock_ack:
        summary = ifood_events.process_events(events)

    assert summary["ignored"] == 1
    mock_ack.assert_called_once_with(["evt-3"])


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_process_events_failed_ingest_not_acked(db, fake_headers):
    from shopman.shop.models import Channel
    from shopman.shop.services import ifood_events

    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood", "is_active": True})
    events = [{"id": "evt-4", "fullCode": "PLACED", "orderId": "boom"}]

    with patch("shopman.shop.services.ifood_orders.fetch_order", side_effect=RuntimeError("500")):
        with patch("shopman.shop.services.ifood_events.acknowledge", return_value=True) as mock_ack:
            summary = ifood_events.process_events(events)

    assert summary["failed"] == 1
    assert summary["ingested"] == 0
    mock_ack.assert_not_called()  # failure → leave un-acked for redelivery


# ── WP-4: status callbacks ───────────────────────────────────────────────────────


def test_action_for_status_mapping():
    from shopman.shop.services import ifood_callbacks

    assert ifood_callbacks.action_for_status("confirmed") == "confirm"
    assert ifood_callbacks.action_for_status("ready") == "readyToPickup"
    assert ifood_callbacks.action_for_status("dispatched") == "dispatch"
    assert ifood_callbacks.action_for_status("cancelled") == "requestCancellation"
    assert ifood_callbacks.action_for_status("preparing") is None


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_send_action_accepts_202(fake_headers):
    from shopman.shop.services import ifood_callbacks

    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=202)
        ifood_callbacks.confirm("o1")
        assert mock_post.call_args[0][0].endswith("/order/v1.0/orders/o1/confirm")


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_send_action_non_2xx_raises(fake_headers):
    from shopman.shop.services import ifood_callbacks

    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=409, text="conflict")
        with pytest.raises(ifood_callbacks.IFoodCallbackError):
            ifood_callbacks.dispatch("o1")


@override_settings(SHOPMAN_IFOOD={**IFOOD_CFG, "cancellation_default_code": "501"})
def test_send_for_status_cancellation_uses_configured_code(fake_headers):
    from shopman.shop.services import ifood_callbacks

    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=202)
        sent = ifood_callbacks.send_for_status("o1", "cancelled", cancellation_reason="sem estoque")
        assert sent is True
        assert mock_post.call_args[0][0].endswith("/requestCancellation")
        body = mock_post.call_args[1]["json"]
        assert body["cancellationCode"] == "501"
        assert body["reason"] == "sem estoque"


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_request_cancellation_without_code_raises(fake_headers):
    """No configured code → loud failure, never a guessed code."""
    from shopman.shop.services import ifood_callbacks

    with patch("requests.post") as mock_post:
        with pytest.raises(ifood_callbacks.IFoodCallbackError):
            ifood_callbacks.request_cancellation("o1")
        mock_post.assert_not_called()


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_fetch_cancellation_reasons(fake_headers):
    from shopman.shop.services import ifood_callbacks

    reasons = [{"cancelCodeId": "501", "description": "Item indisponível"}]
    with patch("requests.get") as mock_get:
        resp = MagicMock(status_code=200)
        resp.json.return_value = reasons
        mock_get.return_value = resp
        assert ifood_callbacks.fetch_cancellation_reasons("o1") == reasons
        assert mock_get.call_args[0][0].endswith("/order/v1.0/orders/o1/cancellationReasons")


def test_send_for_status_unmapped_returns_false():
    from shopman.shop.services import ifood_callbacks

    assert ifood_callbacks.send_for_status("o1", "preparing") is False


def test_status_handler_raises_transient_on_callback_error():
    from shopman.orderman.exceptions import DirectiveTransientError

    from shopman.shop.handlers.ifood_status import IFoodStatusCallbackHandler
    from shopman.shop.services import ifood_callbacks

    handler = IFoodStatusCallbackHandler()
    msg = MagicMock(payload={"ifood_order_id": "o1", "status": "confirmed"})
    with patch(
        "shopman.shop.services.ifood_callbacks.send_for_status",
        side_effect=ifood_callbacks.IFoodCallbackError("down"),
    ):
        with pytest.raises(DirectiveTransientError):
            handler.handle(message=msg, ctx={})


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_signal_receiver_enqueues_directive_for_ifood_order(db):
    from shopman.orderman.models import Directive

    from shopman.shop.directives import IFOOD_STATUS_CALLBACK
    from shopman.shop.handlers.ifood_status import on_order_status_changed

    order = MagicMock(channel_ref="ifood", status="confirmed", ref="ORD-1",
                      external_ref="ifd-1", data={})
    on_order_status_changed(sender=None, order=order, event_type="status_changed", actor="auto")

    d = Directive.objects.filter(topic=IFOOD_STATUS_CALLBACK).first()
    assert d is not None
    assert d.payload["ifood_order_id"] == "ifd-1"
    assert d.payload["status"] == "confirmed"

    # Idempotent: same transition twice → still one directive.
    on_order_status_changed(sender=None, order=order, event_type="status_changed", actor="auto")
    assert Directive.objects.filter(topic=IFOOD_STATUS_CALLBACK).count() == 1


@override_settings(SHOPMAN_IFOOD=IFOOD_CFG)
def test_signal_receiver_ignores_non_ifood_orders(db):
    from shopman.orderman.models import Directive

    from shopman.shop.directives import IFOOD_STATUS_CALLBACK
    from shopman.shop.handlers.ifood_status import on_order_status_changed

    order = MagicMock(channel_ref="web", status="confirmed", ref="ORD-2",
                      external_ref="", data={})
    on_order_status_changed(sender=None, order=order, event_type="status_changed", actor="auto")
    assert Directive.objects.filter(topic=IFOOD_STATUS_CALLBACK).count() == 0


# ── WP-5: signed event webhook ───────────────────────────────────────────────────

import hashlib  # noqa: E402
import hmac  # noqa: E402
import json  # noqa: E402

WEBHOOK_CFG = {**IFOOD_CFG, "webhook_hmac_secret": "sign-secret"}
EVENTS_URL = "/api/webhooks/ifood/events/"


def _sign(raw: bytes, secret: str = "sign-secret") -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


@override_settings(SHOPMAN_IFOOD=WEBHOOK_CFG)
def test_events_webhook_valid_signature_processes(db):
    from rest_framework.test import APIClient

    events = [{"id": "e1", "fullCode": "CONFIRMED", "orderId": "o1"}]
    raw = json.dumps(events).encode()

    with patch("shopman.shop.services.ifood_events.process_events", return_value={"polled": 1}) as mock_proc:
        resp = APIClient().post(
            EVENTS_URL, data=raw, content_type="application/json",
            HTTP_X_IFOOD_SIGNATURE=_sign(raw),
        )

    assert resp.status_code == 200
    mock_proc.assert_called_once_with(events)


@override_settings(SHOPMAN_IFOOD=WEBHOOK_CFG)
def test_events_webhook_invalid_signature_401(db):
    from rest_framework.test import APIClient

    raw = json.dumps([{"id": "e1"}]).encode()
    with patch("shopman.shop.services.ifood_events.process_events") as mock_proc:
        resp = APIClient().post(
            EVENTS_URL, data=raw, content_type="application/json",
            HTTP_X_IFOOD_SIGNATURE="deadbeef",
        )

    assert resp.status_code == 401
    mock_proc.assert_not_called()


@override_settings(SHOPMAN_IFOOD={**IFOOD_CFG, "webhook_hmac_secret": ""})
def test_events_webhook_unconfigured_secret_401(db):
    from rest_framework.test import APIClient

    raw = json.dumps([{"id": "e1"}]).encode()
    resp = APIClient().post(
        EVENTS_URL, data=raw, content_type="application/json",
        HTTP_X_IFOOD_SIGNATURE=_sign(raw),
    )
    assert resp.status_code == 401


@override_settings(SHOPMAN_IFOOD=WEBHOOK_CFG)
def test_events_webhook_accepts_single_event_object(db):
    from rest_framework.test import APIClient

    event = {"id": "e1", "fullCode": "PLACED", "orderId": "o1"}
    raw = json.dumps(event).encode()
    with patch("shopman.shop.services.ifood_events.process_events", return_value={"polled": 1}) as mock_proc:
        resp = APIClient().post(
            EVENTS_URL, data=raw, content_type="application/json",
            HTTP_X_IFOOD_SIGNATURE=_sign(raw),
        )
    assert resp.status_code == 200
    mock_proc.assert_called_once_with([event])
