"""POSProjection — read models for the POS terminal (Fase 5).

Translates product listings, collections, and cash session state into
immutable projections for the POS page. Replaces the inline ``_load_products``
logic from ``shopman.backstage.views.pos``.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from shopman.offerman.models import Collection, Product
from shopman.utils.monetary import format_money

from shopman.backstage.constants import POS_CHANNEL_REF

logger = logging.getLogger(__name__)


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class POSProductProjection:
    """A single product tile in the POS grid."""

    sku: str
    name: str
    price_q: int
    price_display: str
    collection_ref: str
    is_d1: bool


@dataclass(frozen=True)
class POSCollectionProjection:
    """A collection tab in the POS filter bar."""

    ref: str
    name: str


@dataclass(frozen=True)
class POSPaymentMethodProjection:
    """A payment method option in the POS."""

    ref: str
    label: str


@dataclass(frozen=True)
class POSShiftSummaryProjection:
    """Today's shift totals for the POS."""

    count: int
    total_display: str
    last_ref: str
    last_total_display: str


@dataclass(frozen=True)
class POSProjection:
    """Top-level read model for the POS terminal page."""

    products: tuple[POSProductProjection, ...]
    collections: tuple[POSCollectionProjection, ...]
    payment_methods: tuple[POSPaymentMethodProjection, ...]
    has_open_cash_session: bool


# ── Constants ──────────────────────────────────────────────────────────

_PAYMENT_METHODS = (
    POSPaymentMethodProjection(ref="counter", label="Dinheiro"),
    POSPaymentMethodProjection(ref="pix", label="PIX"),
    POSPaymentMethodProjection(ref="card", label="Cartão"),
)


# ── Builders ───────────────────────────────────────────────────────────


def build_pos() -> POSProjection:
    """Build the POS terminal projection."""
    products = _load_products()

    collections = tuple(
        POSCollectionProjection(ref=c["ref"], name=c["name"])
        for c in Collection.objects.filter(is_active=True, parent__isnull=True)
        .order_by("sort_order", "name")
        .values("ref", "name")
    )

    return POSProjection(
        products=tuple(products),
        collections=collections,
        payment_methods=_PAYMENT_METHODS,
        has_open_cash_session=True,  # caller checks this before building
    )


def build_pos_shift_summary(*, channel_ref: str = POS_CHANNEL_REF) -> POSShiftSummaryProjection:
    """Build today's shift summary for the POS."""
    from django.db.models import Sum
    from django.utils import timezone
    from shopman.orderman.models import Order

    today = timezone.localdate()
    qs = Order.objects.filter(
        channel_ref=channel_ref,
        created_at__date=today,
    ).exclude(status="cancelled")

    shift_count = qs.count()
    shift_total_q = qs.aggregate(t=Sum("total_q"))["t"] or 0

    last_order = qs.order_by("-created_at").first()

    return POSShiftSummaryProjection(
        count=shift_count,
        total_display=format_money(shift_total_q),
        last_ref=last_order.ref if last_order else "",
        last_total_display=format_money(last_order.total_q) if last_order else "",
    )


# ── Internals ──────────────────────────────────────────────────────────


def _load_products() -> list[POSProductProjection]:
    """Load products with prices and D-1 flags for the POS grid."""
    products: list[POSProductProjection] = []

    try:
        from shopman.offerman.models import ListingItem

        items = (
            ListingItem.objects.filter(
                listing__ref=POS_CHANNEL_REF,
                listing__is_active=True,
                is_published=True,
                is_sellable=True,
            )
            .select_related("product")
            .order_by("product__name")
        )
        for li in items:
            p = li.product
            price_q = li.price_q if li.price_q else p.base_price_q
            products.append(_product_projection(p, price_q))
    except Exception:
        logger.exception("pos_load_products_listing_failed")

    if not products:
        for p in Product.objects.filter(is_published=True, is_sellable=True).order_by("name"):
            products.append(_product_projection(p, p.base_price_q))

    return products


def _product_projection(product: Product, price_q: int) -> POSProductProjection:
    ci = (
        product.collection_items
        .filter(is_primary=True)
        .select_related("collection")
        .first()
    )

    try:
        from shopman.backstage.projections._helpers import _line_item_is_d1
        is_d1 = _line_item_is_d1(product, listing_ref=POS_CHANNEL_REF)
    except Exception:
        logger.exception("pos_d1_check_failed sku=%s", product.sku)
        is_d1 = False

    return POSProductProjection(
        sku=product.sku,
        name=product.name,
        price_q=price_q,
        price_display=f"R$ {format_money(price_q)}",
        collection_ref=ci.collection.ref if ci else "",
        is_d1=is_d1,
    )
