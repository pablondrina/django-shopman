"""Operator order queue projection and surface guardrails."""

from __future__ import annotations

from django.test import TestCase
from django.utils.dateparse import parse_datetime
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.projections.order_queue import build_order_card, build_two_zone_queue


def _order(ref: str, status: str, fulfillment_type: str = "pickup") -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"session-{ref}",
        status=status,
        total_q=1500,
        data={
            "customer": {"name": f"Cliente {ref}"},
            "fulfillment_type": fulfillment_type,
            "payment": {"method": "cash"},
        },
    )
    OrderItem.objects.create(
        order=order,
        line_id=f"{ref}-1",
        sku="PAO",
        name="Pão",
        qty=1,
        unit_price_q=1500,
        line_total_q=1500,
    )
    return order


def _phone_order(ref: str, phone: str) -> Order:
    order = _order(ref, "new")
    order.data = {
        "customer": {"phone": phone},
        "fulfillment_type": "pickup",
        "payment": {"method": "cash"},
    }
    order.handle_ref = phone
    order.save(update_fields=["data", "handle_ref", "updated_at"])
    return order


class OrderQueueSurfaceTests(TestCase):
    def test_confirmed_and_preparing_orders_are_visible_in_prep(self) -> None:
        _order("Q-NEW", "new")
        _order("Q-CONF", "confirmed")
        _order("Q-PREP", "preparing")
        _order("Q-READY", "ready")
        _order("Q-DISP", "dispatched", "delivery")
        _order("Q-DELIV", "delivered", "delivery")

        queue = build_two_zone_queue()

        self.assertEqual([o.ref for o in queue.intake], ["Q-NEW"])
        self.assertEqual([o.ref for o in queue.prep], ["Q-CONF", "Q-PREP"])
        self.assertEqual(queue.preparing_count, 2)
        self.assertEqual([o.ref for o in queue.expedition_pickup], ["Q-READY"])
        self.assertEqual([o.ref for o in queue.expedition_delivery_transit], ["Q-DISP", "Q-DELIV"])
        self.assertEqual(queue.expedition_delivery_count, 2)
        self.assertEqual(queue.total_count, 6)

    def test_future_preorder_leaves_the_day_columns_for_the_preorders_group(self) -> None:
        """WP-D: encomenda para data futura sai das colunas do dia e vive no grupo
        "Agendados", ordenada pela data combinada. Vale para pedido NOVO (ainda a
        aceitar) e confirmado: ambos carregam o badge "Agendado · <data>", então
        um novo na Entrada com esse badge seria contraditório — pertence aqui."""
        from datetime import timedelta

        from django.utils import timezone

        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        saturday = (timezone.localdate() + timedelta(days=3)).isoformat()

        _order("Q-HOJE", "confirmed")
        later = _order("Q-SAB", "confirmed")
        later.data["delivery_date"] = saturday
        later.save(update_fields=["data", "updated_at"])
        sooner = _order("Q-AMANHA", "confirmed")
        sooner.data["delivery_date"] = tomorrow
        sooner.save(update_fields=["data", "updated_at"])
        new_preorder = _order("Q-NOVA-ENC", "new")
        new_preorder.data["delivery_date"] = tomorrow
        new_preorder.save(update_fields=["data", "updated_at"])

        queue = build_two_zone_queue()

        self.assertEqual([o.ref for o in queue.prep], ["Q-HOJE"])
        # Novo e confirmado, todos futuros → grupo Agendados; a Entrada não recebe
        # card com badge "Agendado" (badge e seção concordam). Ordem: data, criação.
        self.assertEqual([o.ref for o in queue.preorders], ["Q-AMANHA", "Q-NOVA-ENC", "Q-SAB"])
        self.assertEqual(queue.preorders_count, 3)
        self.assertEqual([o.ref for o in queue.intake], [])

        cards = {c.ref: c for c in queue.preorders + queue.intake + queue.prep}
        self.assertTrue(cards["Q-AMANHA"].is_preorder)
        self.assertEqual(cards["Q-AMANHA"].commitment_date, tomorrow)
        self.assertEqual(cards["Q-AMANHA"].commitment_date_display, "amanhã")
        # O card novo segue com o badge de encomenda E a ação de aceitar.
        self.assertTrue(cards["Q-NOVA-ENC"].is_preorder)
        self.assertTrue(cards["Q-NOVA-ENC"].can_confirm)
        self.assertFalse(cards["Q-HOJE"].is_preorder)
        self.assertEqual(cards["Q-HOJE"].commitment_date_display, "")

    def test_past_or_today_commitment_date_is_not_a_preorder(self) -> None:
        """No dia (ou depois dela) a encomenda volta ao fluxo normal do board."""
        from django.utils import timezone

        today_order = _order("Q-DIA", "confirmed")
        today_order.data["delivery_date"] = timezone.localdate().isoformat()
        today_order.save(update_fields=["data", "updated_at"])

        queue = build_two_zone_queue()

        self.assertEqual([o.ref for o in queue.prep], ["Q-DIA"])
        self.assertEqual(queue.preorders, ())

    def test_confirmation_deadline_surfaces_on_new_card(self) -> None:
        from shopman.orderman.models import Directive

        _order("Q-DEADLINE", "new")
        Directive.objects.create(
            topic="confirmation.timeout",
            status="queued",
            payload={
                "order_ref": "Q-DEADLINE",
                "action": "cancel",  # valor real do directive (não "auto_cancel")
                "expires_at": "2026-07-04T12:00:00+00:00",
            },
        )
        _order("Q-NODEADLINE", "new")  # sem timer → campos vazios

        queue = build_two_zone_queue()
        cards = {c.ref: c for c in queue.intake}

        assert cards["Q-DEADLINE"].confirmation_deadline_iso == "2026-07-04T12:00:00+00:00"
        assert cards["Q-DEADLINE"].confirmation_action == "cancel"
        assert cards["Q-NODEADLINE"].confirmation_deadline_iso == ""

    def test_all_active_operator_statuses_have_advance_action_after_confirmation(self) -> None:
        expected_labels = {
            "confirmed": "Iniciar preparo",
            "preparing": "Marcar pronto",
            "dispatched": "Marcar como Entregue",
            "delivered": "Concluir",
        }

        for status, label in expected_labels.items():
            with self.subTest(status=status):
                card = build_order_card(_order(f"A-{status}", status, "delivery"))
                self.assertTrue(card.can_advance)
                self.assertEqual(card.next_action_label, label)

        pickup_ready = build_order_card(_order("A-ready-pickup", "ready", "pickup"))
        delivery_ready = build_order_card(_order("A-ready-delivery", "ready", "delivery"))
        self.assertEqual(pickup_ready.next_action_label, "Marcar como Retirado")
        self.assertEqual(delivery_ready.next_action_label, "Marcar saída para entrega")

    def test_new_orders_keep_confirm_or_reject_as_the_only_primary_decision(self) -> None:
        card = build_order_card(_order("A-NEW", "new"))

        self.assertTrue(card.can_confirm)
        self.assertFalse(card.can_advance)

    def test_cash_marked_paid_is_not_operator_payment_status_source(self) -> None:
        order = _order("A-PAID-CASH", "new")
        order.data["payment"]["marked_paid_by"] = "ana"
        order.save(update_fields=["data", "updated_at"])

        card = build_order_card(order)

        self.assertEqual(card.status, "new")
        self.assertEqual(card.payment_status, "")
        self.assertFalse(card.payment_pending)
        self.assertTrue(card.can_confirm)

    def test_captured_digital_payment_releases_confirm_button_gate(self) -> None:
        from shopman.payman import PaymentService

        order = _order("A-PAID-PIX", "new")
        intent = PaymentService.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="pix",
        )
        order.data["payment"] = {"method": "pix", "intent_ref": intent.ref}
        order.save(update_fields=["data", "updated_at"])
        PaymentService.authorize(intent.ref, gateway_id="pix-paid-gw")
        PaymentService.capture(intent.ref)

        card = build_order_card(Order.objects.get(pk=order.pk))

        self.assertEqual(card.payment_status, "captured")
        self.assertFalse(card.payment_pending)
        self.assertTrue(card.can_confirm)

    def test_card_timer_is_anchored_to_server_time(self) -> None:
        card = build_order_card(_order("A-TIMER", "new"))

        self.assertIsNotNone(parse_datetime(card.created_at_iso))
        self.assertIsNotNone(parse_datetime(card.server_now_iso))
        self.assertGreaterEqual(card.elapsed_seconds, 0)

    def test_customer_phone_is_formatted_for_operator_scan(self) -> None:
        card = build_order_card(_phone_order("A-PHONE", "+5543984049009"))

        self.assertEqual(card.customer_name, "(43) 98404-9009")

    def test_customer_landline_phone_is_formatted_without_brazil_country_code(self) -> None:
        card = build_order_card(_phone_order("A-LANDLINE", "554333231997"))

        self.assertEqual(card.customer_name, "(43) 3323-1997")

    def test_international_customer_phone_keeps_country_code(self) -> None:
        card = build_order_card(_phone_order("A-INTL", "+14155552671"))

        self.assertEqual(card.customer_name, "+14155552671")


