"""POSProjection — read models for the POS terminal (Fase 5).

Translates product listings, collections, and cash session state into
immutable projections for the POS page. Replaces the inline ``_load_products``
logic from ``shopman.backstage.views.pos``.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.utils import timezone
from shopman.offerman.models import Collection, Product
from shopman.orderman.models import Session
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
class POSTabProjection:
    """A visible POS tab card."""

    code: str
    display_code: str
    session_key: str
    state: str
    status_label: str
    status_class: str
    customer_name: str
    customer_phone: str
    item_count: int
    line_count: int
    total_display: str
    last_touched_display: str
    items_preview: str


@dataclass(frozen=True)
class POSProjection:
    """Top-level read model for the POS terminal page."""

    products: tuple[POSProductProjection, ...]
    collections: tuple[POSCollectionProjection, ...]
    payment_methods: tuple[POSPaymentMethodProjection, ...]
    has_open_cash_session: bool


# ── Constants ──────────────────────────────────────────────────────────

_PAYMENT_METHODS = (
    POSPaymentMethodProjection(ref="cash", label="Dinheiro"),
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


def build_pos_tabs(
    *,
    channel_ref: str = POS_CHANNEL_REF,
    query: str = "",
    limit: int = 80,
) -> tuple[POSTabProjection, ...]:
    """Build POS tab cards with empty/in-use state."""
    from shopman.backstage.models import POSTab

    query_norm = _norm(query)
    sessions = {
        str((session.data or {}).get("tab_code") or session.handle_ref or "").strip(): session
        for session in Session.objects.filter(
            channel_ref=channel_ref,
            state="open",
        ).filter(handle_type="pos_tab")
    }
    sessions.update({
        str((session.data or {}).get("tab_code") or "").strip(): session
        for session in Session.objects.filter(
            channel_ref=channel_ref,
            state="open",
            data__has_key="tab_code",
        )
    })
    sessions = {code: session for code, session in sessions.items() if code}

    codes = list(
        POSTab.objects.filter(is_active=True)
        .order_by("code")
        .values_list("code", flat=True)
    )
    for code in sessions:
        if code not in codes:
            codes.append(code)

    tabs = []
    for code in codes:
        tab = _tab_projection(code=code, session=sessions.get(code))
        if query_norm and query_norm not in _tab_haystack(tab, sessions.get(code)):
            continue
        tabs.append(tab)

    tabs.sort(key=lambda tab: (tab.state != "in_use", tab.code))
    return tuple(tabs[:limit])


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


def _tab_projection(*, code: str, session: Session | None) -> POSTabProjection:
    display_code = _display_code(code)
    if session is None:
        return POSTabProjection(
            code=code,
            display_code=display_code,
            session_key="",
            state="empty",
            status_label="Vazia",
            status_class="badge-neutral",
            customer_name="",
            customer_phone="",
            item_count=0,
            line_count=0,
            total_display="R$ 0,00",
            last_touched_display="",
            items_preview="",
        )

    data = session.data or {}
    customer = data.get("customer") or {}
    items = session.items or []
    last_touched = _parse_dt(data.get("last_touched_at"), fallback=session.opened_at)
    item_count = sum(_qty_int(item.get("qty", 1)) for item in items)
    total_q = sum(
        _qty_int(item.get("qty", 1)) * int(item.get("unit_price_q", 0))
        for item in items
    )
    discount_q = int((data.get("manual_discount") or {}).get("discount_q", 0))

    return POSTabProjection(
        code=code,
        display_code=display_code,
        session_key=session.session_key,
        state="in_use",
        status_label="Em uso",
        status_class="badge-warning",
        customer_name=str(customer.get("name") or ""),
        customer_phone=str(customer.get("phone") or ""),
        item_count=item_count,
        line_count=len(items),
        total_display=f"R$ {format_money(max(0, total_q - discount_q))}",
        last_touched_display=_format_time(last_touched),
        items_preview=_items_preview(items),
    )


def _parse_dt(value, *, fallback):
    if not value:
        return fallback
    from django.utils.dateparse import parse_datetime

    parsed = parse_datetime(str(value))
    if parsed is None:
        return fallback
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _format_time(value) -> str:
    return timezone.localtime(value).strftime("%H:%M")


def _qty_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def _items_preview(items: list[dict]) -> str:
    preview = []
    for item in items[:2]:
        qty = _qty_int(item.get("qty", 1))
        name = str(item.get("name") or item.get("sku") or "").strip()
        if not name:
            continue
        preview.append(f"{qty}x {name}")
    if len(items) > 2:
        preview.append(f"+{len(items) - 2}")
    return " · ".join(preview)


def _tab_haystack(tab: POSTabProjection, session: Session | None) -> str:
    item_parts = []
    if session is not None:
        for item in session.items or []:
            item_parts.extend([str(item.get("sku") or ""), str(item.get("name") or "")])
    return _norm(
        " ".join([
            tab.code,
            tab.display_code,
            tab.customer_name,
            tab.customer_phone,
            tab.items_preview,
            *item_parts,
        ])
    )


def _display_code(code: str) -> str:
    return str(code or "").lstrip("0") or "0"


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())
