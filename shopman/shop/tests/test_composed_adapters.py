"""
WP-B3: composed catalog/sku adapters — Offerman (vendáveis) + Buyman (insumos).

A sellable output resolves through Offerman; an ingredient (Material) resolves
through Buyman. Proves the resolution layer that Buyman WP-B5 will activate for
availability. (CATALOG_BACKEND is wired live; SKU_VALIDATOR stays Noop until B5.)
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.buyman.models import Material
from shopman.offerman.models import Product

pytestmark = pytest.mark.django_db


@pytest.fixture
def croissant(db):
    return Product.objects.create(
        sku="CROISSANT", name="Croissant", unit="un",
        base_price_q=800, is_sellable=True,
    )


@pytest.fixture
def farinha(db):
    return Material.objects.create(
        sku="INS-FARINHA-T65", name="Farinha T65", unit="kg", shelf_life_days=180,
    )


class TestComposedCatalogBackend:
    def test_resolves_product_then_material(self, croissant, farinha):
        from shopman.shop.adapters.catalog_backend import ComposedCatalogBackend

        backend = ComposedCatalogBackend()
        prod = backend.get_product("CROISSANT")
        assert prod is not None and prod.unit == "un"

        ingredient = backend.get_product("INS-FARINHA-T65")
        assert ingredient is not None
        assert ingredient.unit == "kg"
        assert ingredient.is_bundle is False  # ingredient is never an output bundle

        assert backend.get_product("NOPE") is None

    def test_delegates_other_methods_to_offerman(self, croissant):
        from shopman.shop.adapters.catalog_backend import ComposedCatalogBackend

        backend = ComposedCatalogBackend()
        # get_price is an Offerman/sellable concern reached via __getattr__ delegation.
        price = backend.get_price("CROISSANT", qty=Decimal("1"))
        assert price.total_price_q == 800


class TestComposedSkuValidator:
    def test_get_sku_info_product_then_material(self, croissant, farinha):
        from shopman.shop.adapters.sku_validator import ComposedSkuValidator

        v = ComposedSkuValidator()
        prod = v.get_sku_info("CROISSANT")
        assert prod is not None and prod.is_sellable is True

        ing = v.get_sku_info("INS-FARINHA-T65")
        assert ing is not None
        assert ing.is_sellable is False
        assert ing.unit == "kg"
        assert ing.shelflife_days == 180

        assert v.get_sku_info("NOPE") is None

    def test_validate_skus_mixed(self, croissant, farinha):
        from shopman.shop.adapters.sku_validator import ComposedSkuValidator

        results = ComposedSkuValidator().validate_skus(["CROISSANT", "INS-FARINHA-T65", "NOPE"])
        assert results["CROISSANT"].valid is True
        assert results["INS-FARINHA-T65"].valid is True
        assert results["NOPE"].valid is False

    def test_search_merges_and_dedups(self, croissant, farinha):
        from shopman.shop.adapters.sku_validator import ComposedSkuValidator

        hits = {i.sku for i in ComposedSkuValidator().search_skus("a", limit=50)}
        # "Farinha"/"Croissant"/"CROISSANT" all contain 'a' — both sources represented.
        assert "INS-FARINHA-T65" in hits
