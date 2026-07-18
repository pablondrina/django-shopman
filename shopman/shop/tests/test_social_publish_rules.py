"""Arc D: per-platform social publish rules + handler guards."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from shopman.offerman.protocols.projection import ProjectedItem

from shopman.shop.services import social_publish_rules as rules

pytestmark = pytest.mark.django_db


def _shop(social_publish=None):
    from shopman.shop.models import Shop

    defaults = {"social_publish": social_publish} if social_publish else {}
    return Shop.objects.create(name="Loja", defaults=defaults)


def _item(image_url=None, sellable=True):
    return ProjectedItem(
        sku="PAO", name="Pão", description="", unit="un",
        price_q=500, is_published=True, is_sellable=sellable, image_url=image_url,
    )


class TestRulesFor:
    def test_defaults_when_unconfigured(self):
        _shop()
        assert rules.rules_for("meta") == {
            "publish_on_create": True, "require_stock": False, "require_image": False,
        }

    def test_merge_override(self):
        _shop({"meta": {"publish_on_create": False, "require_image": True}})
        r = rules.rules_for("meta")
        assert r["publish_on_create"] is False
        assert r["require_image"] is True
        assert r["require_stock"] is False  # untouched → default

    def test_platform_isolation(self):
        _shop({"meta": {"require_image": True}})
        assert rules.rules_for("google")["require_image"] is False

    def test_should_auto_publish_new(self):
        _shop({"meta": {"publish_on_create": False}})
        assert rules.should_auto_publish_new("meta") is False
        assert rules.should_auto_publish_new("google") is True


class TestProjectionGate:
    def test_no_rules_no_gate(self):
        _shop()
        assert rules.projection_gate(_item(), "meta") is None

    def test_require_image_blocks_imageless(self):
        _shop({"meta": {"require_image": True}})
        assert rules.projection_gate(_item(image_url=None), "meta") == ("skipped", "regra: exige imagem")

    def test_require_image_passes_with_image(self):
        _shop({"meta": {"require_image": True}})
        assert rules.projection_gate(_item(image_url="https://x/y.jpg"), "meta") is None

    def test_require_stock_blocks_without_stock(self):
        _shop({"meta": {"require_stock": True}})
        with patch(
            "shopman.shop.projections.catalog_context.availability_for_sku",
            return_value={"total_promisable": 0, "availability_policy": "stock_only"},
        ):
            assert rules.projection_gate(_item(image_url="x"), "meta") == ("pending", "regra: exige estoque")

    def test_require_stock_passes_with_stock(self):
        _shop({"meta": {"require_stock": True}})
        with patch(
            "shopman.shop.projections.catalog_context.availability_for_sku",
            return_value={"total_promisable": 5, "availability_policy": "stock_only"},
        ):
            assert rules.projection_gate(_item(image_url="x"), "meta") is None

    def test_require_stock_lenient_on_unknown(self):
        _shop({"meta": {"require_stock": True}})
        with patch(
            "shopman.shop.projections.catalog_context.availability_for_sku",
            return_value=None,
        ):
            assert rules.projection_gate(_item(image_url="x"), "meta") is None


class TestHandlerGuards:
    def test_publish_on_create_false_skips_and_records(self):
        from shopman.orderman.models import Directive

        from shopman.shop.handlers.catalog_projection import on_product_created
        from shopman.shop.models import CatalogSyncState

        _shop({"ifood": {"publish_on_create": False}})
        with patch(
            "shopman.shop.handlers.catalog_projection._projection_listing_refs",
            return_value=["ifood"],
        ):
            on_product_created(sender=None, instance=None, sku="PAO")

        assert CatalogSyncState.objects.get(sku="PAO", platform="ifood").status == "skipped"
        assert not Directive.objects.filter(payload__sku="PAO").exists()

    def test_publish_on_create_true_enqueues(self):
        from shopman.orderman.models import Directive

        from shopman.shop.directives import CATALOG_PROJECT_SKU
        from shopman.shop.handlers.catalog_projection import on_product_created

        _shop({"ifood": {"publish_on_create": True}})
        with patch(
            "shopman.shop.handlers.catalog_projection._projection_listing_refs",
            return_value=["ifood"],
        ):
            on_product_created(sender=None, instance=None, sku="PAO")

        assert Directive.objects.filter(topic=CATALOG_PROJECT_SKU, payload__sku="PAO").exists()

    def test_require_image_gate_in_handle_skips_push(self):
        from shopman.orderman.models import Directive

        from shopman.shop.directives import CATALOG_PROJECT_SKU
        from shopman.shop.handlers.catalog_projection import CatalogProjectHandler
        from shopman.shop.models import CatalogSyncState, Channel

        _shop({"ifood": {"require_image": True}})
        Channel.objects.create(ref="ifood", name="iFood", is_active=True)
        directive = Directive.objects.create(
            topic=CATALOG_PROJECT_SKU, payload={"sku": "PAO", "listing_ref": "ifood"},
        )
        backend = MagicMock()
        handler = CatalogProjectHandler(backend=backend)
        with patch(
            "shopman.shop.handlers.catalog_projection._get_projected_item",
            return_value=_item(image_url=None),
        ):
            handler.handle(message=directive, ctx={})

        backend.project.assert_not_called()
        assert CatalogSyncState.objects.get(sku="PAO", platform="ifood").status == "skipped"
