"""Headless POS contract tests for alternate operator surfaces."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from shopman.backstage.api.projections import projection_data
from shopman.backstage.models import CashRegisterSession, POSTab
from shopman.backstage.projections.pos import build_pos
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Order
from shopman.shop.models import Channel, Shop
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION


def _grant_pos_perm(user) -> None:
    ct = ContentType.objects.get_for_model(CashRegisterSession)
    perm = Permission.objects.get(content_type=ct, codename="operate_pos")
    user.user_permissions.add(perm)


class POSHeadlessSurfaceContractTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(
            ref="pdv",
            name="PDV",
            is_active=True,
            config={
                "payment": {"method": "cash", "timing": "external"},
                "surface_policy": {"fulfillment_types": ["pickup", "delivery"]},
            },
        )
        POSTab.objects.create(code="00001007", label="1007")
        product = Product.objects.create(
            sku="POS-HEADLESS-ITEM",
            name="Headless Item",
            base_price_q=1200,
            is_published=True,
            is_sellable=True,
        )
        listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
        ListingItem.objects.create(
            listing=listing,
            product=product,
            price_q=1300,
            is_published=True,
            is_sellable=True,
        )

        User = get_user_model()
        self.operator = User.objects.create_user(username="pos-headless", password="x", is_staff=True)
        _grant_pos_perm(self.operator)
        self.client.force_login(self.operator)

    def test_api_pos_payload_matches_projection_builder(self) -> None:
        response = self.client.get("/api/v1/backstage/pos/")

        self.assertEqual(response.status_code, 200)
        expected = projection_data(build_pos())
        payload = response.json()
        self.assertEqual(payload["pos"], expected)
        self.assertEqual(payload["pos"]["products"][0]["sku"], "POS-HEADLESS-ITEM")
        self.assertEqual(payload["pos"]["products"][0]["price_q"], 1300)
        self.assertIn("delivery", {option["ref"] for option in payload["pos"]["fulfillment_options"]})
        payment_collections = {collection["ref"]: collection for collection in payload["pos"]["payment_collections"]}
        self.assertEqual(payment_collections["terminal"]["payment_method_refs"], ["cash", "pix", "card"])
        self.assertEqual(payment_collections["on_delivery"]["payment_method_refs"], ["cash"])
        self.assertIn("close_sale", {action["ref"] for action in payload["pos"]["actions"]})

    def test_api_headless_pos_flow_opens_tab_and_closes_sale(self) -> None:
        opened = self.client.post("/api/v1/backstage/pos/tabs/00001007/open/", {})

        self.assertEqual(opened.status_code, 200)
        tab = opened.json()
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "tab_code": tab["tab_code"],
            "tab_session_key": tab["tab_session_key"],
            "items": [
                {
                    "sku": "POS-HEADLESS-ITEM",
                    "name": "Headless Item",
                    "qty": 2,
                    "unit_price_q": 1300,
                }
            ],
            "customer_name": "Cliente Balcao",
            "customer_phone": "(43) 99999-0000",
            "fulfillment_type": "pickup",
            "payment_method": "cash",
            "payment_collection": "terminal",
            "client_request_id": "pos-headless-contract-001",
        }

        closed = self.client.post(
            "/api/v1/backstage/pos/sale/close/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(closed.status_code, 200)
        body = closed.json()
        self.assertTrue(body["ok"])
        order = Order.objects.get(ref=body["order_ref"])
        self.assertEqual(order.channel_ref, "pdv")
        self.assertEqual(order.total_q, 2600)
        self.assertEqual(order.data["origin_channel"], "pos")
        self.assertEqual(order.data["fulfillment_type"], "pickup")
        self.assertEqual(order.data["payment"]["method"], "cash")
        self.assertEqual(order.data["payment"]["amount_q"], 2600)
        self.assertEqual(order.data["pos"]["client_request_id"], "pos-headless-contract-001")
