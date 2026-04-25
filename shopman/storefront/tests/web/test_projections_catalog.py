"""Unit tests for shopman.shop.projections.catalog.

Reuses the storefront web fixtures (collection, listing, product, etc.)
from ``tests/web/conftest.py``. All tests that want products in the
projection MUST request the ``listing`` fixture — the builder no longer
falls back when the channel's Listing is missing.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.offerman.models import CollectionItem, ListingItem, Product

from shopman.shop.projections.types import Availability
from shopman.storefront.models import Promotion
from shopman.storefront.projections import build_catalog
from shopman.storefront.projections.catalog import (
    CatalogItemProjection,
    CatalogProjection,
)

pytestmark = pytest.mark.django_db


# Low-stock threshold lives on ChannelConfig.Stock. Tests assume the default
# (no Channel row → default cascata = 5). Seed below-threshold for LOW_STOCK.
DEFAULT_LOW_STOCK_THRESHOLD = Decimal("5")


def _seed_stock(sku: str, qty: Decimal) -> None:
    """Seed physical stock so the availability service returns a positive quant."""
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
        reason="projection test seed",
    )


def _publish_on_listing(listing, product: Product, price_q: int | None = None) -> None:
    """Ensure a product is published on the given listing (no-op if already is).

    ``price_q=None`` falls back to ``product.base_price_q``.
    """
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
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _find_item(projection: CatalogProjection, sku: str) -> CatalogItemProjection | None:
    for item in projection.items:
        if item.sku == sku:
            return item
    return None


# ──────────────────────────────────────────────────────────────────────
# Basic shape
# ──────────────────────────────────────────────────────────────────────


class TestBuildCatalogShape:
    def test_empty_catalog_without_listing(self):
        """With no Listing seeded, build_catalog returns an empty projection."""
        proj = build_catalog(channel_ref="web")
        assert isinstance(proj, CatalogProjection)
        assert proj.items == ()
        assert proj.sections == ()
        assert proj.featured == ()
        assert proj.has_items is False
        assert proj.active_category_ref is None

    def test_projection_is_immutable(self, listing, collection, collection_item, product):
        from dataclasses import FrozenInstanceError

        _publish_on_listing(listing, product)
        proj = build_catalog(channel_ref="web")
        with pytest.raises(FrozenInstanceError):
            proj.items = ()  # type: ignore[misc]

    def test_categories_exposed_with_icons(self, collection):
        proj = build_catalog(channel_ref="web")
        assert proj.categories
        pao_cat = next((c for c in proj.categories if c.ref == "paes"), None)
        assert pao_cat is not None
        assert pao_cat.name == "Pães"
        assert pao_cat.icon  # Material Symbols ligature
        assert "/menu/paes/" in pao_cat.url


# ──────────────────────────────────────────────────────────────────────
# Item projection fields
# ──────────────────────────────────────────────────────────────────────


class TestCatalogItemProjection:
    def test_item_shape_fields(self, listing, collection, collection_item, product):
        _publish_on_listing(listing, product)
        proj = build_catalog(channel_ref="web")
        item = _find_item(proj, product.sku)
        assert item is not None
        assert item.sku == product.sku
        assert item.slug == product.sku
        assert item.name == "Pão Francês"
        assert item.base_price_q == 80
        assert item.price_display == "R$ 0,80"
        assert item.has_promotion is False
        assert item.original_price_display is None
        assert item.promotion_label is None
        assert item.category == "paes"
        # Builder should return the item even when stock was never seeded.
        assert item.availability_label  # pt-BR label always present

    def test_available_when_stock_seeded(self, listing, collection, collection_item, product):
        _publish_on_listing(listing, product)
        _seed_stock(product.sku, Decimal("50"))
        proj = build_catalog(channel_ref="web")
        item = _find_item(proj, product.sku)
        assert item is not None
        assert item.availability is Availability.AVAILABLE
        assert item.availability_label == "Disponível"
        assert item.can_add_to_cart is True

    def test_low_stock_when_under_threshold(
        self, listing, collection, collection_item, product,
    ):
        _publish_on_listing(listing, product)
        _seed_stock(product.sku, DEFAULT_LOW_STOCK_THRESHOLD - Decimal("1"))
        proj = build_catalog(channel_ref="web")
        item = _find_item(proj, product.sku)
        assert item is not None
        assert item.availability is Availability.LOW_STOCK
        assert item.availability_label == "Últimas unidades"
        assert item.can_add_to_cart is True

    def test_unsellable_product_is_unavailable(self, listing, product_unavailable):
        _publish_on_listing(listing, product_unavailable)
        proj = build_catalog(channel_ref="web")
        item = _find_item(proj, product_unavailable.sku)
        assert item is not None
        assert item.availability is Availability.UNAVAILABLE
        assert item.availability_label == "Indisponível"
        assert item.can_add_to_cart is False

    def test_unpublished_product_is_hidden(self, listing, product_unpublished):
        # Even if we try to attach it to the listing, is_published=False on the
        # Product excludes it.
        _publish_on_listing(listing, product_unpublished)
        proj = build_catalog(channel_ref="web")
        skus = {item.sku for item in proj.items}
        assert product_unpublished.sku not in skus

    def test_listing_price_wins_over_base_price(
        self, listing, collection, collection_item, product, listing_item,
    ):
        # listing_item fixture is priced at 90, while product.base_price_q is 80.
        proj = build_catalog(channel_ref="web")
        item = _find_item(proj, product.sku)
        assert item is not None
        assert item.base_price_q == 90
        assert item.price_display == "R$ 0,90"


# ──────────────────────────────────────────────────────────────────────
# Sections / grouping
# ──────────────────────────────────────────────────────────────────────


class TestSections:
    def test_sections_grouped_by_collection(
        self, listing, collection, collection_item, product,
    ):
        _publish_on_listing(listing, product)
        proj = build_catalog(channel_ref="web")
        assert len(proj.sections) >= 1
        pao_section = next(
            (s for s in proj.sections if s.category and s.category.ref == "paes"),
            None,
        )
        assert pao_section is not None
        assert any(i.sku == product.sku for i in pao_section.items)

    def test_uncategorized_section(self, listing, croissant):
        # croissant exists but is not attached to any collection.
        _publish_on_listing(listing, croissant)
        proj = build_catalog(channel_ref="web")
        uncat = next((s for s in proj.sections if s.category is None), None)
        assert uncat is not None
        assert any(i.sku == croissant.sku for i in uncat.items)

    def test_collection_filter_isolates_section(
        self, listing, collection, collection_item, product, croissant,
    ):
        _publish_on_listing(listing, product)
        _publish_on_listing(listing, croissant)
        proj = build_catalog(channel_ref="web", collection_ref="paes")
        assert proj.active_category_ref == "paes"
        assert len(proj.sections) == 1
        section = proj.sections[0]
        assert section.category is not None
        assert section.category.ref == "paes"
        skus = {i.sku for i in section.items}
        assert product.sku in skus
        assert croissant.sku not in skus  # croissant is uncategorized


# ──────────────────────────────────────────────────────────────────────
# Promotions
# ──────────────────────────────────────────────────────────────────────


class TestPromotions:
    def test_active_auto_promotion_marks_item(
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

        proj = build_catalog(channel_ref="web")
        item = _find_item(proj, product.sku)
        assert item is not None
        assert item.has_promotion is True
        assert item.original_price_display == "R$ 0,80"
        assert item.base_price_q == 64  # 80 - 20%
        assert item.price_display == "R$ 0,64"
        assert item.promotion_label  # label comes from modifier metadata


# ──────────────────────────────────────────────────────────────────────
# Multiple items
# ──────────────────────────────────────────────────────────────────────


class TestCartAnnotation:
    """`qty_in_cart` should mirror the open cart when a request is passed."""

    def test_qty_in_cart_zero_without_request(
        self, listing, collection, collection_item, product,
    ):
        _publish_on_listing(listing, product)
        proj = build_catalog(channel_ref="web")
        item = _find_item(proj, product.sku)
        assert item is not None
        assert item.qty_in_cart == 0

    def test_qty_in_cart_zero_when_cart_empty(
        self, listing, collection, collection_item, product,
    ):
        from django.test import RequestFactory

        _publish_on_listing(listing, product)
        rf = RequestFactory()
        request = rf.get("/menu/")
        from django.contrib.sessions.backends.db import SessionStore
        request.session = SessionStore()  # type: ignore[attr-defined]

        proj = build_catalog(channel_ref="web", request=request)
        item = _find_item(proj, product.sku)
        assert item is not None
        assert item.qty_in_cart == 0

    def test_qty_in_cart_reflects_cart_session(
        self, listing, collection, collection_item, cart_session, product,
    ):
        """After /cart/add/ puts 2 units in the session, the projection
        should report ``qty_in_cart == 2`` for that SKU."""
        from django.test import RequestFactory

        rf = RequestFactory()
        request = rf.get("/menu/")
        request.session = cart_session.session  # type: ignore[attr-defined]

        proj = build_catalog(channel_ref="web", request=request)
        item = _find_item(proj, product.sku)
        assert item is not None
        assert item.qty_in_cart == 2

    def test_qty_in_cart_zero_for_other_skus(
        self, listing, collection, collection_item, cart_session, product, croissant,
    ):
        from django.test import RequestFactory

        _publish_on_listing(listing, croissant)

        rf = RequestFactory()
        request = rf.get("/menu/")
        request.session = cart_session.session  # type: ignore[attr-defined]

        proj = build_catalog(channel_ref="web", request=request)
        other = _find_item(proj, croissant.sku)
        assert other is not None
        assert other.qty_in_cart == 0


class TestMultipleItemsInCollection:
    def test_multiple_products_order_and_price(
        self, listing, collection, collection_item, product,
    ):
        _publish_on_listing(listing, product)
        second = Product.objects.create(
            sku="PAO-DE-QUEIJO",
            name="Pão de Queijo",
            base_price_q=350,
            is_published=True,
            is_sellable=True,
        )
        CollectionItem.objects.create(
            collection=collection, product=second, sort_order=2,
        )
        _publish_on_listing(listing, second)

        proj = build_catalog(channel_ref="web")
        pao_section = next(
            (s for s in proj.sections if s.category and s.category.ref == "paes"),
            None,
        )
        assert pao_section is not None
        skus = [i.sku for i in pao_section.items]
        assert product.sku in skus
        assert second.sku in skus
        second_item = _find_item(proj, second.sku)
        assert second_item is not None
        assert second_item.price_display == "R$ 3,50"
