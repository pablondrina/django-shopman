"""Courier (Machine): despacho async, funil de status e transições derivadas.

Usa o adapter mock (``courier_mock``) — sem rede. O funil ``apply_status`` é o
mesmo para webhook e polling, então estes testes cobrem as duas vias.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import override_settings
from shopman.orderman.models import Directive, Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.adapters import courier_mock
from shopman.shop.directives import COURIER_DISPATCH, COURIER_SYNC, DELIVERY_AUTO_COMPLETE
from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler
from shopman.shop.handlers.courier_sync import CourierSyncHandler
from shopman.shop.models import Shop
from shopman.shop.services import courier

pytestmark = pytest.mark.django_db

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"


@pytest.fixture(autouse=True)
def _clean_state():
    courier_mock.reset()
    cache.clear()
    yield
    courier_mock.reset()


@pytest.fixture
def shop():
    return Shop.objects.create(
        name="Nelson Boulangerie",
        route="Av. Madre Leônia Milito",
        street_number="446",
        neighborhood="Bela Suíça",
        city="Londrina",
        state_code="PR",
        formatted_address="Av. Madre Leônia Milito, 446 - Bela Suíça, Londrina - PR",
        latitude=-23.3405,
        longitude=-51.1580,
    )


def _delivery_order(ref="CR-1", status=Order.Status.READY, **data_overrides) -> Order:
    data = {
        "fulfillment_type": "delivery",
        "customer": {"name": "Ana Lima", "phone": "5543999990000"},
        "delivery_address_structured": {
            "route": "Rua das Flores",
            "street_number": "123",
            "neighborhood": "Centro",
            "city": "Londrina",
            "state_code": "PR",
            "formatted_address": "Rua das Flores 123 - Centro - Londrina",
            "delivery_instructions": "Portão azul",
            "latitude": -23.31,
            "longitude": -51.16,
        },
        "delivery_fee_q": 800,
    }
    data.update(data_overrides)
    return Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"S-{ref}",
        status=status,
        snapshot={"items": []},
        data=data,
        total_q=5000,
    )


def _run_dispatch(order) -> None:
    directive = Directive.objects.filter(topic=COURIER_DISPATCH, payload__order_ref=order.ref).first()
    assert directive is not None, "despacho não foi enfileirado"
    CourierDispatchHandler().handle(message=directive, ctx={})
    order.refresh_from_db()


# ── request_dispatch ────────────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_request_dispatch_queues_directive_once(shop):
    order = _delivery_order()
    d1 = courier.request_dispatch(order, actor="test")
    d2 = courier.request_dispatch(order, actor="test")
    assert d1 is not None
    assert d2 is not None and d2.pk == d1.pk  # idempotente: reusa o enfileirado
    assert d1.dedupe_key == f"courier.dispatch:{order.ref}:1"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_request_dispatch_noop_for_pickup_and_wrong_status(shop):
    pickup = _delivery_order(ref="CR-P", fulfillment_type="pickup")
    assert courier.request_dispatch(pickup, actor="test") is None

    preparing = _delivery_order(ref="CR-W", status=Order.Status.PREPARING)
    assert courier.request_dispatch(preparing, actor="test") is None


def test_request_dispatch_noop_without_adapter(shop):
    order = _delivery_order()
    assert courier.request_dispatch(order, actor="test") is None
    assert not Directive.objects.filter(topic=COURIER_DISPATCH).exists()


# ── handler de despacho ─────────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_dispatch_handler_opens_ride_and_schedules_sync(shop):
    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    _run_dispatch(order)

    block = courier.get_block(order)
    assert block["id_mch"] == f"MOCK-{order.ref}"
    assert block["provider"] == "machine"
    assert block["status"] == "D"
    assert block["estimate"] == {"value_q": 1250, "minutes": 18.0, "km": 4.2}
    assert Directive.objects.filter(topic=COURIER_SYNC, payload__order_ref=order.ref).exists()

    # payload enviado à Machine: partida = loja, parada = cliente
    ride = courier_mock.rides()[block["id_mch"]]
    payload = ride["payload"]
    assert payload["partida"]["endereco"] == "Av. Madre Leônia Milito 446"
    assert payload["paradas"][0]["id_externo"] == order.ref
    assert payload["paradas"][0]["nome_cliente_parada"] == "Ana Lima"
    assert payload["paradas"][0]["telefone_cliente_parada"] == "5543999990000"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_dispatch_handler_replay_is_noop(shop):
    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    _run_dispatch(order)
    first_id = courier.get_block(order)["id_mch"]

    directive = Directive.objects.filter(topic=COURIER_DISPATCH).first()
    CourierDispatchHandler().handle(message=directive, ctx={})  # replay at-least-once
    order.refresh_from_db()
    assert courier.get_block(order)["id_mch"] == first_id
    assert len(courier_mock.rides()) == 1


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_dispatch_handler_skips_cancelled_order(shop):
    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)
    order.refresh_from_db()
    directive = Directive.objects.filter(topic=COURIER_DISPATCH).first()
    CourierDispatchHandler().handle(message=directive, ctx={})
    assert courier.get_block(order) == {}
    assert not courier_mock.rides()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_dispatch_handler_terminal_failure_records_error_and_alerts(shop, monkeypatch):
    from shopman.orderman.exceptions import DirectiveTerminalError

    from shopman.shop.adapters.courier_machine import CourierError

    def _refuse(payload):
        raise CourierError("Machine recusou (400): [2] Atributo obrigatório.", transient=False)

    monkeypatch.setattr(courier_mock, "dispatch", _refuse)
    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    directive = Directive.objects.filter(topic=COURIER_DISPATCH).first()
    with pytest.raises(DirectiveTerminalError):
        CourierDispatchHandler().handle(message=directive, ctx={})

    order.refresh_from_db()
    assert "recusou" in courier.get_block(order)["error"]["message"]
    alert = OperatorAlert.objects.get(type="courier_dispatch_failed")
    assert alert.order_ref == order.ref
    assert alert.severity == "critical"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_dispatch_handler_transient_failure_raises_for_retry(shop, monkeypatch):
    from shopman.orderman.exceptions import DirectiveTransientError

    from shopman.shop.adapters.courier_machine import CourierError

    def _timeout(payload):
        raise CourierError("Machine indisponível: timeout", transient=True)

    monkeypatch.setattr(courier_mock, "dispatch", _timeout)
    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    directive = Directive.objects.filter(topic=COURIER_DISPATCH).first()
    with pytest.raises(DirectiveTransientError):
        CourierDispatchHandler().handle(message=directive, ctx={})
    order.refresh_from_db()
    assert "error" not in courier.get_block(order)  # transient não marca erro terminal
    assert not OperatorAlert.objects.exists()


# ── apply_status: transições derivadas ──────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def _dispatched_order(shop) -> Order:
    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    _run_dispatch(order)
    return order


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_accepted_ride_enriches_driver_and_tracking(shop):
    order = _dispatched_order(shop)
    courier.apply_status(order, "A", source="poll")
    block = courier.get_block(order)
    assert block["status"] == "A"
    assert block["driver"]["name"] == "Entregador Mock"
    assert block["tracking_url"].startswith("https://rastreio.mock/")
    assert order.status == Order.Status.READY  # aceite ainda não é coleta


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_pickup_by_courier_advances_order_to_dispatched(shop):
    order = _dispatched_order(shop)
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED
    block = courier.get_block(order)
    assert block["status"] == "E"
    assert block["dispatched_at"]
    # rede de segurança por ETA agendada como sempre
    assert Directive.objects.filter(topic=DELIVERY_AUTO_COMPLETE, payload__order_ref=order.ref).exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_finished_ride_marks_delivered(shop):
    order = _dispatched_order(shop)
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    courier.apply_status(order, "F", source="webhook")
    order.refresh_from_db()
    assert order.status in (Order.Status.DELIVERED, Order.Status.COMPLETED)
    assert courier.get_block(order)["finished_at"]


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_finished_without_observed_pickup_still_delivers(shop):
    # Webhook perdido/polling largo: F chega com o pedido ainda READY.
    order = _dispatched_order(shop)
    courier.apply_status(order, "F", source="poll")
    order.refresh_from_db()
    assert order.status in (Order.Status.DELIVERED, Order.Status.COMPLETED)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_not_attended_archives_ride_and_alerts(shop):
    order = _dispatched_order(shop)
    ride_id = courier.get_block(order)["id_mch"]
    courier.apply_status(order, "N", source="poll")
    order.refresh_from_db()

    block = courier.get_block(order)
    assert not courier.has_active_ride(order)
    assert block["attempts"][0]["id_mch"] == ride_id
    assert block["attempts"][0]["status"] == "N"
    assert OperatorAlert.objects.filter(type="courier_not_attended", order_ref=order.ref).exists()
    assert order.status == Order.Status.READY  # pedido não trava por causa da corrida


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_apply_status_is_idempotent_and_ignores_late_events(shop):
    order = _dispatched_order(shop)
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    courier.apply_status(order, "E", source="poll")  # replay: no-op
    courier.apply_status(order, "F", source="webhook")
    order.refresh_from_db()
    events_before = order.events.filter(type="courier_status").count()
    courier.apply_status(order, "E", source="poll")  # atrasado pós-terminal: no-op
    assert order.events.filter(type="courier_status").count() == events_before


# ── redispatch / cancel_ride ────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_redispatch_after_not_attended_queues_new_attempt(shop):
    order = _dispatched_order(shop)
    courier.apply_status(order, "N", source="poll")
    order.refresh_from_db()
    Directive.objects.filter(topic=COURIER_DISPATCH).delete()

    courier.redispatch(order, actor="operator:maria")
    directive = Directive.objects.get(topic=COURIER_DISPATCH, payload__order_ref=order.ref)
    assert directive.dedupe_key == f"courier.dispatch:{order.ref}:2"

    CourierDispatchHandler().handle(message=directive, ctx={})
    order.refresh_from_db()
    assert courier.has_active_ride(order)
    assert len(courier.get_block(order)["attempts"]) == 1


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_redispatch_blocked_with_active_ride(shop):
    order = _dispatched_order(shop)
    with pytest.raises(ValueError, match="corrida ativa"):
        courier.redispatch(order, actor="operator:maria")


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_cancel_ride_before_pickup(shop):
    order = _dispatched_order(shop)
    courier.apply_status(order, "A", source="poll")
    courier.cancel_ride(order, actor="maria")
    order.refresh_from_db()
    assert not courier.has_active_ride(order)
    # cancelamento pelo operador não gera alerta (ele mesmo agiu)
    assert not OperatorAlert.objects.filter(type="courier_ride_cancelled").exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_cancel_ride_blocked_after_pickup(shop):
    order = _dispatched_order(shop)
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    with pytest.raises(ValueError, match="em rota"):
        courier.cancel_ride(order, actor="maria")


# ── polling (courier.sync) ──────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_sync_handler_applies_status_and_reschedules(shop):
    order = _dispatched_order(shop)
    courier_mock.set_status(courier.get_block(order)["id_mch"], "A")
    directive = Directive.objects.get(topic=COURIER_SYNC, payload__order_ref=order.ref)
    Directive.objects.filter(pk=directive.pk).update(status=Directive.Status.DONE)

    CourierSyncHandler().handle(message=directive, ctx={})
    order.refresh_from_db()
    assert courier.get_block(order)["status"] == "A"
    assert Directive.objects.filter(
        topic=COURIER_SYNC, payload__order_ref=order.ref, status=Directive.Status.QUEUED
    ).exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_sync_handler_stops_on_terminal_status(shop):
    order = _dispatched_order(shop)
    ride_id = courier.get_block(order)["id_mch"]
    courier_mock.set_status(ride_id, "E")
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    courier_mock.set_status(ride_id, "F")

    directive = Directive.objects.get(topic=COURIER_SYNC, payload__order_ref=order.ref)
    Directive.objects.filter(pk=directive.pk).update(status=Directive.Status.DONE)
    CourierSyncHandler().handle(message=directive, ctx={})
    order.refresh_from_db()

    assert order.status in (Order.Status.DELIVERED, Order.Status.COMPLETED)
    assert not Directive.objects.filter(
        topic=COURIER_SYNC, payload__order_ref=order.ref, status=Directive.Status.QUEUED
    ).exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_sync_handler_respects_poll_disabled(shop):
    shop.defaults = {"delivery": {"courier_poll_seconds": 0}}
    shop.save()
    from shopman.shop.models.shop import SHOP_CACHE_KEY

    cache.delete(SHOP_CACHE_KEY)

    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    _run_dispatch(order)
    # com polling desligado o despacho não agenda heartbeat
    assert not Directive.objects.filter(topic=COURIER_SYNC, payload__order_ref=order.ref).exists()


# ── cotação ─────────────────────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_estimate_for_order_caches_and_stores(shop):
    order = _delivery_order()
    est = courier.estimate_for_order(order, store=True)
    assert est == {"value_q": 1250, "minutes": 18.0, "km": 4.2}
    order.refresh_from_db()
    assert courier.get_block(order)["estimate"] == est
    # segunda chamada vem do cache (adapter não é consultado)
    import unittest.mock as mock

    with mock.patch.object(courier_mock, "estimate", side_effect=AssertionError("cache miss")):
        assert courier.estimate_for_order(order) == est


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_estimate_for_order_none_without_coordinates(shop):
    order = _delivery_order(delivery_address_structured={"city": "Londrina"})
    assert courier.estimate_for_order(order) is None


# ── gancho do lifecycle (_on_ready) ─────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_on_ready_with_courier_auto_queues_dispatch(shop):
    from shopman.shop.config import ChannelConfig
    from shopman.shop.lifecycle import _on_ready

    config = ChannelConfig.from_dict(
        {"fulfillment": {"timing": "external", "courier": "auto"}}
    )
    order = _delivery_order()
    _on_ready(order, config)
    assert Directive.objects.filter(topic=COURIER_DISPATCH, payload__order_ref=order.ref).exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_on_ready_with_courier_none_does_not_dispatch(shop):
    from shopman.shop.config import ChannelConfig
    from shopman.shop.lifecycle import _on_ready

    config = ChannelConfig.from_dict({"fulfillment": {"timing": "external"}})
    order = _delivery_order()
    _on_ready(order, config)
    assert not Directive.objects.filter(topic=COURIER_DISPATCH).exists()


# ── notificação: link de rastreio do entregador ─────────────────────


def test_notification_context_includes_courier_tracking(shop):
    from shopman.shop.services.notification import _build_context

    order = _delivery_order(
        courier={
            "provider": "machine",
            "id_mch": "1",
            "status": "E",
            "tracking_url": "https://rastreio.mock/pedido/x",
        }
    )
    ctx = _build_context(order, {"order_ref": order.ref}, "order_dispatched")
    assert ctx["courier_tracking_url"] == "https://rastreio.mock/pedido/x"
    assert ctx["courier_tracking_suffix"] == "\nAcompanhe o entregador: https://rastreio.mock/pedido/x"


def test_notification_context_suppresses_suffix_without_ride(shop):
    from shopman.shop.services.notification import _build_context

    order = _delivery_order(ref="CR-NO-RIDE")
    ctx = _build_context(order, {"order_ref": order.ref}, "order_dispatched")
    assert ctx["courier_tracking_url"] == ""
    assert ctx["courier_tracking_suffix"] == ""


def test_channel_config_validates_courier_values():
    from shopman.shop.config import ChannelConfig

    config = ChannelConfig.from_dict({"fulfillment": {"courier": "sempre"}})
    with pytest.raises(ValueError, match="fulfillment.courier"):
        config.validate()
