"""Webhook Machine: auth fail-closed, idempotência e transições via funil."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from shopman.orderman.models import Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.adapters import courier_mock
from shopman.shop.models import Shop
from shopman.shop.services import courier

pytestmark = pytest.mark.django_db

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"
MACHINE = {"webhook_token": "tok-machine-1"}


@pytest.fixture(autouse=True)
def _clean_state():
    courier_mock.reset()
    cache.clear()
    yield
    courier_mock.reset()


@pytest.fixture
def shop():
    return Shop.objects.create(
        name="Nelson",
        city="Londrina",
        state_code="PR",
        latitude=-23.34,
        longitude=-51.15,
    )


def _order_with_ride(ref="WH-1") -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"S-{ref}",
        status=Order.Status.READY,
        snapshot={"items": []},
        data={
            "fulfillment_type": "delivery",
            "customer": {"name": "Ana", "phone": "5543999990000"},
            "delivery_address_structured": {"latitude": -23.31, "longitude": -51.16},
            "courier": {
                "provider": "machine",
                "id_mch": "184532",
                "status": "D",
                "requested_at": "2026-07-07T10:00:00-03:00",
            },
        },
        total_q=5000,
    )
    courier_mock.dispatch({"paradas": [{"id_externo": ref}]})  # popula o mock p/ get_details
    courier_mock.rides()["184532"] = courier_mock.rides().pop(f"MOCK-{ref}")
    return order


def _url(token="tok-machine-1"):
    url = reverse("webhooks:machine-webhook")
    return f"{url}?token={token}" if token else url


# ── autenticação ────────────────────────────────────────────────────


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_rejects_without_token():
    resp = APIClient().post(_url(token=""), {"id_mch": "1", "status": "E"}, format="json")
    assert resp.status_code == 401


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_rejects_wrong_token():
    resp = APIClient().post(_url(token="errado"), {"id_mch": "1", "status": "E"}, format="json")
    assert resp.status_code == 401


@override_settings(SHOPMAN_MACHINE={"webhook_token": ""})
def test_rejects_everything_when_token_unconfigured():
    # Fail-closed: sem token configurado o endpoint rejeita até o token "vazio".
    resp = APIClient().post(_url(token=""), {}, format="json")
    assert resp.status_code == 401


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_accepts_token_via_header():
    client = APIClient()
    resp = client.post(
        reverse("webhooks:machine-webhook"),
        {"foo": "bar"},
        format="json",
        HTTP_X_MACHINE_WEBHOOK_TOKEN="tok-machine-1",
    )
    assert resp.status_code == 202  # autenticado; payload não reconhecido


# ── payload defensivo ───────────────────────────────────────────────


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_unrecognized_payload_is_accepted_not_rejected():
    resp = APIClient().post(_url(), {"algo": "desconhecido"}, format="json")
    assert resp.status_code == 202
    assert resp.data["status"] == "unrecognized"


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_unknown_ride_returns_ok(shop):
    resp = APIClient().post(_url(), {"id_mch": "999999", "status": "E"}, format="json")
    assert resp.status_code == 200
    assert resp.data["kind"] == "unknown_ride"


# ── eventos de status ───────────────────────────────────────────────


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_status_e_advances_order_to_dispatched(shop):
    order = _order_with_ride()
    resp = APIClient().post(_url(), {"id_mch": "184532", "status": "E"}, format="json")
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED
    assert courier.get_block(order)["status"] == "E"
    assert courier.get_block(order)["last_source"] == "webhook"


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_status_f_marks_delivered(shop):
    order = _order_with_ride()
    client = APIClient()
    client.post(_url(), {"id_mch": "184532", "status": "E"}, format="json")
    resp = client.post(_url(), {"id_mch": "184532", "status": "F"}, format="json")
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status in (Order.Status.DELIVERED, Order.Status.COMPLETED)


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_status_n_alerts_operator(shop):
    order = _order_with_ride()
    resp = APIClient().post(_url(), {"id_mch": "184532", "status": "N"}, format="json")
    assert resp.status_code == 200
    order.refresh_from_db()
    assert not courier.has_active_ride(order)
    assert OperatorAlert.objects.filter(type="courier_not_attended", order_ref=order.ref).exists()


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_replay_same_status_is_noop(shop):
    order = _order_with_ride()
    client = APIClient()
    first = client.post(_url(), {"id_mch": "184532", "status": "E"}, format="json")
    assert first.data["kind"] == "status"
    replay = client.post(_url(), {"id_mch": "184532", "status": "E"}, format="json")
    assert replay.status_code == 200
    assert replay.data["kind"] == "replay"
    order.refresh_from_db()
    assert order.events.filter(type="courier_status").count() == 1


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_alternate_id_and_status_keys_are_understood(shop):
    order = _order_with_ride()
    resp = APIClient().post(
        _url(), {"solicitacao_id": 184532, "situacao": "e"}, format="json"
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED


# ── eventos de posição ──────────────────────────────────────────────


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_position_event_goes_to_cache_not_order(shop):
    order = _order_with_ride()
    before = order.updated_at
    resp = APIClient().post(
        _url(), {"id_mch": "184532", "lat": "-23.305", "lng": "-51.162"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["kind"] == "position"
    assert cache.get("courier:pos:184532") == {"lat": "-23.305", "lng": "-51.162"}
    order.refresh_from_db()
    assert order.updated_at == before  # posição nunca escreve no Order
