"""Checkout read-side projections — repricing + stock shortfalls (data).

Drained out of ``checkout_context`` (which embedded ``format_money`` and copy).
Both builders take the cart DATA projection's lines and return semantic data —
cents, refs, quantities — with no copy or formatting. The storefront
presentation renders the "preço mudou / Deseja continuar?" and stock messages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from . import checkout_context

logger = logging.getLogger(__name__)

_REPRICING_TOLERANCE_DEFAULT = 0.05  # 5% — surface a repricing prompt past this drift


@dataclass(frozen=True)
class RepricingChangeProjection:
    """A cart line whose catalog price drifted past the tolerance — cents only."""

    sku: str
    name: str
    cart_price_q: int
    current_price_q: int


@dataclass(frozen=True)
class StockShortfallProjection:
    """A cart line whose requested qty exceeds what can be promised now."""

    line_id: str
    sku: str
    name: str
    requested_qty: int
    available_qty: int


def _repricing_tolerance() -> float:
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        raw = (shop.defaults or {}).get("repricing_tolerance") if shop else None
        return float(raw) if raw else _REPRICING_TOLERANCE_DEFAULT
    except Exception:
        logger.debug("repricing_tolerance degraded; using default", exc_info=True)
        return _REPRICING_TOLERANCE_DEFAULT


def repricing_changes(cart_lines) -> tuple[RepricingChangeProjection, ...]:
    """Lines whose cart price drifted from the current catalog price past the
    configured tolerance. ``cart_lines`` is the cart projection's ``lines``.
    """
    skus = [line.sku for line in cart_lines if line.sku]
    if not skus:
        return ()

    from shopman.offerman.models import Product

    products = {
        p.sku: p
        for p in Product.objects.filter(sku__in=skus).only("sku", "name", "base_price_q")
    }
    tolerance = _repricing_tolerance()
    changes = []
    for line in cart_lines:
        product = products.get(line.sku)
        if product is None:
            continue
        cart_price = int(line.unit_price_q)
        current_price = int(product.base_price_q)
        if cart_price <= 0 or current_price <= 0:
            continue
        if abs(current_price - cart_price) / current_price > tolerance:
            changes.append(
                RepricingChangeProjection(
                    sku=line.sku,
                    name=product.name or line.sku,
                    cart_price_q=cart_price,
                    current_price_q=current_price,
                )
            )
    return tuple(changes)


def cart_stock_shortfalls(
    *,
    session_key: str,
    cart_lines,
    channel_ref: str,
    target_date: date | None = None,
) -> tuple[tuple[StockShortfallProjection, ...], bool]:
    """Lines whose requested qty exceeds the own-hold-aware promisable qty.

    Returns ``(shortfalls, service_unavailable)``; ``service_unavailable`` is
    True when the stock service answered for nothing (every lookup skipped).
    """
    if not cart_lines:
        return (), False

    session_held = checkout_context.session_held_qty(session_key, target_date=target_date)
    shortfalls = []
    checked = 0
    skipped = 0
    for line in cart_lines:
        avail = checkout_context._availability_for_sku(line.sku, channel_ref=channel_ref, target_date=target_date)
        if avail is None:
            skipped += 1
            continue
        checked += 1
        if avail.get("availability_policy") == "demand_ok" and not avail.get("is_paused", False):
            continue
        available_qty = int(avail.get("total_promisable", 0)) + session_held.get(line.sku, 0)
        if line.qty > available_qty:
            shortfalls.append(
                StockShortfallProjection(
                    line_id=line.line_id,
                    sku=line.sku,
                    name=line.name or line.sku,
                    requested_qty=line.qty,
                    available_qty=available_qty,
                )
            )

    service_unavailable = skipped > 0 and checked == 0
    if service_unavailable:
        logger.warning("checkout.stock_check_unavailable: %d line(s) skipped", skipped)
    return tuple(shortfalls), service_unavailable


def availability_dates(max_preorder_days: int) -> tuple[tuple[str, ...], tuple[int, ...]]:
    """Próximas datas operacionais (ISO) + dias da semana fechados.

    Fonte: ``business_calendar`` (horário semanal + feriados/férias coletivas) —
    o mesmo serviço read-only que ``shop_status``/``order_tracking`` já consomem
    pelo read-side. Exposto aqui para a presentation ler sem importar o serviço
    (regra R-A). Degrada para vazio se algo falhar — a UI cai no fallback de datas.
    """
    try:
        from shopman.shop.services import business_calendar

        # Duas é o bastante: a UI mostra "Hoje" (se aberto) + a próxima fornada.
        dates = business_calendar.available_dates(max_count=2, horizon_days=max_preorder_days)
        return (
            tuple(d.isoformat() for d in dates),
            tuple(business_calendar.closed_weekdays()),
        )
    except Exception:
        logger.debug("checkout_projection_availability_dates_failed", exc_info=True)
        return (), ()


__all__ = [
    "RepricingChangeProjection",
    "StockShortfallProjection",
    "availability_dates",
    "cart_stock_shortfalls",
    "repricing_changes",
]
