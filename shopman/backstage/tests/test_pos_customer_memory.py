"""POS customer memory and delivery handoff behavior."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from shopman.guestman.contrib.insights.models import CustomerInsight
from shopman.guestman.contrib.timeline.models import TimelineEvent
from shopman.guestman.models import Customer, CustomerAddress
from shopman.orderman.models import Fulfillment, Order

from shopman.backstage.models import POSTab
from shopman.backstage.projections.pos import build_open_tab
from shopman.shop.models import Channel, Shop
from shopman.shop.services import customer as customer_service
from shopman.shop.services import operator_orders
from shopman.shop.services import pos as pos_service


def _grant_pos_perm(user):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    from shopman.backstage.models import CashShift

    ct = ContentType.objects.get_for_model(CashShift)
    perm = Permission.objects.get(content_type=ct, codename="operate_pos")
    user.user_permissions.add(perm)


class POSCustomerMemoryTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
        POSTab.objects.create(ref="00001007", label="1007")
        from shopman.offerman.models import Product

        Product.objects.create(
            sku="POS-MEM-ITEM",
            name="Memory Item",
            base_price_q=1200,
            is_published=True,
            is_sellable=True,
        )

    def _open_tab(self) -> dict:
        return build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_ref="1007",
            actor="pos:ana",
            operator_username="ana",
        ))

    def _payload(self, opened: dict, **overrides) -> dict:
        payload = {
            "items": [{"sku": "POS-MEM-ITEM", "name": "Memory Item", "qty": 1, "unit_price_q": 1200}],
            "customer_name": "Ana Cliente",
            "customer_phone": "",
            "payment_method": "cash",
            "tab_ref": opened["tab_ref"],
            "tab_session_key": opened["tab_session_key"],
        }
        payload.update(overrides)
        return payload

    def test_pos_creates_customer_ref_even_with_name_only_data(self) -> None:
        opened = self._open_tab()

        result = pos_service.close_sale(
            channel_ref="pdv",
            payload=self._payload(opened),
            actor="pos:ana",
            operator_username="ana",
        )

        order = Order.objects.get(ref=result.order_ref)
        customer_ref = order.data["customer_ref"]
        customer = Customer.objects.get(ref=customer_ref)
        self.assertEqual(customer.name, "Ana Cliente")
        self.assertEqual(order.data["customer"]["ref"], customer.ref)

        customer_service.ensure(order)
        self.assertTrue(
            TimelineEvent.objects.filter(
                customer=customer,
                event_type="order",
                reference=f"order:{order.ref}",
            ).exists()
        )
        insight = CustomerInsight.objects.get(customer=customer)
        self.assertEqual(insight.total_orders, 1)
        self.assertEqual(insight.total_spent_q, 1200)

    def test_pos_merges_tax_email_and_delivery_address_into_existing_customer(self) -> None:
        customer = Customer.objects.create(
            ref="CUST-POS-MERGE",
            first_name="Ana",
            last_name="",
            phone="+5543999990000",
            source_system="seed",
        )
        opened = self._open_tab()

        result = pos_service.close_sale(
            channel_ref="pdv",
            payload=self._payload(
                opened,
                customer_name="Ana Maria",
                customer_phone="(43) 99999-0000",
                customer_tax_id="123.456.789-01",
                receipt_mode="email",
                receipt_email="ana@example.com",
                fulfillment_type="delivery",
                delivery_address="Rua das Flores, 100 - Centro, Londrina - PR",
                delivery_address_structured={
                    "formatted_address": "Rua das Flores, 100 - Centro, Londrina - PR",
                    "route": "Rua das Flores",
                    "street_number": "100",
                    "neighborhood": "Centro",
                    "city": "Londrina",
                    "state_code": "PR",
                    "postal_code": "86000-000",
                    "latitude": -23.3,
                    "longitude": -51.1,
                    "place_id": "ChIJ-pos-merge-address",
                    "delivery_instructions": "Portaria",
                },
                payment_collection="on_delivery",
            ),
            actor="pos:ana",
            operator_username="ana",
        )

        order = Order.objects.get(ref=result.order_ref)
        customer.refresh_from_db()
        self.assertEqual(order.data["customer_ref"], customer.ref)
        self.assertEqual(customer.document, "12345678901")
        self.assertEqual(customer.email, "ana@example.com")
        self.assertEqual(customer.last_name, "Maria")
        self.assertTrue(
            CustomerAddress.objects.filter(
                customer=customer,
                formatted_address="Rua das Flores, 100 - Centro, Londrina - PR",
                is_default=True,
            ).exists()
        )
        address = CustomerAddress.objects.get(customer=customer)
        self.assertEqual(address.route, "Rua das Flores")
        self.assertEqual(address.street_number, "100")
        self.assertEqual(address.neighborhood, "Centro")
        self.assertEqual(address.place_id, "ChIJ-pos-merge-address")
        self.assertEqual(float(address.latitude), -23.3)
        self.assertEqual(order.data["customer"]["email"], "ana@example.com")

    def test_pos_customer_lookup_exposes_consumption_memory_and_default_address(self) -> None:
        customer = Customer.objects.create(
            ref="CUST-POS-LOOKUP",
            first_name="Bruno",
            last_name="Souza",
            phone="+5543999991111",
        )
        CustomerAddress.objects.create(
            customer=customer,
            label="home",
            formatted_address="Rua do Cliente, 42",
            is_default=True,
        )
        Order.objects.create(
            ref="ORD-POS-HIST-1",
            channel_ref="pdv",
            session_key="sess-pos-hist-1",
            status=Order.Status.COMPLETED,
            snapshot={"items": [{"sku": "POS-MEM-ITEM", "name": "Memory Item", "qty": 2}], "pricing": {"total_q": 2400}},
            data={"customer_ref": customer.ref, "customer": {"ref": customer.ref, "name": customer.name}},
            total_q=2400,
        )

        User = get_user_model()
        staff = User.objects.create_user(username="pos_lookup", password="x", is_staff=True)
        _grant_pos_perm(staff)
        self.client.force_login(staff)

        response = self.client.post("/gestor/pos/customer-lookup/", {"phone": "(43) 99999-1111"})

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(f'data-customer-ref="{customer.ref}"', body)
        self.assertIn('data-default-address="Rua do Cliente, 42"', body)
        self.assertIn("1 pedidos", body)
        self.assertIn("prefere Memory Item", body)


class DeliveryOrderManagerLifecycleTests(TestCase):
    def test_delivery_advance_updates_fulfillment_for_order_manager_handoff(self) -> None:
        order = Order.objects.create(
            ref="ORD-DELIVERY-LIFE",
            channel_ref="pdv",
            session_key="sess-delivery-life",
            status=Order.Status.READY,
            snapshot={"items": [], "data": {"fulfillment_type": "delivery"}},
            data={"fulfillment_type": "delivery"},
            total_q=2500,
        )
        fulfillment = Fulfillment.objects.create(order=order)

        dispatched = operator_orders.advance_order(order, actor="operator:ana")
        order.refresh_from_db()
        fulfillment.refresh_from_db()

        self.assertEqual(dispatched, Order.Status.DISPATCHED)
        self.assertEqual(order.status, Order.Status.DISPATCHED)
        self.assertEqual(fulfillment.status, Fulfillment.Status.DISPATCHED)

        delivered = operator_orders.advance_order(order, actor="operator:ana")
        order.refresh_from_db()
        fulfillment.refresh_from_db()

        self.assertEqual(delivered, Order.Status.DELIVERED)
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertEqual(fulfillment.status, Fulfillment.Status.DELIVERED)
