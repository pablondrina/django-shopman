from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from shopman.orderman.models import Order

from shopman.backstage.models import CashShift, POSTab, POSTerminal
from shopman.shop.models import Channel, Shop
from shopman.shop.services import operator_orders
from shopman.shop.services import pos as pos_service


class POSCommercialCompletionTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
        POSTab.objects.create(ref="00001007", label="1007")
        from shopman.offerman.models import Product

        Product.objects.create(
            sku="POS-COMM-ITEM",
            name="Commercial Item",
            base_price_q=1200,
            is_published=True,
            is_sellable=True,
        )
        User = get_user_model()
        self.operator = User.objects.create_user(username="commercial-pos", password="x", is_staff=True)
        self.terminal = POSTerminal.default()

    def _open_tab(self) -> dict:
        return pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_ref="1007",
            actor="pos:commercial-pos",
            operator_username="commercial-pos",
        )

    def _payload(self, opened: dict, **overrides) -> dict:
        payload = {
            "items": [{"sku": "POS-COMM-ITEM", "name": "Commercial Item", "qty": 1, "unit_price_q": 1200}],
            "customer_name": "Cliente POS",
            "payment_method": "cash",
            "tab_ref": opened["tab_ref"],
            "tab_session_key": opened["tab_session_key"],
            "client_request_id": "pos:test-commercial-001",
        }
        payload.update(overrides)
        return payload

    def test_split_tender_persists_mixed_payment_and_counts_only_cash_in_shift(self) -> None:
        shift = CashShift.objects.create(operator=self.operator, terminal=self.terminal, opening_amount_q=1000)
        opened = self._open_tab()

        result = pos_service.close_sale(
            channel_ref="pdv",
            payload=self._payload(
                opened,
                cash_shift_id=shift.pk,
                pos_terminal_ref=self.terminal.ref,
                payment_tenders=[
                    {"method": "cash", "amount_q": 500, "collection": "terminal"},
                    {"method": "pix", "amount_q": 700, "collection": "terminal", "reference": "PIX-123"},
                ],
            ),
            actor="pos:commercial-pos",
            operator_username="commercial-pos",
        )

        order = Order.objects.get(ref=result.order_ref)
        payment = order.data["payment"]
        self.assertEqual(payment["method"], "mixed")
        self.assertEqual(payment["cash_received_q"], 500)
        self.assertEqual(payment["tenders"][1]["reference"], "PIX-123")

        shift.close(blind_closing_amount_q=1500)
        self.assertEqual(shift.expected_amount_q, 1500)
        self.assertEqual(shift.difference_q, 0)

    def test_duplicate_client_request_id_returns_existing_order_after_commit(self) -> None:
        opened = self._open_tab()
        payload = self._payload(opened, client_request_id="pos:idem-commercial-001", tendered_amount_q=1200)

        first = pos_service.close_sale(
            channel_ref="pdv",
            payload=payload,
            actor="pos:commercial-pos",
            operator_username="commercial-pos",
        )
        second = pos_service.close_sale(
            channel_ref="pdv",
            payload=payload,
            actor="pos:commercial-pos",
            operator_username="commercial-pos",
        )

        self.assertEqual(second.order_ref, first.order_ref)
        self.assertEqual(Order.objects.filter(data__pos__client_request_id="pos:idem-commercial-001").count(), 1)

    def test_delivery_cash_settlement_moves_on_delivery_cash_to_active_shift(self) -> None:
        shift = CashShift.objects.create(operator=self.operator, terminal=self.terminal, opening_amount_q=0)
        order = Order.objects.create(
            ref="ORD-COD-SETTLE",
            channel_ref="pdv",
            session_key="sess-cod-settle",
            status=Order.Status.DISPATCHED,
            snapshot={"items": [], "data": {"fulfillment_type": "delivery"}},
            data={
                "fulfillment_type": "delivery",
                "payment": {
                    "method": "cash",
                    "collection": "on_delivery",
                    "tenders": [{"method": "cash", "amount_q": 1200, "collection": "on_delivery", "status": "pending"}],
                },
            },
            total_q=1200,
        )

        amount_q = operator_orders.settle_delivery_cash(
            order,
            cash_shift=shift,
            actor="operator:commercial-pos",
        )
        order.refresh_from_db()

        self.assertEqual(amount_q, 1200)
        self.assertEqual(order.data["payment"]["cod_cash_shift_id"], shift.pk)
        self.assertEqual(order.data["payment"]["cash_received_q"], 1200)
        self.assertEqual(order.events.filter(type="payment_collected").count(), 1)

        shift.close(blind_closing_amount_q=1200)
        self.assertEqual(shift.expected_amount_q, 1200)
        self.assertEqual(shift.difference_q, 0)
