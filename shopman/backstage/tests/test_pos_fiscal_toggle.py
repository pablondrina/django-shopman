"""Toggle 'Nota fiscal' no PDV: flag da loja (Admin) × adapter fiscal configurado.

O toggle só aparece quando a loja OFERECE NFC-e (Shop.defaults['pos']['fiscal_toggle'])
E o adapter fiscal está configurado. Decisão por-estabelecimento, não por-operador.
"""

from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase, override_settings

from shopman.backstage.projections.pos import (
    _pos_fiscal_toggle_enabled,
    _supports_fiscal_document,
)
from shopman.shop.models import Shop
from shopman.shop.models.shop import SHOP_CACHE_KEY

_ADAPTER = "shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend"


class PosFiscalToggleTests(TestCase):
    def _shop(self, defaults):
        cache.delete(SHOP_CACHE_KEY)
        Shop.objects.all().delete()
        Shop.objects.create(name="Test", defaults=defaults)
        cache.delete(SHOP_CACHE_KEY)

    def test_flag_reads_from_shop_defaults(self):
        self._shop({"pos": {"fiscal_toggle": True}})
        self.assertTrue(_pos_fiscal_toggle_enabled())
        self._shop({"pos": {"fiscal_toggle": False}})
        self.assertFalse(_pos_fiscal_toggle_enabled())

    def test_flag_defaults_false_when_absent(self):
        self._shop({})
        self.assertFalse(_pos_fiscal_toggle_enabled())

    @override_settings(SHOPMAN_FISCAL_ADAPTER=_ADAPTER)
    def test_supports_true_with_adapter_and_flag(self):
        self._shop({"pos": {"fiscal_toggle": True}})
        self.assertTrue(_supports_fiscal_document())

    @override_settings(SHOPMAN_FISCAL_ADAPTER=None)
    def test_supports_false_without_adapter(self):
        self._shop({"pos": {"fiscal_toggle": True}})
        self.assertFalse(_supports_fiscal_document())

    @override_settings(SHOPMAN_FISCAL_ADAPTER=_ADAPTER)
    def test_supports_false_with_adapter_but_flag_off(self):
        self._shop({"pos": {"fiscal_toggle": False}})
        self.assertFalse(_supports_fiscal_document())
