"""Operator order queue projection and surface guardrails."""

from __future__ import annotations

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from shopman.backstage.projections.order_queue import build_order_card, build_two_zone_queue
from shopman.orderman.models import Order, OrderItem
from shopman.shop.models import Shop


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
        self.assertEqual(delivery_ready.next_action_label, "Saiu para entrega")

    def test_new_orders_keep_confirm_or_reject_as_the_only_primary_decision(self) -> None:
        card = build_order_card(_order("A-NEW", "new"))

        self.assertTrue(card.can_confirm)
        self.assertFalse(card.can_advance)

    def test_customer_phone_is_formatted_for_operator_scan(self) -> None:
        card = build_order_card(_phone_order("A-PHONE", "+5543984049009"))

        self.assertEqual(card.customer_name, "(43) 98404-9009")

    def test_customer_landline_phone_is_formatted_without_brazil_country_code(self) -> None:
        card = build_order_card(_phone_order("A-LANDLINE", "554333231997"))

        self.assertEqual(card.customer_name, "(43) 3323-1997")

    def test_international_customer_phone_keeps_country_code(self) -> None:
        card = build_order_card(_phone_order("A-INTL", "+14155552671"))

        self.assertEqual(card.customer_name, "+14155552671")


class OrderAdvanceSurfaceTests(TestCase):
    def setUp(self) -> None:
        Shop.objects.create(name="Test Shop", brand_name="Test Shop")
        self.staff = User.objects.create_user("orders_staff", password="pw", is_staff=True)
        ct = ContentType.objects.get(app_label="shop", model="shop")
        perm = Permission.objects.get(content_type=ct, codename="manage_orders")
        self.staff.user_permissions.add(perm)
        self.client.force_login(self.staff)

    def test_advance_button_endpoint_moves_confirmed_order_to_preparing(self) -> None:
        order = _order("ADV-CONF", "confirmed")

        response = self.client.post(f"/gestor/pedidos/{order.ref}/advance/")

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "preparing")
        self.assertContains(response, "Marcar pronto")

    def test_advance_button_endpoint_moves_delivery_ready_order_to_dispatched(self) -> None:
        order = _order("ADV-DELIVERY", "ready", "delivery")

        response = self.client.post(f"/gestor/pedidos/{order.ref}/advance/")

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "dispatched")
        self.assertContains(response, "Marcar como Entregue")
