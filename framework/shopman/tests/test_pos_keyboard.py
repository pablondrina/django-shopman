"""Tests for WP-R13 — POS Keyboard Shortcuts.

The shortcuts are implemented in Alpine.js (client-side) and therefore
cannot be exercised in Django unit tests. This module verifies that
the template renders all the required shortcut hooks so the browser
can wire them up correctly.

Manual test checklist:
  F1–F4 : filtra coleção (índice 0–3)
  F5    : limpa carrinho
  F6    : abre modal de desconto (só se cart não vazio)
  F8    : fecha venda (equivale a clicar "Fechar Venda")
  /     : foca campo de busca
  Esc   : fecha modal aberto / limpa carrinho
  Enter : fecha venda quando carrinho não está vazio (fora de input)
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase


def _make_shop():
    from shopman.models import Shop
    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _make_channel():
    from shopman.models import Channel
    return Channel.objects.get_or_create(
        ref="balcao",
        defaults={"name": "Balcão", "is_active": True},
    )[0]


class POSKeyboardShortcutTemplateTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        _make_shop()
        _make_channel()
        User = get_user_model()
        self.staff = User.objects.create_user(username="kb_staff", password="x", is_staff=True)
        self.client.force_login(self.staff)
        # WP-R16: POS requires an open cash register session
        from shopman.models import CashRegisterSession
        CashRegisterSession.objects.create(operator=self.staff, opening_amount_q=0)

    def _content(self):
        return self.client.get("/gestao/pos/").content.decode()

    def test_global_keydown_handler_present(self) -> None:
        """Template binds @keydown.window to handleKey."""
        self.assertIn("handleKey", self._content())

    def test_f8_shortcut_hint_on_close_button(self) -> None:
        """Close sale button shows F8 shortcut hint."""
        content = self._content()
        self.assertIn("F8", content)
        self.assertIn("pos-close-btn", content)

    def test_f5_shortcut_hint_on_clear_button(self) -> None:
        """Clear button shows F5 hint."""
        self.assertIn("F5", self._content())

    def test_f6_shortcut_hint_on_discount_button(self) -> None:
        """Discount button shows F6 hint."""
        self.assertIn("F6", self._content())

    def test_search_focus_hint_present(self) -> None:
        """Search input includes / shortcut placeholder hint."""
        self.assertIn("(/)", self._content())

    def test_escape_handler_in_alpine_data(self) -> None:
        """Alpine data contains Escape handling logic."""
        content = self._content()
        self.assertIn("Escape", content)
        self.assertIn("showDiscountModal", content)

    def test_f1_to_f4_collection_shortcuts(self) -> None:
        """F1–F4 collection switching is handled."""
        content = self._content()
        self.assertIn("F1", content)
        self.assertIn("F4", content)
