"""POS tab command semantics."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from shopman.orderman.models import Order, Session

from shopman.backstage.models import POSTab
from shopman.backstage.projections.pos import build_pos_tabs
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service


def _grant_pos_perm(user):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    from shopman.backstage.models import CashRegisterSession

    ct = ContentType.objects.get_for_model(CashRegisterSession)
    perm = Permission.objects.get(content_type=ct, codename="operate_pos")
    user.user_permissions.add(perm)


def _payload(
    *,
    sku: str = "POS-TAB-ITEM",
    name: str = "Tab Item",
    qty: int = 1,
    customer_name: str = "Ana",
    customer_phone: str = "",
    tab_code: str = "00001007",
    tab_session_key: str = "",
) -> dict:
    return {
        "items": [{"sku": sku, "name": name, "qty": qty, "unit_price_q": 1000}],
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "payment_method": "cash",
        "manual_discount": None,
        "tab_code": tab_code,
        "tab_session_key": tab_session_key or None,
    }


@override_settings(SHOPMAN_HAPPY_HOUR_START="00:00", SHOPMAN_HAPPY_HOUR_END="00:00")
class POSTabSessionTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
        POSTab.objects.create(code="00001007", label="1007")
        POSTab.objects.create(code="00001008", label="1008")
        from shopman.offerman.models import Product

        Product.objects.create(
            sku="POS-TAB-ITEM",
            name="Tab Item",
            base_price_q=1000,
            is_published=True,
            is_sellable=True,
        )
        Product.objects.create(
            sku="POS-TAB-ALT",
            name="Alt Item",
            base_price_q=1000,
            is_published=True,
            is_sellable=True,
        )

    def test_opening_empty_tab_creates_open_session(self) -> None:
        payload = pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_code="1007",
            actor="pos:alice",
            operator_username="alice",
        )

        self.assertEqual(payload["tab_code"], "00001007")
        self.assertEqual(payload["tab_display"], "1007")
        self.assertEqual(payload["items"], [])
        session = Session.objects.get(session_key=payload["tab_session_key"])
        self.assertEqual(session.handle_type, "pos_tab")
        self.assertEqual(session.handle_ref, "00001007")
        self.assertEqual(session.data["tab_code"], "00001007")

    def test_saving_tab_keeps_single_in_use_session(self) -> None:
        opened = pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_code="00001007",
            actor="pos:alice",
            operator_username="alice",
        )

        saved = pos_service.save_pos_tab(
            channel_ref="pdv",
            payload=_payload(qty=2, tab_session_key=opened["tab_session_key"]),
            actor="pos:alice",
            operator_username="alice",
        )

        self.assertEqual(saved.tab_code, "00001007")
        session = Session.objects.get(session_key=saved.session_key)
        self.assertEqual(Session.objects.filter(channel_ref="pdv", state="open").count(), 1)
        self.assertEqual(int(session.items[0]["qty"]), 2)

    def test_reopening_in_use_tab_loads_existing_cart(self) -> None:
        opened = pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_code="1007",
            actor="pos:alice",
            operator_username="alice",
        )
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload=_payload(qty=3, tab_session_key=opened["tab_session_key"]),
            actor="pos:alice",
            operator_username="alice",
        )

        loaded = pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_code="00001007",
            actor="pos:bob",
            operator_username="bob",
        )

        self.assertEqual(loaded["tab_session_key"], opened["tab_session_key"])
        self.assertEqual(loaded["items"][0]["qty"], 3)

    def test_closing_tab_consumes_original_session_and_frees_tab(self) -> None:
        opened = pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_code="1007",
            actor="pos:alice",
            operator_username="alice",
        )
        result = pos_service.close_sale(
            channel_ref="pdv",
            payload=_payload(qty=2, tab_session_key=opened["tab_session_key"]),
            actor="pos:alice",
            operator_username="alice",
        )

        order = Order.objects.get(ref=result.order_ref)
        session = Session.objects.get(session_key=opened["tab_session_key"])
        self.assertEqual(order.session_key, opened["tab_session_key"])
        self.assertEqual(session.state, "committed")
        self.assertEqual(order.total_q, 2000)
        self.assertEqual(build_pos_tabs(channel_ref="pdv")[0].state, "empty")
        self.assertEqual(order.data["tab_code"], "00001007")

    def test_closing_tab_persists_checkout_fields(self) -> None:
        opened = pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_code="1007",
            actor="pos:alice",
            operator_username="alice",
        )
        payload = _payload(tab_session_key=opened["tab_session_key"], customer_phone="43999990000")
        payload.update({
            "customer_tax_id": "12345678901",
            "tendered_amount_q": 5000,
            "issue_fiscal_document": True,
            "receipt_mode": "email",
            "receipt_email": "ana@example.com",
        })

        result = pos_service.close_sale(
            channel_ref="pdv",
            payload=payload,
            actor="pos:alice",
            operator_username="alice",
        )

        order = Order.objects.get(ref=result.order_ref)
        self.assertEqual(order.data["customer"]["tax_id"], "12345678901")
        self.assertEqual(order.data["payment"]["method"], "cash")
        self.assertEqual(order.data["payment"]["tendered_q"], 5000)
        self.assertEqual(order.data["fiscal"], {"issue_document": True, "tax_id": "12345678901"})
        self.assertEqual(order.data["receipt"], {"mode": "email", "email": "ana@example.com"})

    def test_tab_projection_shows_empty_and_in_use_tabs(self) -> None:
        opened = pos_service.open_pos_tab(
            channel_ref="pdv",
            tab_code="1007",
            actor="pos:alice",
            operator_username="alice",
        )
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload=_payload(customer_name="Ana Mesa", customer_phone="43999990000", tab_session_key=opened["tab_session_key"]),
            actor="pos:alice",
            operator_username="alice",
        )

        tabs = build_pos_tabs(channel_ref="pdv")
        self.assertEqual([(tab.code, tab.state) for tab in tabs], [("00001007", "in_use"), ("00001008", "empty")])
        self.assertEqual([tab.code for tab in build_pos_tabs(channel_ref="pdv", query="1007")], ["00001007"])
        self.assertEqual([tab.code for tab in build_pos_tabs(channel_ref="pdv", query="ana")], ["00001007"])
        self.assertEqual([tab.code for tab in build_pos_tabs(channel_ref="pdv", query="1008")], ["00001008"])

    def test_pos_tabs_partial_renders_registered_tabs(self) -> None:
        User = get_user_model()
        staff = User.objects.create_user(username="tab_staff", password="x", is_staff=True)
        _grant_pos_perm(staff)
        self.client.force_login(staff)

        response = self.client.get("/gestor/pos/tabs/", {"tab_code": "1007"})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("1007", content)
        self.assertNotIn("1008", content)

    def test_pos_tab_open_accepts_short_display_code(self) -> None:
        User = get_user_model()
        staff = User.objects.create_user(username="tab_open_staff", password="x", is_staff=True)
        _grant_pos_perm(staff)
        self.client.force_login(staff)

        response = self.client.post("/gestor/pos/tab/open/", {"tab_code": "1007"})

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["tab_code"], "00001007")
        self.assertEqual(data["tab_display"], "1007")

    def test_pos_tab_create_registers_short_display_code(self) -> None:
        User = get_user_model()
        staff = User.objects.create_user(username="tab_create_staff", password="x", is_staff=True)
        _grant_pos_perm(staff)
        self.client.force_login(staff)

        response = self.client.post("/gestor/pos/tab/create/", {"tab_code": "1009", "label": "1009"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "posTabSaved")
        self.assertTrue(POSTab.objects.filter(code="00001009", label="1009", is_active=True).exists())

    def test_pos_page_starts_on_tab_selection_mode(self) -> None:
        from shopman.backstage.models import CashRegisterSession

        User = get_user_model()
        staff = User.objects.create_user(username="tab_page_staff", password="x", is_staff=True)
        _grant_pos_perm(staff)
        CashRegisterSession.objects.create(operator=staff, opening_amount_q=0)
        self.client.force_login(staff)

        response = self.client.get("/gestor/pos/")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("mode: 'tab_select'", content)
        self.assertIn("mode === 'checkout'", content)
        self.assertIn('id="pos-tab-grid"', content)
        self.assertIn("/gestor/pos/tab/create/", content)
        self.assertIn("openTabFromInput()", content)
        self.assertIn("CPF/CNPJ na nota", content)
        self.assertIn("addTenderedQ(5000)", content)
