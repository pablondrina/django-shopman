from __future__ import annotations

from django.test import TestCase
from shopman.guestman.adapters.orderman import OrdermanOrderHistoryBackend
from shopman.guestman.models import Customer, CustomerGroup
from shopman.orderman.models import Order


class GuestmanOrderHistoryTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        group = CustomerGroup.objects.create(ref="regular", name="Regular", is_default=True, priority=0)
        self.customer = Customer.objects.create(
            ref="CUST-HIST-001",
            first_name="Ana",
            last_name="Silva",
            phone="+5543999990001",
            group=group,
        )
        self.backend = OrdermanOrderHistoryBackend()

    def test_reads_orders_via_customer_ref_in_order_data(self) -> None:
        Order.objects.create(
            ref="ORD-HIST-001",
            channel_ref="web",
            session_key="sess-hist-1",
            status=Order.Status.COMPLETED,
            snapshot={"pricing": {"total_q": 2500}, "items": [{"sku": "SKU-1"}]},
            data={"customer_ref": self.customer.ref},
            total_q=2500,
        )
        Order.objects.create(
            ref="ORD-HIST-002",
            channel_ref="web",
            session_key="sess-hist-2",
            status=Order.Status.CANCELLED,
            snapshot={"pricing": {"total_q": 900}, "items": [{"sku": "SKU-2"}]},
            data={"customer_ref": "OTHER-CUST"},
            total_q=900,
        )

        orders = self.backend.get_customer_orders(self.customer.ref)
        stats = self.backend.get_order_stats(self.customer.ref)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].order_ref, "ORD-HIST-001")
        self.assertEqual(stats.total_orders, 1)
        self.assertEqual(stats.total_spent_q, 2500)
