"""Unit tests for shopman.shop.projections.product_detail.

Reuses the storefront web fixtures (collection, listing, product, etc.)
from ``tests/web/conftest.py``. Mirrors the CatalogProjection tests: the
PDP builder shares the same listing + availability assumptions.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.offerman.models import ListingItem, Product

from shopman.shop.projections.types import Availability
from shopman.storefront.models import Promotion
from shopman.storefront.projections import build_product_detail
from shopman.storefront.projections.product_detail import (
    AllergenInfoProjection,
    ConservationInfoProjection,
    ProductDetailProjection,
)

pytestmark = pytest.mark.django_db


DEFAULT_LOW_STOCK_THRESHOLD = Decimal("5")


def _seed_stock(sku: str, qty: Decimal) -> None:
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={
            "name": "Loja Principal",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    stock.receive(
        quantity=qty,
        sku=sku,
        position=position,
        target_date=date.today(),
        reason="pdp projection test seed",
    )


def _publish_on_listing(listing, product: Product, price_q: int | None = None) -> None:
    ListingItem.objects.get_or_create(
        listing=listing,
        product=product,
        defaults={
            "price_q": price_q if price_q is not None else product.base_price_q,
            "is_published": True,
            "is_sellable": True,
        },
    )


# ──────────────────────────────────────────────────────────────────────
# Basic shape
# ──────────────────────────────────────────────────────────────────────


class TestBuildProductDetailShape:
    def test_returns_none_for_unknown_sku(self):
        assert build_product_detail(sku="does-not-exist", channel_ref="web") is None

    def test_returns_none_for_unpublished_product(self, product_unpublished):
        assert build_product_detail(sku=product_unpublished.sku, channel_ref="web") is None

    def test_basic_shape(self, listing, collection, collection_item, product):
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert isinstance(proj, ProductDetailProjection)
        assert proj.sku == product.sku
        assert proj.slug == product.sku
        assert proj.name == "Pão Francês"
        assert proj.base_price_q == 80
        assert proj.price_display == "R$ 0,80"
        assert proj.has_promotion is False
        assert proj.original_price_display is None
        assert proj.promotion_label is None
        assert proj.max_qty == 99
        assert proj.is_bundle is False
        assert proj.components == ()

    def test_projection_is_immutable(self, listing, collection, collection_item, product):
        from dataclasses import FrozenInstanceError

        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        with pytest.raises(FrozenInstanceError):
            proj.name = "x"  # type: ignore[misc]

    def test_listing_price_wins_over_base(self, listing, product, listing_item):
        # listing_item fixture seeds price_q=90
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.base_price_q == 90
        assert proj.price_display == "R$ 0,90"

    def test_breadcrumb_category_is_first_collection(
        self, listing, collection, collection_item, product,
    ):
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.breadcrumb_category is not None
        assert proj.breadcrumb_category.ref == "paes"
        assert proj.breadcrumb_category.name == "Pães"
        assert proj.breadcrumb_category.icon


# ──────────────────────────────────────────────────────────────────────
# Availability
# ──────────────────────────────────────────────────────────────────────


class TestAvailability:
    def test_available_when_stock_seeded(self, listing, product):
        _publish_on_listing(listing, product)
        _seed_stock(product.sku, Decimal("50"))
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.availability is Availability.AVAILABLE
        assert proj.availability_label == "Disponível"
        assert proj.can_add_to_cart is True
        assert proj.available_qty == 50

    def test_low_stock_under_threshold(self, listing, product):
        _publish_on_listing(listing, product)
        _seed_stock(product.sku, DEFAULT_LOW_STOCK_THRESHOLD - Decimal("1"))
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.availability is Availability.LOW_STOCK
        assert proj.can_add_to_cart is True

    def test_unsellable_product_is_unavailable(self, listing, product_unavailable):
        _publish_on_listing(listing, product_unavailable)
        proj = build_product_detail(
            sku=product_unavailable.sku, channel_ref="web",
        )
        assert proj is not None
        assert proj.availability is Availability.UNAVAILABLE
        assert proj.can_add_to_cart is False


# ──────────────────────────────────────────────────────────────────────
# Promotions
# ──────────────────────────────────────────────────────────────────────


class TestPromotions:
    def test_active_auto_promotion_reflected(
        self, listing, collection, collection_item, product,
    ):
        _publish_on_listing(listing, product)
        now = timezone.now()
        Promotion.objects.create(
            name="Testão 20% OFF",
            type="percent",
            value=20,
            skus=[product.sku],
            is_active=True,
            valid_from=now - timedelta(hours=1),
            valid_until=now + timedelta(hours=1),
        )
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.has_promotion is True
        assert proj.original_price_display == "R$ 0,80"
        assert proj.base_price_q == 64  # 80 - 20%
        assert proj.price_display == "R$ 0,64"
        assert proj.promotion_label


# ──────────────────────────────────────────────────────────────────────
# Allergens / Conservation
# ──────────────────────────────────────────────────────────────────────


class TestCartAnnotation:
    """``qty_in_cart`` should mirror the visitor's open cart for the PDP SKU."""

    def test_qty_in_cart_zero_without_request(self, listing, product):
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.qty_in_cart == 0

    def test_qty_in_cart_reflects_cart_session(
        self, listing, collection, collection_item, cart_session, product,
    ):
        from django.test import RequestFactory

        rf = RequestFactory()
        request = rf.get(f"/produto/{product.sku}/")
        request.session = cart_session.session  # type: ignore[attr-defined]

        proj = build_product_detail(
            sku=product.sku, channel_ref="web", request=request,
        )
        assert proj is not None
        assert proj.qty_in_cart == 2


class TestAllergenAndConservation:
    def test_allergen_panel_populated_from_metadata(self, listing, product):
        product.metadata = {
            "allergens": ["glúten", "leite"],
            "dietary_info": ["vegetariano"],
            "serves": "2",
        }
        product.save()
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert isinstance(proj.allergen, AllergenInfoProjection)
        assert proj.allergen.allergens == ("glúten", "leite")
        assert proj.allergen.dietary_info == ("vegetariano",)
        assert proj.allergen.serves == "2"
        assert proj.allergen.has_any is True

    def test_purchase_measurements_from_metadata(self, listing, product):
        product.unit_weight_g = 400
        product.metadata = {
            "serves": "2 a 4 pessoas",
            "approx_dimensions": "aprox. 24 x 12 x 10 cm",
        }
        product.save()
        _publish_on_listing(listing, product)

        proj = build_product_detail(sku=product.sku, channel_ref="web")

        assert proj is not None
        assert proj.unit_weight_label == "~400g a unidade"
        assert proj.approx_dimensions_label == "aprox. 24 x 12 x 10 cm"
        assert proj.allergen is not None
        assert proj.allergen.serves == "2 a 4 pessoas"

    def test_allergen_is_none_when_metadata_empty(self, listing, product):
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.allergen is None

    def test_conservation_panel_same_day(self, listing, product):
        product.shelf_life_days = 0
        product.storage_tip = "Consumir fresco."
        product.unit_weight_g = 150
        product.save()
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert isinstance(proj.conservation, ConservationInfoProjection)
        assert proj.conservation.shelf_life_label == "Melhor consumido no mesmo dia"
        assert proj.conservation.storage_tip == "Consumir fresco."
        assert proj.unit_weight_label == "~150g a unidade"

    def test_conservation_plural_days(self, listing, product):
        product.shelf_life_days = 3
        product.save()
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.conservation is not None
        assert proj.conservation.shelf_life_label == "Conserva bem por 3 dias"

    def test_conservation_none_when_empty(self, listing, product):
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.conservation is None
