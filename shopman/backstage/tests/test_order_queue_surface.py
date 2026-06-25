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
    def test_confirmed_and_preparing_orders_are_visible_in_preparo(self) -> None:
        _order("Q-NEW", "new")
        _order("Q-CONF", "confirmed")
        _order("Q-PREP", "preparing")
        _order("Q-READY", "ready")
        _order("Q-DISP", "dispatched", "delivery")
        _order("Q-DELIV", "delivered", "delivery")

        queue = build_two_zone_queue()

        self.assertEqual([o.ref for o in queue.entrada], ["Q-NEW"])
        self.assertEqual([o.ref for o in queue.preparo], ["Q-CONF", "Q-PREP"])
        self.assertEqual(queue.preparing_count, 2)
        self.assertEqual([o.ref for o in queue.saida_retirada], ["Q-READY"])
        self.assertEqual([o.ref for o in queue.saida_delivery_transit], ["Q-DISP", "Q-DELIV"])
        self.assertEqual(queue.saida_delivery_count, 2)
        self.assertEqual(queue.total_count, 6)

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

# As ações do operador (advance/reject/confirm) agora são exercidas no contrato
# headless em test_api_orders_surface.py; a semântica de lifecycle (new não avança,
# terminal não avança, reject só em new) é coberta nos testes de shop/operator_orders.