class OperatorOrderPresetTests(TestCase):
    def test_detail_projection_exposes_store_cancellation_presets(self) -> None:
        from django.core.cache import cache

        from shopman.backstage.projections.order_queue import build_operator_order
        from shopman.shop.models import Shop

        Shop.objects.create(
            name="Loja Teste",
            cancellation_presets=["Item indisponível", "  ", "Problema técnico"],
        )
        cache.clear()  # Shop.load() memoizes the singleton

        proj = build_operator_order(_order("PRESET-1", "new"))

        # Blank entries are dropped; the rest are exposed in order for the gestor.
        self.assertEqual(proj.cancellation_presets, ("Item indisponível", "Problema técnico"))

    def test_detail_projection_exposes_store_kitchen_note_tags(self) -> None:
        from django.core.cache import cache

        from shopman.backstage.projections.order_queue import build_operator_order
        from shopman.shop.models import Shop

        Shop.objects.create(
            name="Loja Teste",
            kitchen_note_tags=["Bem assado", "  ", "Sem cebola"],
        )
        cache.clear()  # Shop.load() memoizes the singleton

        proj = build_operator_order(_order("KTAG-1", "new"))

        # Blank entries dropped; the rest exposed in order for the gestor's tag buttons.
        self.assertEqual(proj.kitchen_note_tags, ("Bem assado", "Sem cebola"))

    def test_detail_projection_reads_kitchen_note(self) -> None:
        from shopman.backstage.projections.order_queue import build_operator_order

        order = _order("KNOTE-1", "new")
        order.data = {**order.data, "kitchen_note": "Sem cebola. Cortar ao meio."}
        order.save(update_fields=["data", "updated_at"])

        proj = build_operator_order(order)

        self.assertEqual(proj.kitchen_note, "Sem cebola. Cortar ao meio.")

# As ações do operador (advance/reject/confirm) agora são exercidas no contrato
# headless em test_api_orders_surface.py; a semântica de lifecycle (new não avança,
# terminal não avança, reject só em new) é coberta nos testes de shop/operator_orders.
