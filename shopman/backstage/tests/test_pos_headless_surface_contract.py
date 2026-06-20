"""Headless POS contract tests for alternate operator surfaces."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from shopman.guestman.models import Customer, CustomerAddress
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Order

from shopman.backstage.api.projections import projection_data
from shopman.backstage.models import CashShift, POSTab, POSTerminal
from shopman.backstage.projections.pos import build_pos
from shopman.shop.models import Channel, Shop
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION


def _grant_pos_perm(user) -> None:
    ct = ContentType.objects.get_for_model(CashShift)
    perm = Permission.objects.get(content_type=ct, codename="operate_pos")
    user.user_permissions.add(perm)


def _grant_adjust_cashshift_perm(user) -> None:
    ct = ContentType.objects.get_for_model(CashShift)
    perm = Permission.objects.get(content_type=ct, codename="adjust_cashshift")
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
        POSTab.objects.create(ref="00001007", label="1007")
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
        self.terminal = POSTerminal.default()
        self.shift = CashShift.objects.create(operator=self.operator, terminal=self.terminal, opening_amount_q=0)

    def test_api_pos_payload_matches_projection_builder(self) -> None:
        response = self.client.get("/api/v1/backstage/pos/")

        self.assertEqual(response.status_code, 200)
        expected = projection_data(build_pos(operator=self.operator))
        payload = response.json()
        self.assertEqual(payload["pos"], expected)
        self.assertEqual(payload["pos"]["products"][0]["sku"], "POS-HEADLESS-ITEM")
        self.assertEqual(payload["pos"]["products"][0]["price_q"], 1300)
        payment_methods = {method["ref"]: method for method in payload["pos"]["payment_methods"]}
        self.assertEqual(payment_methods["cash"]["label"], "Dinheiro")
        self.assertIn("mixed", payment_methods)
        self.assertIn("delivery", {option["ref"] for option in payload["pos"]["fulfillment_options"]})
        payment_collections = {collection["ref"]: collection for collection in payload["pos"]["payment_collections"]}
        self.assertEqual(payment_collections["terminal"]["payment_method_refs"], ["cash", "pix", "card", "mixed"])
        self.assertEqual(payment_collections["on_delivery"]["payment_method_refs"], ["cash", "mixed"])
        action_refs = {action["ref"] for action in payload["pos"]["actions"]}
        self.assertIn("review_sale", action_refs)
        self.assertIn("close_sale", action_refs)
        self.assertIn("reverse_geocode", action_refs)
        self.assertIn("create_tab", action_refs)
        self.assertIn("cancel_recent_sale", action_refs)
        self.assertIn("open_cash_shift", action_refs)
        self.assertIn("close_cash_shift", action_refs)
        self.assertIn("cash_movement", action_refs)
        self.assertTrue(payload["pos"]["cash_runtime"]["has_open_shift"])
        self.assertEqual(payload["pos"]["cash_runtime"]["shift_id"], self.shift.pk)
        self.assertEqual(payload["pos"]["cash_runtime"]["status"], "open")

        checkout = payload["pos"]["checkout"]
        self.assertEqual(checkout["intent_version"], POS_SALE_INTENT_VERSION)
        self.assertIn("customer_tax_id", checkout["allowed_payload_keys"])
        self.assertIn("payment_tenders", checkout["allowed_payload_keys"])
        self.assertIn("manager_approval", checkout["allowed_payload_keys"])
        self.assertEqual(
            {mode["ref"] for mode in checkout["receipt_modes"]},
            {"none", "print", "email"},
        )
        field_refs = {field["ref"]: field for field in checkout["fields"]}
        self.assertEqual(field_refs["delivery_address"]["input_type"], "address_autocomplete")
        self.assertEqual(field_refs["delivery_address"]["capability_ref"], "delivery_address_autocomplete")
        self.assertEqual(field_refs["delivery_address"]["required_when"], {"fulfillment_type": "delivery"})
        self.assertEqual(
            field_refs["tendered_amount_q"]["required_when"],
            {"payment_method": "cash", "payment_collection": "terminal"},
        )
        self.assertTrue(checkout["capabilities"]["supports_split_payment"])
        provider_readiness = {item["provider"]: item for item in checkout["capabilities"]["provider_readiness"]}
        self.assertEqual(set(provider_readiness), {"focus_nfe", "efi_pix", "stripe_card"})
        self.assertIn(provider_readiness["focus_nfe"]["status"], {"ready", "warning", "error"})
        self.assertEqual(checkout["capabilities"]["prepare_checkout_action_ref"], "save_tab")
        self.assertEqual(checkout["capabilities"]["review_action_ref"], "review_sale")
        self.assertEqual(checkout["capabilities"]["customer_lookup_action_ref"], "customer_lookup")
        self.assertEqual(checkout["capabilities"]["address_autocomplete"]["provider"], "google_places")
        self.assertIn("place_id", checkout["capabilities"]["address_autocomplete"]["structured_fields"])
        self.assertEqual(checkout["capabilities"]["tab_lifecycle"]["create_action_ref"], "create_tab")
        self.assertEqual(checkout["capabilities"]["tab_lifecycle"]["tab_ref_format"], "free_text")
        self.assertEqual(checkout["capabilities"]["tab_lifecycle"]["tab_ref_max_length"], 64)
        self.assertEqual(checkout["capabilities"]["tab_lifecycle"]["numeric_refs_zero_padded_to"], 8)
        self.assertFalse(checkout["capabilities"]["tab_lifecycle"]["requires_open_tab_for_cart"])
        self.assertTrue(checkout["capabilities"]["tab_lifecycle"]["requires_tab_before_save"])
        self.assertTrue(checkout["capabilities"]["tab_lifecycle"]["allows_direct_checkout_without_tab"])
        self.assertTrue(checkout["capabilities"]["tab_lifecycle"]["allows_operator_tab_creation"])
        self.assertEqual(checkout["capabilities"]["tab_lifecycle"]["draft_association_target_states"], ["empty"])
        self.assertEqual(checkout["capabilities"]["tab_lifecycle"]["occupied_tab_selection"], "open_existing_not_merge")
        self.assertEqual(checkout["capabilities"]["cash_management"]["movement_kinds"], ["sangria", "suprimento", "ajuste"])
        self.assertEqual(checkout["capabilities"]["sale_correction"]["cancel_recent_action_ref"], "cancel_recent_sale")
        self.assertTrue(checkout["capabilities"]["idempotent_replay"]["safe_for_offline_queue"])

    def test_projection_shows_terminal_occupied_when_other_operator_has_shift(self) -> None:
        User = get_user_model()
        other = User.objects.create_user(username="other-pos-operator", password="x", is_staff=True)
        _grant_pos_perm(other)
        self.shift.close(blind_closing_amount_q=0)
        CashShift.objects.create(operator=other, terminal=self.terminal, opening_amount_q=0)

        payload = projection_data(build_pos(operator=self.operator))

        self.assertFalse(payload["has_open_cash_session"])
        self.assertFalse(payload["cash_runtime"]["has_open_shift"])
        self.assertEqual(payload["cash_runtime"]["status"], "terminal_occupied")
        self.assertEqual(payload["cash_runtime"]["blocking_operator_username"], "other-pos-operator")
        self.assertIn("other-pos-operator", payload["cash_runtime"]["blocking_message"])

        response = self.client.post(
            "/api/v1/backstage/pos/cash/open/",
            {"opening_amount": "0,00", "terminal_ref": self.terminal.ref},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "cash_terminal_occupied")

    def test_api_headless_pos_flow_opens_tab_and_closes_sale(self) -> None:
        opened = self.client.post("/api/v1/backstage/pos/tabs/00001007/open/", {})

        self.assertEqual(opened.status_code, 200)
        tab = opened.json()
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "tab_ref": tab["tab_ref"],
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

    def test_api_headless_pos_can_review_and_close_direct_checkout_without_tab(self) -> None:
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "items": [
                {
                    "sku": "POS-HEADLESS-ITEM",
                    "name": "Headless Item",
                    "qty": 1,
                    "unit_price_q": 1300,
                }
            ],
            "customer_name": "Cliente Rapido",
            "fulfillment_type": "pickup",
            "payment_method": "cash",
            "payment_collection": "terminal",
            "client_request_id": "pos-headless-direct-001",
        }

        reviewed = self.client.post(
            "/api/v1/backstage/pos/sale/review/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(reviewed.json()["review"]["tab_ref"], "")
        self.assertEqual(Order.objects.count(), 0)

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
        self.assertEqual(order.total_q, 1300)
        self.assertEqual(order.data["origin_channel"], "pos")
        self.assertEqual(order.data["payment"]["method"], "cash")
        self.assertEqual(order.data["pos"]["direct_checkout"], True)
        self.assertEqual(order.data["pos"]["client_request_id"], "pos-headless-direct-001")
        self.assertNotIn("tab_ref", order.data)

    @override_settings(
        SHOPMAN_PAYMENT_ADAPTERS={
            "pix": "shopman.shop.adapters.payment_mock",
            "card": "shopman.shop.adapters.payment_mock",
            "cash": None,
            "external": None,
        },
        SHOPMAN_MOCK_PIX_AUTO_CONFIRM=False,
    )
    def test_api_headless_pos_pix_close_returns_gateway_payment_display(self) -> None:
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "items": [
                {
                    "sku": "POS-HEADLESS-ITEM",
                    "name": "Headless Item",
                    "qty": 1,
                    "unit_price_q": 1300,
                }
            ],
            "customer_name": "Cliente PIX",
            "fulfillment_type": "pickup",
            "payment_method": "pix",
            "payment_collection": "terminal",
            "client_request_id": "pos-headless-pix-001",
        }

        closed = self.client.post(
            "/api/v1/backstage/pos/sale/close/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(closed.status_code, 200)
        body = closed.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["payment"]["method"], "pix")
        self.assertEqual(body["payment"]["status"], "pending")
        self.assertTrue(body["payment"]["intent_ref"].startswith("PAY-"))
        self.assertIn("000201", body["payment"]["copy_paste"])
        self.assertTrue(body["payment"]["qr_code"].startswith("data:image/png;base64,"))
        order = Order.objects.get(ref=body["order_ref"])
        self.assertEqual(order.data["payment"]["method"], "pix")
        self.assertEqual(order.data["payment"]["intent_ref"], body["payment"]["intent_ref"])

    def test_api_headless_pos_review_requires_open_cash_shift(self) -> None:
        self.shift.delete()
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "items": [
                {
                    "sku": "POS-HEADLESS-ITEM",
                    "name": "Headless Item",
                    "qty": 1,
                    "unit_price_q": 1300,
                }
            ],
            "fulfillment_type": "pickup",
            "payment_method": "cash",
            "payment_collection": "terminal",
            "client_request_id": "pos-headless-no-shift-001",
        }

        reviewed = self.client.post(
            "/api/v1/backstage/pos/sale/review/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(reviewed.status_code, 409)
        self.assertEqual(reviewed.json()["error"]["code"], "cash_shift_required")
        self.assertEqual(Order.objects.count(), 0)

    def test_api_headless_pos_review_validates_checkout_without_committing(self) -> None:
        opened = self.client.post("/api/v1/backstage/pos/tabs/00001007/open/", {})
        self.assertEqual(opened.status_code, 200)
        tab = opened.json()
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "tab_ref": tab["tab_ref"],
            "tab_session_key": tab["tab_session_key"],
            "items": [
                {
                    "sku": "POS-HEADLESS-ITEM",
                    "name": "Headless Item",
                    "qty": 1,
                    "unit_price_q": 1300,
                }
            ],
            "customer_name": "Cliente Balcao",
            "fulfillment_type": "pickup",
            "payment_method": "cash",
            "payment_collection": "terminal",
            "tendered_amount_q": 2000,
            "receipt_mode": "none",
            "client_request_id": "pos-headless-review-001",
        }

        reviewed = self.client.post(
            "/api/v1/backstage/pos/sale/review/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(reviewed.status_code, 200)
        body = reviewed.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["review"]["total_q"], 1300)
        self.assertEqual(body["review"]["change_q"], 700)
        self.assertEqual(body["review"]["payment_method"], "cash")
        self.assertEqual(Order.objects.count(), 0)

    def test_api_headless_pos_review_computes_manual_discount_canonically(self) -> None:
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "items": [{"sku": "POS-HEADLESS-ITEM", "name": "Headless Item", "qty": 2, "unit_price_q": 1300}],
            "fulfillment_type": "pickup",
            "payment_method": "cash",
            "payment_collection": "terminal",
            "manual_discount": {"type": "percent", "value": "10", "reason": "fidelidade"},
            "client_request_id": "pos-headless-discount-review-001",
        }

        reviewed = self.client.post(
            "/api/v1/backstage/pos/sale/review/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(reviewed.status_code, 200)
        review = reviewed.json()["review"]
        self.assertEqual(review["subtotal_q"], 2600)
        self.assertEqual(review["discount_q"], 260)
        self.assertEqual(review["total_q"], 2340)
        self.assertEqual(Order.objects.count(), 0)

    @override_settings(SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q=50)
    def test_api_headless_pos_close_returns_structured_manager_approval_error(self) -> None:
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "items": [{"sku": "POS-HEADLESS-ITEM", "name": "Headless Item", "qty": 1, "unit_price_q": 1300}],
            "fulfillment_type": "pickup",
            "payment_method": "cash",
            "payment_collection": "terminal",
            "manual_discount": {"type": "fixed", "value": "1,00", "reason": "cortesia"},
            "client_request_id": "pos-headless-manager-approval-001",
        }

        closed = self.client.post(
            "/api/v1/backstage/pos/sale/close/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(closed.status_code, 422)
        self.assertEqual(closed.json()["error"]["code"], "manager_approval_required")
        self.assertEqual(closed.json()["error"]["field"], "manager_approval")
        self.assertEqual(closed.json()["error"]["focus"], "approval")

    @override_settings(SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q=50)
    def test_api_headless_pos_close_accepts_manager_approval_for_canonical_discount(self) -> None:
        from shopman.doorman.models import PinCredential

        manager = get_user_model().objects.create_user(username="pos-manager-api", password="secret", is_staff=True)
        _grant_adjust_cashshift_perm(manager)
        PinCredential.set_for(manager, "4321")
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "items": [{"sku": "POS-HEADLESS-ITEM", "name": "Headless Item", "qty": 1, "unit_price_q": 1300}],
            "fulfillment_type": "pickup",
            "payment_method": "cash",
            "payment_collection": "terminal",
            "manual_discount": {"type": "fixed", "value": "1,00", "reason": "cortesia"},
            "manager_approval": {"username": "pos-manager-api", "pin": "4321"},
            "client_request_id": "pos-headless-manager-approval-002",
        }

        closed = self.client.post(
            "/api/v1/backstage/pos/sale/close/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(closed.status_code, 200)
        order = Order.objects.get(ref=closed.json()["order_ref"])
        self.assertEqual(order.total_q, 1200)
        self.assertEqual(order.data["manual_discount"]["discount_q"], 100)
        self.assertEqual(order.data["manual_discount"]["approved_by"], "pos-manager-api")

    def test_api_headless_pos_review_uses_same_intent_errors_as_close(self) -> None:
        opened = self.client.post("/api/v1/backstage/pos/tabs/00001007/open/", {})
        self.assertEqual(opened.status_code, 200)
        tab = opened.json()
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "tab_ref": tab["tab_ref"],
            "tab_session_key": tab["tab_session_key"],
            "items": [{"sku": "POS-HEADLESS-ITEM", "name": "Headless Item", "qty": 1, "unit_price_q": 1300}],
            "fulfillment_type": "delivery",
            "payment_method": "cash",
        }

        reviewed = self.client.post(
            "/api/v1/backstage/pos/sale/review/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(reviewed.status_code, 422)
        self.assertEqual(reviewed.json()["error"]["code"], "delivery_address_required")
        self.assertEqual(Order.objects.count(), 0)

    def test_api_headless_pos_review_warns_but_close_rejects_incomplete_split_payment(self) -> None:
        opened = self.client.post("/api/v1/backstage/pos/tabs/00001007/open/", {})
        self.assertEqual(opened.status_code, 200)
        tab = opened.json()
        base_payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "tab_ref": tab["tab_ref"],
            "tab_session_key": tab["tab_session_key"],
            "items": [{"sku": "POS-HEADLESS-ITEM", "name": "Headless Item", "qty": 1, "unit_price_q": 1300}],
            "fulfillment_type": "pickup",
            "payment_method": "mixed",
            "payment_collection": "terminal",
            "client_request_id": "pos-headless-split-error-001",
        }

        missing_review = self.client.post(
            "/api/v1/backstage/pos/sale/review/",
            data=json.dumps(base_payload),
            content_type="application/json",
        )
        mismatch_review = self.client.post(
            "/api/v1/backstage/pos/sale/review/",
            data=json.dumps({
                **base_payload,
                "payment_tenders": [{"method": "cash", "amount_q": 1000, "collection": "terminal"}],
            }),
            content_type="application/json",
        )
        missing_close = self.client.post(
            "/api/v1/backstage/pos/sale/close/",
            data=json.dumps(base_payload),
            content_type="application/json",
        )
        mismatch_close = self.client.post(
            "/api/v1/backstage/pos/sale/close/",
            data=json.dumps({
                **base_payload,
                "client_request_id": "pos-headless-split-error-002",
                "payment_tenders": [{"method": "cash", "amount_q": 1000, "collection": "terminal"}],
            }),
            content_type="application/json",
        )

        self.assertEqual(missing_review.status_code, 200)
        self.assertEqual(missing_review.json()["review"]["warnings"][0]["code"], "payment_tenders_required")
        self.assertEqual(mismatch_review.status_code, 200)
        self.assertEqual(mismatch_review.json()["review"]["warnings"][0]["code"], "payment_tenders_total_mismatch")
        self.assertEqual(missing_close.status_code, 422)
        self.assertEqual(missing_close.json()["error"]["code"], "payment_tenders_required")
        self.assertEqual(missing_close.json()["error"]["focus"], "payment")
        self.assertEqual(mismatch_close.status_code, 422)
        self.assertEqual(mismatch_close.json()["error"]["code"], "payment_tenders_total_mismatch")
        self.assertEqual(mismatch_close.json()["error"]["field"], "payment_tenders")
        self.assertEqual(Order.objects.count(), 0)

    def test_api_headless_pos_split_with_change_is_accepted(self) -> None:
        """Split que COBRE o total (excedente = troco) passa — não é mismatch.

        Regressão: antes a validação exigia soma EXATA (`!= total`), então uma
        linha de dinheiro recebida a mais (troco) era rejeitada por engano.
        """
        opened = self.client.post("/api/v1/backstage/pos/tabs/00001008/open/", {})
        self.assertEqual(opened.status_code, 200)
        tab = opened.json()
        # total = 1300; card 1000 + cash 500 = 1500 → cobre, troco 200.
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "tab_ref": tab["tab_ref"],
            "tab_session_key": tab["tab_session_key"],
            "items": [{"sku": "POS-HEADLESS-ITEM", "name": "Headless Item", "qty": 1, "unit_price_q": 1300}],
            "fulfillment_type": "pickup",
            "payment_method": "mixed",
            "payment_collection": "terminal",
            "client_request_id": "pos-headless-split-change-001",
            "payment_tenders": [
                {"method": "card", "amount_q": 1000, "collection": "terminal"},
                {"method": "cash", "amount_q": 500, "collection": "terminal"},
            ],
        }

        review = self.client.post(
            "/api/v1/backstage/pos/sale/review/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(review.status_code, 200)
        review_body = review.json()["review"]
        codes = [w["code"] for w in review_body["warnings"]]
        self.assertNotIn("payment_tenders_total_mismatch", codes)
        self.assertEqual(review_body["change_q"], 200)

        close = self.client.post(
            "/api/v1/backstage/pos/sale/close/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(close.status_code, 200)
        self.assertEqual(Order.objects.count(), 1)

    def test_api_customer_lookup_returns_memory_and_default_address_projection(self) -> None:
        customer = Customer.objects.create(
            ref="CUST-POS-HEADLESS",
            first_name="Lia",
            last_name="Cliente",
            phone="+5543999993333",
            email="lia@example.com",
        )
        CustomerAddress.objects.create(
            customer=customer,
            label="home",
            formatted_address="Rua Headless, 77",
            route="Rua Headless",
            street_number="77",
            neighborhood="Centro",
            city="Londrina",
            state_code="PR",
            postal_code="86000-000",
            latitude=-23.3,
            longitude=-51.1,
            place_id="ChIJ-pos-headless",
            is_default=True,
        )
        Order.objects.create(
            ref="ORD-POS-HEADLESS-MEM",
            channel_ref="pdv",
            session_key="sess-pos-headless-mem",
            status=Order.Status.COMPLETED,
            snapshot={
                "items": [{"sku": "POS-HEADLESS-ITEM", "name": "Headless Item", "qty": 2, "unit_price_q": 1300}],
                "pricing": {"total_q": 2600},
            },
            data={"customer_ref": customer.ref, "customer": {"ref": customer.ref, "name": customer.name}},
            total_q=2600,
        )

        response = self.client.get("/api/v1/backstage/pos/customer/lookup/?phone=(43)%2099999-3333")

        self.assertEqual(response.status_code, 200)
        lookup = response.json()["customer"]
        self.assertEqual(lookup["ref"], customer.ref)
        self.assertEqual(lookup["email"], "lia@example.com")
        self.assertEqual(lookup["default_address"]["place_id"], "ChIJ-pos-headless")
        self.assertEqual(lookup["default_address"]["route"], "Rua Headless")
        self.assertEqual(lookup["saved_addresses"][0]["place_id"], "ChIJ-pos-headless")
        self.assertEqual(lookup["memory"]["total_orders"], 1)
        self.assertEqual(lookup["memory"]["favorite_item"]["sku"], "POS-HEADLESS-ITEM")

    def test_api_customer_search_matches_any_unique_key(self) -> None:
        Customer.objects.create(
            ref="CUST-SEARCH-1",
            first_name="Bruno",
            last_name="Souza",
            phone="+5543988887777",
            email="bruno@example.com",
            document="11122233344",
        )

        def refs(query: str) -> list[str]:
            response = self.client.get(f"/api/v1/backstage/pos/customer/search/?q={query}")
            self.assertEqual(response.status_code, 200)
            return [row["ref"] for row in response.json()["results"]]

        self.assertIn("CUST-SEARCH-1", refs("Bruno"))       # by name
        self.assertIn("CUST-SEARCH-1", refs("98888"))       # by phone fragment
        self.assertIn("CUST-SEARCH-1", refs("bruno@example"))  # by email
        self.assertIn("CUST-SEARCH-1", refs("11122233"))    # by document (CPF)
        # too short → no results (avoid scanning on a single character)
        self.assertEqual(self.client.get("/api/v1/backstage/pos/customer/search/?q=b").json()["results"], [])

    def test_api_customer_resolve_creates_just_in_time_and_is_idempotent(self) -> None:
        before = Customer.objects.count()
        # A fresh name+phone → created NOW (not deferred to order commit).
        created = self.client.post(
            "/api/v1/backstage/pos/customer/resolve/",
            {"customer_name": "Cliente JIT", "customer_phone": "43966665555"},
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 200)
        customer = created.json()["customer"]
        self.assertIsNotNone(customer)
        self.assertEqual(customer["name"], "Cliente JIT")
        self.assertEqual(Customer.objects.count(), before + 1)
        ref = customer["ref"]
        # Resolving the same identifiers again returns the same customer (no dup).
        again = self.client.post(
            "/api/v1/backstage/pos/customer/resolve/",
            {"customer_name": "Cliente JIT", "customer_phone": "43966665555"},
            content_type="application/json",
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["customer"]["ref"], ref)
        self.assertEqual(Customer.objects.count(), before + 1)

    def test_api_customer_resolve_empty_returns_null(self) -> None:
        response = self.client.post(
            "/api/v1/backstage/pos/customer/resolve/", {}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["customer"])

    def test_api_headless_pos_can_cancel_recent_sale_through_pos_contract(self) -> None:
        opened = self.client.post("/api/v1/backstage/pos/tabs/00001007/open/", {})
        self.assertEqual(opened.status_code, 200)
        tab = opened.json()
        closed = self.client.post(
            "/api/v1/backstage/pos/sale/close/",
            data=json.dumps({
                "intent_version": POS_SALE_INTENT_VERSION,
                "tab_ref": tab["tab_ref"],
                "tab_session_key": tab["tab_session_key"],
                "items": [{"sku": "POS-HEADLESS-ITEM", "name": "Headless Item", "qty": 1, "unit_price_q": 1300}],
                "payment_method": "cash",
                "payment_collection": "terminal",
                "client_request_id": "pos-headless-cancel-001",
            }),
            content_type="application/json",
        )
        self.assertEqual(closed.status_code, 200)
        order_ref = closed.json()["order_ref"]

        cancelled = self.client.post(
            "/api/v1/backstage/pos/sale/recent/cancel/",
            data=json.dumps({"order_ref": order_ref, "reason": "Erro de lançamento"}),
            content_type="application/json",
        )

        self.assertEqual(cancelled.status_code, 200)
        order = Order.objects.get(ref=order_ref)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.data["pos_correction_reason"], "Erro de lançamento")
