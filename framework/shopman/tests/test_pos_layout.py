"""Tests for WP-R11 — POS Design Tokens + Layout."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase


def _make_shop():
    from shopman.models import Shop
    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _make_channel():
    from shopman.omniman.models import Channel
    return Channel.objects.get_or_create(
        ref="balcao",
        defaults={"name": "Balcão", "pricing_policy": "fixed", "edit_policy": "open", "config": {}, "is_active": True},
    )[0]


class POSLayoutTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        _make_shop()
        _make_channel()
        User = get_user_model()
        self.staff = User.objects.create_user(username="staff", password="x", is_staff=True)
        # WP-R16: POS requires an open cash register session
        from shopman.models import CashRegisterSession
        CashRegisterSession.objects.create(operator=self.staff, opening_amount_q=0)

    def test_pos_loads_for_staff(self) -> None:
        """Staff can access POS page."""
        self.client.force_login(self.staff)
        resp = self.client.get("/gestao/pos/")
        self.assertEqual(resp.status_code, 200)

    def test_pos_redirects_non_staff(self) -> None:
        """Non-staff is redirected to admin login."""
        User = get_user_model()
        user = User.objects.create_user(username="regular", password="x", is_staff=False)
        self.client.force_login(user)
        resp = self.client.get("/gestao/pos/")
        self.assertEqual(resp.status_code, 302)

    def test_pos_context_has_payment_methods(self) -> None:
        """POS context includes payment_methods list."""
        self.client.force_login(self.staff)
        resp = self.client.get("/gestao/pos/")
        self.assertIn("payment_methods", resp.context)
        self.assertGreater(len(resp.context["payment_methods"]), 0)

    def test_pos_template_uses_tailwind_classes(self) -> None:
        """POS template uses Tailwind-based design tokens (no inline pos-tile CSS)."""
        self.client.force_login(self.staff)
        resp = self.client.get("/gestao/pos/")
        content = resp.content.decode()
        # Uses Tailwind class, not old custom CSS class
        self.assertIn("rounded-xl", content)
        # Design tokens are rendered (Tailwind output.css link present)
        self.assertIn("output.css", content)

    def test_pos_includes_shift_footer(self) -> None:
        """POS page includes the shift summary footer placeholder."""
        self.client.force_login(self.staff)
        resp = self.client.get("/gestao/pos/")
        self.assertContains(resp, "pos-shift-footer")

    def test_pos_includes_keyboard_hints(self) -> None:
        """POS page shows keyboard shortcut hints on buttons."""
        self.client.force_login(self.staff)
        resp = self.client.get("/gestao/pos/")
        self.assertContains(resp, "F8")
        self.assertContains(resp, "F5")
        self.assertContains(resp, "F6")
