"""POS sale intent contract, proactive delivery, and customer memory tests."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from shopman.backstage.models import CashShift, POSTab, POSTerminal
from shopman.guestman.models import Customer
from shopman.orderman.models import Order
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import (
    POS_SALE_INTENT_PAYLOAD_KEYS,
    POS_SALE_INTENT_RECEIPT_MODES,
    POS_SALE_INTENT_VERSION,
    PosIntentError,
    parse_pos_sale_intent,
)


def _grant_pos_perm(user):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    from shopman.backstage.models import CashRegisterSession

    ct = ContentType.objects.get_for_model(CashRegisterSession)
    perm = Permission.objects.get(content_type=ct, codename="operate_pos")
    user.user_permissions.add(perm)


class PosSaleIntentParserTests(TestCase):
    def test_exposes_public_contract_constants_for_projections(self) -> None:
        self.assertIn("customer_tax_id", POS_SALE_INTENT_PAYLOAD_KEYS)
        self.assertIn("payment_tenders", POS_SALE_INTENT_PAYLOAD_KEYS)
        self.assertIn("manager_approval", POS_SALE_INTENT_PAYLOAD_KEYS)
        self.assertEqual(set(POS_SALE_INTENT_RECEIPT_MODES), {"none", "print", "email"})

    def test_rejects_unknown_intent_version(self) -> None:
        with self.assertRaises(PosIntentError) as ctx:
            parse_pos_sale_intent({"intent_version": "pos.sale-intent.v99", "items": []})

        self.assertEqual(ctx.exception.code, "unknown_intent_version")
        self.assertEqual(ctx.exception.status, 400)

    def test_rejects_unexpected_field(self) -> None:
        with self.assertRaises(PosIntentError) as ctx:
            parse_pos_sale_intent({
                "intent_version": POS_SALE_INTENT_VERSION,
                "items": [{"sku": "SKU", "qty": 1, "unit_price_q": 100}],
                "admin_override_total_q": 1,
            })

        self.assertEqual(ctx.exception.code, "unexpected_intent_field")
        self.assertEqual(ctx.exception.field, "admin_override_total_q")

    def test_requires_delivery_address_for_commit(self) -> None:
        with self.assertRaises(PosIntentError) as ctx:
            parse_pos_sale_intent({
                "intent_version": POS_SALE_INTENT_VERSION,
                "items": [{"sku": "SKU", "qty": 1, "unit_price_q": 1000}],
                "fulfillment_type": "delivery",
                "tab_code": "00000001",
            })

        self.assertEqual(ctx.exception.code, "delivery_address_required")
        self.assertEqual(ctx.exception.focus, "delivery_address")

    def test_normalizes_valid_intent(self) -> None:
        intent = parse_pos_sale_intent({
            "intent_version": POS_SALE_INTENT_VERSION,
            "items": [{"sku": "SKU", "name": "Produto", "qty": "2", "unit_price_q": "500"}],
            "fulfillment_type": "delivery",
            "delivery_address": "Rua A, 10",
            "delivery_address_structured": {
                "formatted_address": "Rua A, 10 - Centro, Londrina - PR",
                "route": "Rua A",
                "street_number": "10",
                "neighborhood": "Centro",
                "city": "Londrina",
                "state_code": "PR",
                "postal_code": "86000-000",
                "latitude": "-23.3",
                "longitude": "-51.1",
                "place_id": "ChIJ-pos-intent",
                "delivery_instructions": "Portaria",
                "is_verified": True,
                "ignored": "x",
            },
            "payment_method": "cash",
            "payment_collection": "on_delivery",
            "tab_code": "00000001",
        })

        self.assertEqual(intent.payload["items"][0]["qty"], 2)
        structured = intent.payload["delivery_address_structured"]
        self.assertEqual(structured["route"], "Rua A")
        self.assertEqual(structured["place_id"], "ChIJ-pos-intent")
        self.assertEqual(structured["latitude"], -23.3)
        self.assertEqual(structured["longitude"], -51.1)
        self.assertNotIn("ignored", structured)
        self.assertEqual(intent.payload["payment_collection"], "on_delivery")

    def test_allows_direct_checkout_intent_without_tab(self) -> None:
        intent = parse_pos_sale_intent({
            "intent_version": POS_SALE_INTENT_VERSION,
            "items": [{"sku": "SKU", "name": "Produto", "qty": "1", "unit_price_q": "500"}],
            "fulfillment_type": "pickup",
            "payment_method": "cash",
        })

        self.assertEqual(intent.payload["tab_code"], "")
        self.assertEqual(intent.payload["tab_session_key"], "")
        self.assertEqual(intent.payload["payment_method"], "cash")


class PosIntentViewContractTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
        from shopman.offerman.models import Product

        Product.objects.create(
            sku="POS-INTENT-ITEM",
            name="Intent Item",
            base_price_q=1200,
            is_published=True,
            is_sellable=True,
        )
        POSTab.objects.create(code="00001007", label="1007")
        User = get_user_model()
        self.operator = User.objects.create_user(username="intent-pos", password="x", is_staff=True)
        _grant_pos_perm(self.operator)
        self.client.force_login(self.operator)
        self.terminal = POSTerminal.default()
        self.shift = CashShift.objects.create(operator=self.operator, terminal=self.terminal, opening_amount_q=0)

    def _opened(self) -> dict:
        return pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_code="1007",
            actor="pos:intent-pos",
            operator_username="intent-pos",
        )

    def test_close_rejects_unknown_intent_version_with_stable_error_code(self) -> None:
        opened = self._opened()
        payload = {
            "intent_version": "pos.sale-intent.v99",
            "items": [{"sku": "POS-INTENT-ITEM", "name": "Intent Item", "qty": 1, "unit_price_q": 1200}],
            "tab_code": opened["tab_code"],
            "tab_session_key": opened["tab_session_key"],
        }

        response = self.client.post("/gestor/pos/close/", {"payload": json.dumps(payload)})

        self.assertEqual(response.status_code, 400)
        body = response.content.decode()
        self.assertIn('data-error-code="unknown_intent_version"', body)
        self.assertIn('data-focus-target="search"', body)

    def test_close_persists_intent_metadata_and_reconciles_delivery_fee(self) -> None:
        opened = self._opened()
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "items": [{"sku": "POS-INTENT-ITEM", "name": "Intent Item", "qty": 1, "unit_price_q": 1200}],
            "customer_name": "Cliente Intent",
            "customer_memory_action": "favorite_item",
            "fulfillment_type": "delivery",
            "delivery_address": "Rua A, 10, Centro",
            "delivery_address_structured": {"route": "Rua A", "street_number": "10", "neighborhood": "Centro"},
            "delivery_fee_q": 300,
            "payment_method": "cash",
            "tendered_amount_q": 1500,
            "tab_code": opened["tab_code"],
            "tab_session_key": opened["tab_session_key"],
            "client_request_id": "pos:intent-contract-001",
        }

        response = self.client.post("/gestor/pos/close/", {"payload": json.dumps(payload)})

        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(data__pos__client_request_id="pos:intent-contract-001")
        self.assertEqual(order.total_q, 1500)
        self.assertEqual(order.data["delivery_fee_q"], 300)
        self.assertEqual(order.data["delivery_address_structured"]["neighborhood"], "Centro")
        self.assertEqual(order.data["payment"]["amount_q"], 1500)
        self.assertEqual(order.data["payment"]["tenders"][0]["amount_q"], 1500)
        self.assertEqual(order.data["pos"]["intent_version"], POS_SALE_INTENT_VERSION)
        self.assertEqual(order.data["pos"]["customer_memory_action"], "favorite_item")

    def test_customer_lookup_exposes_memory_action_payloads(self) -> None:
        customer = Customer.objects.create(
            ref="CUST-POS-INTENT-MEM",
            first_name="Lia",
            last_name="Cliente",
            phone="+5543999992222",
        )
        Order.objects.create(
            ref="ORD-POS-INTENT-HIST",
            channel_ref="pdv",
            session_key="sess-pos-intent-hist",
            status=Order.Status.COMPLETED,
            snapshot={
                "items": [{"sku": "POS-INTENT-ITEM", "name": "Intent Item", "qty": 2, "unit_price_q": 1200}],
                "pricing": {"total_q": 2400},
            },
            data={"customer_ref": customer.ref, "customer": {"ref": customer.ref, "name": customer.name}},
            total_q=2400,
        )

        response = self.client.post("/gestor/pos/customer-lookup/", {"phone": "(43) 99999-2222"})

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("data-favorite-item", body)
        self.assertIn("data-last-order-items", body)
        self.assertIn("POS-INTENT-ITEM", body)
