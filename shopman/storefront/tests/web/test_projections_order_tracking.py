"""Unit tests for shopman.shop.projections.order_tracking.

Uses order fixtures from conftest.py. Verifies OrderTrackingProjection
and OrderTrackingStatusProjection shape, timeline construction, terminal
status detection, fulfillment display, and the status colour mapping.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from shopman.shop.projections.types import (
    OrderItemProjection,
    TimelineEventProjection,
)
from shopman.storefront.presentation.order_tracking import (
    OrderTrackingProjection,
    OrderTrackingPromiseProjection,
    OrderTrackingStatusProjection,
    build_order_tracking,
    build_order_tracking_status,
)
from shopman.storefront.presentation.types import OrderProgressStepProjection

pytestmark = pytest.mark.django_db


# ──────────────────────────────────────────────────────────────────────
# OrderTrackingProjection — shape
# ──────────────────────────────────────────────────────────────────────


class TestOrderTrackingShape:
    def test_returns_projection(self, order):
        proj = build_order_tracking(order)
        assert isinstance(proj, OrderTrackingProjection)

    def test_is_immutable(self, order):
        from dataclasses import FrozenInstanceError

        proj = build_order_tracking(order)
        with pytest.raises(FrozenInstanceError):
            proj.status = "confirmed"  # type: ignore[misc]

    def test_order_ref_matches(self, order):
        proj = build_order_tracking(order)
        assert proj.order_ref == order.ref

    def test_has_server_time_anchor_for_countdowns(self, order):
        from django.utils.dateparse import parse_datetime

        proj = build_order_tracking(order)

        assert parse_datetime(proj.server_now_iso) is not None

    def test_has_current_operational_promise(self, order):
        proj = build_order_tracking(order)

        assert isinstance(proj.promise, OrderTrackingPromiseProjection)
        assert proj.promise.state == "received"
        assert proj.promise.title == "Recebemos seu pedido"
        assert proj.promise.timer_mode == "none"
        assert proj.promise.actions == ()
        assert proj.promise.message == "Estamos conferindo a disponibilidade dos itens."

    def test_has_refresh_freshness_contract(self, order):
        from django.utils.dateparse import parse_datetime

        proj = build_order_tracking(order)

        assert parse_datetime(proj.last_updated_iso) is not None
        assert proj.last_updated_display == "Atualizado agora"
        assert proj.stale_after_seconds == 30
        assert proj.promise_deadline_label == "Prazo"
        # "Atualizado agora" is shown once (standalone) — never repeated as a row.
        assert "Última atualização" not in [row.label for row in proj.promise_rows]

    def test_status_matches(self, order):
        proj = build_order_tracking(order)
        assert proj.status == "new"
        assert proj.status_label == "Aguardando confirmação"

    def test_total_display_formatted(self, order):
        proj = build_order_tracking(order)
        assert proj.total_display.startswith("R$ ")
        assert "16,00" in proj.total_display  # 1600q

    def test_is_active_for_non_terminal(self, order):
        proj = build_order_tracking(order)
        assert proj.is_active is True

    def test_is_active_false_for_completed(self, order):
        from shopman.orderman.models import Order as _Order
        _Order.objects.filter(pk=order.pk).update(status="completed")
        order.refresh_from_db()
        proj = build_order_tracking(order)
        assert proj.is_active is False


# ──────────────────────────────────────────────────────────────────────
# Items
# ──────────────────────────────────────────────────────────────────────


class TestOrderTrackingItems:
    def test_items_populated(self, order_items):
        proj = build_order_tracking(order_items)
        assert len(proj.items) == 2
        assert all(isinstance(i, OrderItemProjection) for i in proj.items)

    def test_item_fields(self, order_items, product, croissant):
        proj = build_order_tracking(order_items)
        skus = {i.sku for i in proj.items}
        assert product.sku in skus
        assert croissant.sku in skus

    def test_item_price_formatted(self, order_items):
        proj = build_order_tracking(order_items)
        for item in proj.items:
            assert item.unit_price_display.startswith("R$ ")
            assert item.total_display.startswith("R$ ")
            assert item.qty > 0

    def test_empty_order_has_empty_items(self, order):
        proj = build_order_tracking(order)
        assert proj.items == ()


# ──────────────────────────────────────────────────────────────────────
# Timeline
# ──────────────────────────────────────────────────────────────────────


class TestOrderTrackingTimeline:
    def test_created_event_in_timeline(self, order):
        # Emit a created event
        order.emit_event(event_type="created", actor="test", payload={})
        proj = build_order_tracking(order)
        assert len(proj.timeline) >= 1
        assert all(isinstance(e, TimelineEventProjection) for e in proj.timeline)
        labels = [e.label for e in proj.timeline]
        assert "Pedido criado" in labels

    def test_status_change_appears_in_timeline(self, order):
        order.emit_event(
            event_type="status_changed",
            actor="test",
            payload={"new_status": "confirmed"},
        )
        proj = build_order_tracking(order)
        labels = [e.label for e in proj.timeline]
        assert "Confirmado" in labels

    def test_timeline_timestamp_display_formatted(self, order):
        order.emit_event(event_type="created", actor="test", payload={})
        proj = build_order_tracking(order)
        for event in proj.timeline:
            assert event.timestamp_display  # non-empty
            assert "às" in event.timestamp_display  # e.g. "15/04 às 14:32"

    def test_timeline_is_immutable(self, order):
        from dataclasses import FrozenInstanceError

        order.emit_event(event_type="created", actor="test", payload={})
        proj = build_order_tracking(order)
        with pytest.raises(FrozenInstanceError):
            proj.timeline[0].label = "changed"  # type: ignore[misc]


class TestOrderProgressSteps:
    def test_new_pickup_order_progress_path(self, order):
        proj = build_order_tracking(order)

        assert all(isinstance(step, OrderProgressStepProjection) for step in proj.progress_steps)
        assert [step.label for step in proj.progress_steps] == [
            "Recebemos seu pedido",
        ]
        assert [step.state for step in proj.progress_steps] == [
            "current",
        ]

    def test_confirmed_unpaid_pix_hides_future_payment_step(self, order_with_payment):
        order_with_payment.transition_status("confirmed", actor="test")
        order_with_payment.refresh_from_db()

        proj = build_order_tracking(order_with_payment)

        states = {step.key: step.state for step in proj.progress_steps}
        assert [step.label for step in proj.progress_steps] == [
            "Recebemos seu pedido",
            "Disponibilidade confirmada",
        ]
        assert states["received"] == "completed"
        assert states["availability"] == "current"
        assert "payment" not in states

    def test_confirmed_without_canonical_timestamp_hides_availability_step(self, order_with_payment):
        from shopman.orderman.models import Order as _Order

        _Order.objects.filter(pk=order_with_payment.pk).update(status="confirmed")
        order_with_payment.refresh_from_db()

        proj = build_order_tracking(order_with_payment)

        assert [step.key for step in proj.progress_steps] == ["received"]

    def test_preparing_paid_pix_marks_payment_done_and_preparing_current(self, order_with_payment):
        from shopman.payman import PaymentService

        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref,
            amount_q=order_with_payment.total_q,
            method="pix",
        )
        order_with_payment.data["payment"]["intent_ref"] = intent.ref
        order_with_payment.save(update_fields=["data"])
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        order_with_payment.transition_status("confirmed", actor="test")
        order_with_payment.transition_status("preparing", actor="test")
        order_with_payment.refresh_from_db()

        proj = build_order_tracking(order_with_payment)

        states = {step.key: step.state for step in proj.progress_steps}
        assert states["payment"] == "completed"
        assert states["preparing"] == "current"

    def test_delivery_path_uses_dispatch_and_delivered_steps(self, order_with_payment):
        from shopman.payman import PaymentService

        order_with_payment.data["fulfillment_type"] = "delivery"
        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref,
            amount_q=order_with_payment.total_q,
            method="pix",
        )
        order_with_payment.data["payment"]["intent_ref"] = intent.ref
        order_with_payment.save(update_fields=["data"])
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        for status in ("confirmed", "preparing", "ready", "dispatched", "delivered", "completed"):
            order_with_payment.transition_status(status, actor="test")
        order_with_payment.refresh_from_db()

        proj = build_order_tracking(order_with_payment)

        labels = [step.label for step in proj.progress_steps]
        assert "Pedido pronto" in labels
        assert "Saiu para entrega" in labels
        assert "Pedido entregue" in labels
        assert "Pronto para retirada" not in labels
        assert proj.progress_steps[-1].label == "Pedido concluído"
        assert proj.progress_steps[-1].state == "current"

    def test_delivery_ready_is_waiting_collection_not_dispatched(self, order):
        order.data = {"fulfillment_type": "delivery"}
        order.save(update_fields=["data"])
        for status in ("confirmed", "preparing", "ready"):
            order.transition_status(status, actor="test")
        order.refresh_from_db()

        proj = build_order_tracking(order)

        labels = [step.label for step in proj.progress_steps]
        states = {step.key: step.state for step in proj.progress_steps}
        assert proj.status_label == "Aguardando entregador"
        assert "Pedido pronto" in labels
        assert "Saiu para entrega" not in labels
        assert states["ready_delivery"] == "current"
        assert "dispatched" not in states

    def test_delivery_fulfillment_without_tracking_does_not_show_pickup_info(self, order):
        from shopman.orderman.models import Fulfillment

        order.data = {"fulfillment_type": "delivery"}
        order.save(update_fields=["data"])
        Fulfillment.objects.create(order=order)

        proj = build_order_tracking(order)

        assert proj.is_delivery is True
        assert len(proj.delivery_fulfillments) == 1
        assert proj.pickup_fulfillments == ()
        assert proj.pickup_info is None

    def test_unknown_fulfillment_without_tracking_does_not_show_pickup_info(self, order):
        from shopman.orderman.models import Fulfillment

        order.data = {}
        order.save(update_fields=["data"])
        Fulfillment.objects.create(order=order)

        proj = build_order_tracking(order)

        assert proj.is_delivery is False
        assert proj.delivery_fulfillments == ()
        assert proj.pickup_fulfillments == ()
        assert proj.pickup_info is None

    def test_delivery_dispatched_only_after_dispatch_transition(self, order):
        order.data = {"fulfillment_type": "delivery"}
        order.save(update_fields=["data"])
        for status in ("confirmed", "preparing", "ready", "dispatched"):
            order.transition_status(status, actor="test")
        order.refresh_from_db()

        proj = build_order_tracking(order)

        states = {step.key: step.state for step in proj.progress_steps}
        assert "Saiu para entrega" in [step.label for step in proj.progress_steps]
        assert states["ready_delivery"] == "completed"
        assert states["dispatched"] == "current"
        assert proj.promise.requires_active_notification is True
        assert proj.promise.notification_topic == "order_dispatched"

    def test_cancelled_order_has_cancelled_terminal_step(self, order):
        order.transition_status("cancelled", actor="test")
        order.refresh_from_db()

        proj = build_order_tracking(order)

        assert proj.progress_steps[-1].label == "Pedido cancelado"
        assert proj.progress_steps[-1].state == "cancelled"
        assert "Pedido concluído" not in [step.label for step in proj.progress_steps]


# ──────────────────────────────────────────────────────────────────────
# Status colours (Penguin tokens)
# ──────────────────────────────────────────────────────────────────────


class TestStatusColours:
    @pytest.mark.parametrize("status,expected_fragment", [
        ("new", "info"),
        ("confirmed", "info"),
        ("preparing", "warning"),
        ("ready", "success"),
        ("dispatched", "info"),
        ("delivered", "success"),
        ("completed", "success"),
        ("cancelled", "danger"),
    ])
    def test_status_colour_uses_penguin_tokens(self, order, status, expected_fragment):
        from shopman.orderman.models import Order as _Order
        _Order.objects.filter(pk=order.pk).update(status=status)
        order.refresh_from_db()
        proj = build_order_tracking(order)
        assert expected_fragment in proj.status_color

    def test_ready_pickup_label(self, order):
        from shopman.orderman.models import Order as _Order

        from shopman.shop.models import Shop
        shop = Shop.load()
        shop.formatted_address = "Rua das Flores, 123 - Centro, Londrina - PR"
        shop.save(update_fields=["formatted_address"])

        _Order.objects.filter(pk=order.pk).update(status="ready", data={"fulfillment_type": "pickup"})
        order.refresh_from_db()
        proj = build_order_tracking(order)
        assert proj.status_label == "Pronto para retirada"
        assert proj.promise.state == "ready_pickup"
        assert proj.promise.requires_active_notification is False
        assert proj.promise.notification_topic is None
        assert proj.promise.actions[0].label == "Retirar pedido"
        assert proj.promise.actions[0].kind == "instruction"
        assert proj.promise.actions[0].href == ""
        assert proj.promise.active_notification == ""
        assert proj.pickup_fulfillments == ()
        assert proj.pickup_info is not None
        assert proj.pickup_info.directions_url is not None
        assert proj.pickup_info.directions_url.startswith("https://www.google.com/maps/dir/?")
        assert "destination=Rua+das+Flores" in proj.pickup_info.directions_url
        assert proj.copy.page_kicker == "Acompanhamento"
        assert proj.copy.support_label == "Ajuda"
        assert proj.copy.progress_heading == "Etapas do pedido"
        # O painel mostra a mensagem do estado + a linha "Próximo passo" (a ação
        # segue como botão, "Atualizado agora" segue standalone).
        assert proj.promise.message == "Pode retirar quando quiser — estamos esperando você."
        assert proj.promise.next_event == "Retire no estabelecimento quando puder."
        assert [row.label for row in proj.promise_rows] == ["Próximo passo"]

    def test_pickup_info_uses_structured_shop_address_without_fulfillment(self, order):
        from shopman.orderman.models import Order as _Order

        from shopman.shop.models import Shop

        shop = Shop.load()
        shop.formatted_address = ""
        shop.route = "Rua das Flores"
        shop.street_number = "123"
        shop.neighborhood = "Centro"
        shop.city = "Londrina"
        shop.state_code = "PR"
        shop.save(update_fields=[
            "formatted_address",
            "route",
            "street_number",
            "neighborhood",
            "city",
            "state_code",
        ])

        _Order.objects.filter(pk=order.pk).update(status="ready", data={"fulfillment_type": "pickup"})
        order.refresh_from_db()

        proj = build_order_tracking(order)

        assert proj.pickup_fulfillments == ()
        assert proj.pickup_info is not None
        assert proj.pickup_info.address == "Rua das Flores, 123\nCentro\nLondrina — PR"
        assert proj.pickup_info.directions_url is not None
        assert "destination=Rua+das+Flores%2C+123%2C+Centro%2C+Londrina" in proj.pickup_info.directions_url

    def test_pickup_info_projects_directions_copy_and_url(self, order):
        from decimal import Decimal

        from shopman.orderman.models import Fulfillment
        from shopman.orderman.models import Order as _Order

        from shopman.shop.models import Shop

        shop = Shop.load()
        shop.formatted_address = "Av. Madre Leônia Milito, 446 - Bela Suíça, Londrina - PR"
        shop.latitude = Decimal("-23.3044521")
        shop.longitude = Decimal("-51.1695824")
        shop.place_id = "ChIJ-shopman"
        shop.save(update_fields=["formatted_address", "latitude", "longitude", "place_id"])

        _Order.objects.filter(pk=order.pk).update(status="ready", data={"fulfillment_type": "pickup"})
        Fulfillment.objects.create(order=order)
        order.refresh_from_db()

        proj = build_order_tracking(order)

        assert proj.pickup_info is not None
        assert proj.pickup_info.heading == "Retirada"
        assert proj.pickup_info.directions_label == "Como chegar"
        assert proj.pickup_info.directions_url is not None
        assert proj.pickup_info.directions_url.startswith("https://www.google.com/maps/dir/?")
        assert "destination=Av.+Madre+Le%C3%B4nia+Milito%2C+446" in proj.pickup_info.directions_url
        assert "destination_place_id=ChIJ-shopman" in proj.pickup_info.directions_url
        assert "origin=" not in proj.pickup_info.directions_url
        assert "travelmode=" not in proj.pickup_info.directions_url

    def test_pickup_fulfillment_uses_counter_labels_without_shipment_tracking(self, order):
        # Retirada não é envio: o card não pode dizer "Rastrear envio" (não acionável).
        from shopman.orderman.models import Fulfillment
        from shopman.orderman.models import Order as _Order

        _Order.objects.filter(pk=order.pk).update(data={"fulfillment_type": "pickup"})
        Fulfillment.objects.create(order=order, status="pending")
        order.refresh_from_db()

        proj = build_order_tracking(order)

        assert len(proj.pickup_fulfillments) == 1
        ful = proj.pickup_fulfillments[0]
        assert ful.status_label == "Em preparo"
        assert ful.tracking_label == ""
        assert ful.tracking_url is None

    def test_pickup_directions_fall_back_to_coordinates_without_address(self, order):
        from decimal import Decimal

        from shopman.orderman.models import Fulfillment
        from shopman.orderman.models import Order as _Order

        from shopman.shop.models import Shop

        shop = Shop.load()
        shop.formatted_address = ""
        shop.route = ""
        shop.street_number = ""
        shop.neighborhood = ""
        shop.postal_code = ""
        shop.latitude = Decimal("-23.3044521")
        shop.longitude = Decimal("-51.1695824")
        shop.save(update_fields=[
            "formatted_address",
            "route",
            "street_number",
            "neighborhood",
            "postal_code",
            "latitude",
            "longitude",
        ])

        _Order.objects.filter(pk=order.pk).update(status="ready", data={"fulfillment_type": "pickup"})
        Fulfillment.objects.create(order=order)
        order.refresh_from_db()

        proj = build_order_tracking(order)

        assert proj.pickup_info is not None
        assert proj.pickup_info.directions_url is not None
        assert "destination=-23.3044521%2C-51.1695824" in proj.pickup_info.directions_url

    def test_ready_unknown_fulfillment_label_is_not_pickup(self, order):
        from shopman.orderman.models import Order as _Order
        _Order.objects.filter(pk=order.pk).update(status="ready", data={})
        order.refresh_from_db()
        proj = build_order_tracking(order)
        assert proj.status_label == "Pronto"
        assert "Pronto para retirada" not in [
            step.label for step in proj.progress_steps
        ]

    def test_ready_delivery_label(self, order):
        from shopman.orderman.models import Order as _Order
        _Order.objects.filter(pk=order.pk).update(status="ready", data={"fulfillment_type": "delivery"})
        order.refresh_from_db()
        proj = build_order_tracking(order)
        assert proj.status_label == "Aguardando entregador"
        assert proj.promise.requires_active_notification is False
        assert proj.promise.notification_topic is None
        assert proj.promise.active_notification == ""
        assert "Aviso ativo" not in [row.label for row in proj.promise_rows]

    def test_dispatched_delivery_is_honest_no_arrival_promise(self, order):
        """Trecho mais sensível: courier terceirizado, sem rastreio nem detecção
        de chegada. Nunca prometer 'avisamos quando chegar'. Damos janela de ETA
        + a ação 'Recebi' para o cliente fechar o loop."""
        from shopman.orderman.models import Order as _Order
        _Order.objects.filter(pk=order.pk).update(status="dispatched", data={"fulfillment_type": "delivery"})
        order.refresh_from_db()
        order.emit_event(event_type="status_changed", actor="op", payload={"new_status": "dispatched"})

        proj = build_order_tracking(order)

        assert proj.promise.state == "dispatched"
        assert proj.promise.title == "Saiu para entrega"
        assert "a caminho" in proj.promise.message
        assert "por volta das" in proj.promise.message  # janela de ETA
        # Nunca promete notificar a chegada — não há como saber.
        assert "avisamos" not in proj.promise.message.lower()
        assert "quando chegar" not in proj.promise.message.lower()
        # Loop fechado pelo cliente, não dependente.
        assert any(a.ref == "confirm_received" for a in proj.promise.actions)

    def test_confirm_received_marks_delivery_done(self, order):
        from shopman.storefront.services import orders as order_service
        order.data = {"fulfillment_type": "delivery"}
        order.save(update_fields=["data"])
        for next_status in ("confirmed", "preparing", "ready", "dispatched"):
            order.transition_status(next_status, actor="op")
        order.refresh_from_db()
        assert order.status == "dispatched"

        assert order_service.confirm_received(order) is True
        order.refresh_from_db()
        assert order.status in {"delivered", "completed"}
        # Idempotente: já não está em entrega → no-op.
        assert order_service.confirm_received(order) is False

    def test_confirm_received_rejects_non_delivery_or_wrong_status(self, order):
        from shopman.orderman.models import Order as _Order

        from shopman.storefront.services import orders as order_service
        # pickup em dispatched não é entrega → não aplica
        _Order.objects.filter(pk=order.pk).update(status="dispatched", data={"fulfillment_type": "pickup"})
        order.refresh_from_db()
        assert order_service.confirm_received(order) is False

    def test_new_pix_order_shows_payment_pending_label(self, order_with_payment):
        proj = build_order_tracking(order_with_payment)

        assert proj.status_label == "Aguardando pagamento"
        assert proj.payment_pending is True
        assert proj.payment_expired is False
        assert proj.payment_status_label == "Aguardando confirmação do pagamento"
        assert proj.confirmation_countdown is False
        assert proj.promise.state == "payment_pending"
        assert proj.promise.deadline_kind == "payment"
        assert proj.promise.deadline_at == proj.payment_expires_at

    def test_expired_auto_confirm_countdown_is_not_rendered(self, order, channel):
        from django.utils import timezone
        from shopman.orderman.models import Order as _Order

        channel.config = {"confirmation": {"mode": "auto_confirm", "timeout_minutes": 5}}
        channel.save(update_fields=["config"])
        _Order.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timezone.timedelta(minutes=6),
        )
        order.refresh_from_db()

        proj = build_order_tracking(order)

        assert proj.confirmation_countdown is False
        assert proj.confirmation_expires_at is None

    def test_pending_payment_suppresses_store_confirmation_countdown(self, order_with_payment, channel):
        from django.utils import timezone
        from shopman.orderman.models import Directive

        channel.config = {"confirmation": {"mode": "auto_confirm", "timeout_minutes": 5}}
        channel.save(update_fields=["config"])
        Directive.objects.create(
            topic="confirmation.timeout",
            payload={
                "order_ref": order_with_payment.ref,
                "action": "confirm",
                "expires_at": (timezone.now() + timezone.timedelta(minutes=5)).isoformat(),
            },
            available_at=timezone.now() + timezone.timedelta(minutes=5),
        )

        proj = build_order_tracking(order_with_payment)

        assert proj.payment_pending is True
        assert proj.confirmation_countdown is False
        assert proj.confirmation_expires_at is None

    def test_paid_new_order_waits_for_store_confirmation(self, order_with_payment, channel):
        from django.utils import timezone
        from shopman.orderman.models import Directive
        from shopman.payman import PaymentService

        channel.config = {"confirmation": {"mode": "auto_confirm", "timeout_minutes": 5}}
        channel.save(update_fields=["config"])
        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref,
            amount_q=order_with_payment.total_q,
            method="pix",
        )
        order_with_payment.data["payment"]["intent_ref"] = intent.ref
        order_with_payment.save(update_fields=["data"])
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        expires_at = timezone.now() + timezone.timedelta(minutes=5)
        Directive.objects.create(
            topic="confirmation.timeout",
            payload={
                "order_ref": order_with_payment.ref,
                "action": "confirm",
                "expires_at": expires_at.isoformat(),
            },
            available_at=expires_at,
        )

        proj = build_order_tracking(order_with_payment)

        assert proj.status_label == "Aguardando confirmação"
        assert proj.payment_pending is False
        assert proj.payment_confirmed is True
        assert proj.show_payment_confirmed_notice is True
        assert proj.payment_status_label == "Pagamento confirmado"
        assert proj.confirmation_countdown is True
        assert proj.confirmation_expires_at is not None
        assert proj.promise.state == "availability_check"
        assert proj.promise.title == "Recebemos seu pedido"
        assert proj.promise.message == "Estamos conferindo a disponibilidade dos itens."
        assert proj.promise.next_event == "Se a disponibilidade for confirmada, liberamos o pagamento e avisamos você."

    def test_closed_store_new_order_defers_availability_without_countdown(
        self, order, channel, shop_instance,
    ):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from shopman.orderman.models import Directive

        tz = ZoneInfo("America/Sao_Paulo")
        shop_instance.timezone = "America/Sao_Paulo"
        shop_instance.opening_hours = {
            "monday": {"open": "09:00", "close": "18:00"},
            "tuesday": {"open": "09:00", "close": "18:00"},
            "wednesday": {"open": "09:00", "close": "18:00"},
            "thursday": {"open": "09:00", "close": "18:00"},
            "friday": {"open": "09:00", "close": "18:00"},
            "saturday": {"open": "09:00", "close": "18:00"},
        }
        shop_instance.save(update_fields=["timezone", "opening_hours"])
        channel.config = {"confirmation": {"mode": "auto_confirm", "timeout_minutes": 5}}
        channel.save(update_fields=["config"])
        Directive.objects.create(
            topic="confirmation.timeout",
            payload={
                "order_ref": order.ref,
                "action": "confirm",
                "expires_at": datetime(2026, 5, 4, 9, 5, tzinfo=tz).isoformat(),
                "outside_business_hours": True,
                "deferred_until": datetime(2026, 5, 4, 9, 0, tzinfo=tz).isoformat(),
            },
            available_at=datetime(2026, 5, 4, 9, 5, tzinfo=tz),
        )

        with patch(
            "shopman.shop.services.business_calendar.timezone.now",
            return_value=datetime(2026, 5, 3, 12, 0, tzinfo=tz),
        ):
            proj = build_order_tracking(order)

        assert proj.confirmation_countdown is False
        assert proj.confirmation_expires_at is None
        assert proj.promise.state == "availability_deferred"
        assert proj.promise.deadline_at is None
        assert proj.promise.timer_mode == "none"
        assert proj.promise.message == (
            "Estamos fechados agora. Conferimos a disponibilidade quando abrirmos, amanhã às 9h."
        )
        assert proj.promise.next_event == "Próxima abertura: amanhã às 9h"

    def test_payment_timeout_cancelled_order_shows_payment_expired(self, order_with_payment):
        from shopman.orderman.models import Order as _Order

        _Order.objects.filter(pk=order_with_payment.pk).update(
            status="cancelled",
            data={
                **order_with_payment.data,
                "cancellation_reason": "payment_timeout",
                "payment_timeout_at": "2026-05-01T10:00:00-03:00",
            },
        )
        order_with_payment.refresh_from_db()

        proj = build_order_tracking(order_with_payment)

        assert proj.status_label == "Pagamento expirado"
        assert proj.payment_pending is False
        assert proj.payment_expired is True
        assert proj.payment_confirmed is False
        assert proj.show_payment_confirmed_notice is False
        assert proj.payment_status_label == "Prazo para pagamento expirado"
        assert proj.confirmation_countdown is False
        assert proj.promise.requires_active_notification is True
        assert proj.promise.notification_topic == "payment_expired"
        assert proj.promise.actions == ()
        assert "repetir o pedido" in proj.promise.message
        assert proj.promise.next_event == "Você pode refazer o pedido quando quiser."
        assert proj.promise.recovery == ""
        assert any(action.ref == "reorder" and action.label == "Repetir pedido" for action in proj.actions)
        row_labels = [row.label for row in proj.promise_rows]
        assert "Próximo passo" in row_labels
        assert "Se algo mudar" not in row_labels

    def test_confirmed_paid_order_keeps_payment_confirmation_visible(self, order_with_payment):
        from shopman.payman import PaymentService

        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref,
            amount_q=order_with_payment.total_q,
            method="pix",
        )
        order_with_payment.data["payment"]["intent_ref"] = intent.ref
        order_with_payment.save(update_fields=["data"])
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        order_with_payment.transition_status("confirmed", actor="test")
        order_with_payment.refresh_from_db()

        proj = build_order_tracking(order_with_payment)

        assert proj.status_label == "Confirmado"
        assert proj.payment_pending is False
        assert proj.payment_confirmed is True
        assert proj.show_payment_confirmed_notice is True
        assert proj.payment_status_label == "Pagamento confirmado"

    def test_paid_order_after_preparing_hides_payment_confirmation_notice(self, order_with_payment):
        from shopman.payman import PaymentService

        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref,
            amount_q=order_with_payment.total_q,
            method="pix",
        )
        order_with_payment.data["payment"]["intent_ref"] = intent.ref
        order_with_payment.save(update_fields=["data"])
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        order_with_payment.transition_status("confirmed", actor="test")
        order_with_payment.transition_status("preparing", actor="test")
        order_with_payment.refresh_from_db()

        proj = build_order_tracking(order_with_payment)

        assert proj.payment_confirmed is True
        assert proj.show_payment_confirmed_notice is False

    def test_confirmed_unpaid_digital_order_shows_payment_pending(self, order_with_payment):
        order_with_payment.transition_status("confirmed", actor="test")
        order_with_payment.refresh_from_db()

        proj = build_order_tracking(order_with_payment)

        assert proj.status_label == "Aguardando pagamento"
        assert proj.payment_pending is True
        assert proj.payment_confirmed is False
        assert proj.payment_status_label == "Aguardando confirmação do pagamento"
        assert proj.promise.state == "payment_requested"
        assert proj.promise.requires_active_notification is True
        assert proj.promise.notification_topic == "payment_requested"
        assert proj.promise.actions[0].ref == "pay_now"
        assert proj.promise.actions[0].label == "Pagar agora"
        assert proj.promise.actions[0].href == f"/pedido/{order_with_payment.ref}/pagamento/"
        assert proj.promise.message == "Confirme o PIX e já começamos a preparar."
        assert proj.promise.next_event == "Depois do pagamento, seguimos com o pedido."
        assert proj.promise.recovery == "Liberamos sua reserva e o pedido é cancelado."

    def test_authorized_card_is_internal_not_surface_payment_action(self, order_with_payment):
        from shopman.orderman.models import Order as _Order
        from shopman.payman import PaymentService

        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref,
            amount_q=order_with_payment.total_q,
            method="card",
        )
        order_with_payment.data["payment"] = {
            "method": "card",
            "intent_ref": intent.ref,
            "amount_q": order_with_payment.total_q,
        }
        order_with_payment.save(update_fields=["data"])
        PaymentService.authorize(intent.ref)
        _Order.objects.filter(pk=order_with_payment.pk).update(status="confirmed")
        order_with_payment.refresh_from_db()

        proj = build_order_tracking(order_with_payment)

        assert proj.payment_pending is False
        assert proj.payment_confirmed is False
        assert proj.payment_status_label == "Pagamento autorizado"
        assert proj.status_label == "Pagamento autorizado"
        assert proj.promise.state == "card_authorized"
        assert proj.promise.actions == ()
        assert "Aguardando pagamento" not in {proj.status_label, proj.payment_status_label}

    def test_eta_uses_preparing_timestamp_not_order_creation(self, order):
        from django.utils import timezone
        from shopman.orderman.models import Order as _Order

        preparing_at = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        created_at = preparing_at - timezone.timedelta(minutes=20)
        _Order.objects.filter(pk=order.pk).update(
            status="preparing",
            created_at=created_at,
            preparing_at=preparing_at,
        )
        order.refresh_from_db()

        proj = build_order_tracking(order)

        expected_eta = (timezone.localtime(preparing_at) + timezone.timedelta(minutes=30)).strftime("%H:%M")
        assert proj.eta_display == expected_eta
        assert proj.promise.message == f"Fica pronto por volta das {proj.eta_display}. Avisamos você quando puder retirar."

    def test_eta_is_not_invented_without_preparing_timestamp(self, order):
        from shopman.orderman.models import Order as _Order

        _Order.objects.filter(pk=order.pk).update(status="preparing", preparing_at=None)
        order.refresh_from_db()

        proj = build_order_tracking(order)

        assert proj.eta_display is None
        assert proj.promise.state == "preparing"
        assert proj.promise.message == "Já estamos no preparo. Avisamos você quando estiver pronto."


# ──────────────────────────────────────────────────────────────────────
# OrderTrackingStatusProjection
# ──────────────────────────────────────────────────────────────────────


class TestOrderTrackingStatusProjection:
    def test_returns_status_projection(self, order):
        proj = build_order_tracking_status(order)
        assert isinstance(proj, OrderTrackingStatusProjection)

    def test_is_immutable(self, order):
        from dataclasses import FrozenInstanceError

        proj = build_order_tracking_status(order)
        with pytest.raises(FrozenInstanceError):
            proj.status = "confirmed"  # type: ignore[misc]

    def test_not_terminal_for_active_order(self, order):
        proj = build_order_tracking_status(order)
        assert proj.is_terminal is False

    @pytest.mark.parametrize("status", ["completed", "cancelled", "returned"])
    def test_terminal_for_terminal_statuses(self, order, status):
        from shopman.orderman.models import Order as _Order
        _Order.objects.filter(pk=order.pk).update(status=status)
        order.refresh_from_db()
        proj = build_order_tracking_status(order)
        assert proj.is_terminal is True

    def test_status_label_and_color_populated(self, order):
        proj = build_order_tracking_status(order)
        assert proj.status_label
        assert proj.status_color

    def test_status_projection_does_not_expose_action_flags(self, order):
        proj = build_order_tracking_status(order)
        assert not hasattr(proj, "can_cancel")
