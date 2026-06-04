"""Tests for WP-R13 — POS Keyboard Shortcuts.

The shortcuts are implemented in Alpine.js (client-side) and therefore
cannot be exercised in Django unit tests. This module verifies that
the template renders all the required shortcut hooks so the browser
can wire them up correctly.

Manual test checklist:
  F2    : foca leitura de comanda
  F3    : foca busca de produto
  F4    : foca carrinho
  F5    : abre confirmação para limpar comanda
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
    from shopman.shop.models import Shop
    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _make_channel():
    from shopman.shop.models import Channel
    return Channel.objects.get_or_create(
        ref="pdv",
        defaults={"name": "Balcão", "is_active": True},
    )[0]



def _grant_pos_perm(user):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    from shopman.backstage.models import CashShift
    ct = ContentType.objects.get_for_model(CashShift)
    perm = Permission.objects.get(content_type=ct, codename="operate_pos")
    user.user_permissions.add(perm)


class POSKeyboardShortcutTemplateTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        _make_shop()
        _make_channel()
        User = get_user_model()
        self.staff = User.objects.create_user(username="kb_staff", password="x", is_staff=True)
        _grant_pos_perm(self.staff)
        self.client.force_login(self.staff)
        # WP-R16: POS requires an open cash register session
        from shopman.backstage.models import CashShift
        CashShift.objects.create(operator=self.staff, opening_amount_q=0)
        from shopman.offerman.models import Product
        Product.objects.create(sku="KB-PROD", name="Produto Teclado", base_price_q=1000, is_published=True, is_sellable=True)

    def _content(self):
        return self.client.get("/gestor/pos/").content.decode()

    def test_global_keydown_handler_present(self) -> None:
        """Template binds @keydown.window to handleKey."""
        self.assertIn("handleKey", self._content())

    def test_f8_shortcut_hint_on_close_button(self) -> None:
        """Close sale button shows F8 shortcut hint."""
        content = self._content()
        self.assertIn("F8", content)
        self.assertIn("pos-close-btn", content)

    def test_f5_shortcut_hint_on_clear_button(self) -> None:
        """Clear action shows F5 hint but requires explicit confirmation."""
        content = self._content()
        self.assertIn("F5", content)
        self.assertIn("Limpar comanda?", content)
        self.assertIn("showClearSaleModal", content)
        self.assertIn("requestClearActiveSale()", content)
        self.assertIn("confirmClearActiveSale", content)

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

    def test_focus_shortcuts_are_present(self) -> None:
        """F2/F3/F4 focus shortcuts are handled."""
        content = self._content()
        self.assertIn("F2", content)
        self.assertIn("F3", content)
        self.assertIn("F4", content)
        self.assertIn("Pausar comanda", content)
        self.assertIn("Alt+1..9", content)
        self.assertIn("addFirstMatchedProductFromSearch", content)

    def test_roving_keyboard_hooks_are_present(self) -> None:
        """Product/tab/payment grids expose roving keyboard handlers."""
        content = self._content()
        self.assertIn("handleProductGridKey", content)
        self.assertIn("handleTabGridKey", content)
        self.assertIn("handlePaymentKey", content)
        self.assertIn("data-product-tile", content)
        self.assertIn("data-payment-option", content)
        self.assertIn("e.stopPropagation();", content)
        self.assertIn("lowStockLabel", content)
        self.assertIn("syncCartBeforeCheckout", content)
        self.assertIn("Conferindo preços, promoções e regras", content)
        self.assertIn("isPricingDirty", content)
        self.assertIn("Checkout conferido pelo backend", content)
        self.assertIn("Setas", content)

    def test_operational_journal_and_health_hooks_are_present(self) -> None:
        content = self._content()
        self.assertIn("showHealthPanel", content)
        self.assertIn("offlineJournal", content)
        self.assertIn("shopman.pos.offlineQueue.v2", content)
        self.assertIn("pos.sale-intent.v1", content)
