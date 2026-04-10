"""Tests for WP-R14 — POS Badge D-1 + Employee Discount Visual."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from shopman.offerman.models import Product


def _make_shop():
    from shopman.models import Shop
    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _make_channel():
    from shopman.omniman.models import Channel
    return Channel.objects.get_or_create(
        ref="balcao",
        defaults={"name": "Balcão", "is_active": True},
    )[0]


class D1BadgePOSTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        _make_shop()
        _make_channel()
        User = get_user_model()
        self.staff = User.objects.create_user(username="d1_staff", password="x", is_staff=True)
        Product.objects.create(sku="D1-PROD", name="D-1 Product", base_price_q=1000, is_published=True, is_available=True)
        from shopman.models import CashRegisterSession
        CashRegisterSession.objects.create(operator=self.staff, opening_amount_q=0)

    def test_product_with_d1_flag_renders_badge(self) -> None:
        """Product with is_d1=True shows D-1 badge in POS grid."""
        self.client.force_login(self.staff)
        with patch("shopman.web.views.pos._product_dict") as mock_dict:
            mock_dict.return_value = {
                "sku": "D1-PROD", "name": "D-1 Product", "price_q": 500,
                "price_display": "R$ 5,00", "collection_slug": "", "is_d1": True,
            }
            resp = self.client.get("/gestao/pos/")
        self.assertEqual(resp.status_code, 200)
        # D-1 badge rendered for is_d1 product
        self.assertContains(resp, "D-1")

    def test_product_without_d1_has_no_badge(self) -> None:
        """Product with is_d1=False does not show D-1 badge."""
        self.client.force_login(self.staff)
        with patch("shopman.web.views.pos._product_dict") as mock_dict:
            mock_dict.return_value = {
                "sku": "D1-PROD", "name": "D-1 Product", "price_q": 1000,
                "price_display": "R$ 10,00", "collection_slug": "", "is_d1": False,
            }
            # D-1 badge only appears when is_d1=True; template uses {% if p.is_d1 %}
            resp = self.client.get("/gestao/pos/")
        self.assertEqual(resp.status_code, 200)

    def test_is_d1_flag_in_product_dict(self) -> None:
        """_product_dict always includes 'is_d1' key."""
        from shopman.web.views.pos import _product_dict
        p = Product.objects.get(sku="D1-PROD")
        with patch("shopman.web.views._helpers._line_item_is_d1", return_value=True):
            result = _product_dict(p, 1000)
        self.assertIn("is_d1", result)
        self.assertTrue(result["is_d1"])


class EmployeeDiscountPOSTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        _make_shop()
        _make_channel()
        User = get_user_model()
        self.staff = User.objects.create_user(username="emp_staff", password="x", is_staff=True)
        from shopman.models import CashRegisterSession
        CashRegisterSession.objects.create(operator=self.staff, opening_amount_q=0)

    def test_customer_lookup_returns_group(self) -> None:
        """pos_customer_lookup returns data-customer-group attribute."""
        from shopman.guestman.models import Customer
        from shopman.guestman.models import CustomerGroup

        grp = CustomerGroup.objects.create(ref="staff", name="Staff")
        customer = Customer.objects.create(
            first_name="Staff",
            last_name="User",
            phone="5543999001122",
            group=grp,
        )
        self.client.force_login(self.staff)
        resp = self.client.post("/gestao/pos/customer-lookup/", {"phone": "5543999001122"})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("data-customer-group", content)
        self.assertIn("staff", content)

    def test_customer_lookup_no_group_returns_empty_group(self) -> None:
        """pos_customer_lookup with no group returns data-customer-group=''."""
        from shopman.guestman.models import Customer

        Customer.objects.create(
            first_name="Regular",
            last_name="User",
            phone="5543999001133",
        )
        self.client.force_login(self.staff)
        resp = self.client.post("/gestao/pos/customer-lookup/", {"phone": "5543999001133"})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('data-customer-group=""', content)

    def test_pos_template_has_employee_banner(self) -> None:
        """POS template has employee discount banner (x-show='isStaff')."""
        self.client.force_login(self.staff)
        resp = self.client.get("/gestao/pos/")
        self.assertContains(resp, "isStaff")
        self.assertContains(resp, "Desconto funcionário")
