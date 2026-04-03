"""DiscountModifier._matches — alinhamento vitrine vs carrinho (fulfillment)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from shopman.modifiers import DiscountModifier


@pytest.mark.django_db
class TestDiscountModifierMatches:
    def test_fulfillment_promo_matches_when_session_has_no_fulfillment_type(self) -> None:
        """Promo só-delivery deve casar na sessão web antes do checkout (igual vitrine)."""
        promo = MagicMock()
        promo.fulfillment_types = ["delivery"]
        promo.skus = []
        promo.collections = []
        promo.customer_segments = []

        ctx = {
            "fulfillment_type": "",
            "sku_collections": {"CIABATTA": ["paes-artesanais"]},
        }
        assert DiscountModifier._matches(promo, "CIABATTA", ctx) is True

    def test_fulfillment_promo_rejects_wrong_ft(self) -> None:
        promo = MagicMock()
        promo.fulfillment_types = ["delivery"]
        promo.skus = []
        promo.collections = []
        promo.customer_segments = []

        ctx = {
            "fulfillment_type": "pickup",
            "sku_collections": {},
        }
        assert DiscountModifier._matches(promo, "CIABATTA", ctx) is False

    def test_explicit_fulfillment_still_works(self) -> None:
        promo = MagicMock()
        promo.fulfillment_types = ["delivery", "pickup"]
        promo.skus = []
        promo.collections = []
        promo.customer_segments = []

        ctx = {
            "fulfillment_type": "delivery",
            "sku_collections": {},
        }
        assert DiscountModifier._matches(promo, "X", ctx) is True
