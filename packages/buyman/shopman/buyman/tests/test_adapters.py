import pytest
from shopman.buyman.models import Material

pytestmark = pytest.mark.django_db


class TestBuymanCatalogBackend:
    """get_product resolves a Material (ingredient) for Craftsman's unit lookup."""

    def test_get_product_resolves_material(self):
        from shopman.buyman.adapters.catalog_backend import BuymanCatalogBackend

        Material.objects.create(sku="INS-FARINHA-T65", name="Farinha T65", unit="kg")
        info = BuymanCatalogBackend().get_product("INS-FARINHA-T65")
        assert info is not None
        assert info.unit == "kg"
        assert info.is_bundle is False
        assert info.is_sellable is False

    def test_get_product_unknown_returns_none(self):
        from shopman.buyman.adapters.catalog_backend import BuymanCatalogBackend

        assert BuymanCatalogBackend().get_product("INS-NOPE") is None


class TestMaterialSkuValidator:
    """SkuValidator over Material — needs Stockman protocols (skips standalone)."""

    def test_get_sku_info_resolves_material(self):
        pytest.importorskip("shopman.stockman")
        from shopman.buyman.adapters.sku_validator import MaterialSkuValidator

        Material.objects.create(
            sku="INS-FERMENTO-NAT", name="Levain", unit="kg", shelf_life_days=7,
        )
        info = MaterialSkuValidator().get_sku_info("INS-FERMENTO-NAT")
        assert info is not None
        assert info.unit == "kg"
        assert info.is_sellable is False
        assert info.shelflife_days == 7
        assert info.availability_policy == "planned_ok"

    def test_validate_sku_found_and_missing(self):
        pytest.importorskip("shopman.stockman")
        from shopman.buyman.adapters.sku_validator import MaterialSkuValidator

        Material.objects.create(sku="INS-SAL", name="Sal", unit="kg")
        v = MaterialSkuValidator()
        assert v.validate_sku("INS-SAL").valid is True
        assert v.validate_sku("INS-NOPE").valid is False
