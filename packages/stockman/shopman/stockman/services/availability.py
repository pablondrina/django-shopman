"""
Disponibilidade por SKU/canal — lógica compartilhada entre API REST e orquestrador.

Não importar de ``shopman.stockman.api.views``; views importam daqui.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from shopman.stockman.models import Hold, Quant
from shopman.stockman.models.enums import HoldStatus


def sku_exists(sku: str) -> bool:
    """Check if SKU exists via offering.Product."""
    from shopman.offerman.models import Product

    return Product.objects.filter(sku=sku).exists()


def _product_is_orderable(sku: str) -> bool:
    """Check if product is published AND available for sale."""
    from shopman.offerman.models import Product

    return Product.objects.filter(
        sku=sku, is_published=True, is_available=True,
    ).exists()


def availability_for_sku(
    sku: str,
    position=None,
    safety_margin: int = 0,
    *,
    allowed_positions: list[str] | None = None,
) -> dict:
    """
    Build availability dict for a SKU with breakdown.

    Breakdown categories:
    - ready: Position.is_saleable=True, batch != "D-1"
    - in_production: Position.is_saleable=False (e.g. producao)
    - d1: batch == "D-1" (yesterday's leftovers)

    total_available = ready - held - safety_margin (only saleable stock).
    is_planned = True if any quant has a future target_date.

    If product is paused (is_available=False or is_published=False),
    returns zeros for orderable/available — stock may exist but is not for sale.

    ``allowed_positions``: when not None, only quants at those position refs are
    considered (e.g. remote channels exclude ``ontem`` so D-1 leftovers there are
    invisible online). Ignored when ``position`` is set (single-position query).
    """
    from shopman.stockman.models import Batch

    zero = Decimal("0")
    zero_breakdown = {"ready": zero, "in_production": zero, "d1": zero}
    orderable = _product_is_orderable(sku)

    # If product is paused, return zeros (stock exists but not for sale)
    if not orderable:
        return {
            "sku": sku,
            "total_available": zero,
            "total_orderable": zero,
            "total_reserved": zero,
            "breakdown": zero_breakdown,
            "is_planned": False,
            "is_paused": True,
            "positions": [],
        }

    today = date.today()

    # Expired batch refs for this SKU (loose coupling via string)
    expired_refs = set(
        Batch.objects.filter(sku=sku, expiry_date__lt=today)
        .values_list("ref", flat=True)
    )

    # Check if there are planned (future) quants → is_planned flag
    is_planned = Quant.objects.filter(
        sku=sku, target_date__gt=today, _quantity__gt=0,
    ).exists()

    quants = (
        Quant.objects.filter(sku=sku)
        .filter(Q(target_date__isnull=True) | Q(target_date__lte=today))
        .filter(_quantity__gt=0)
        .select_related("position")
    )

    if position:
        quants = quants.filter(position=position)
    elif allowed_positions is not None:
        quants = quants.filter(position__ref__in=allowed_positions)

    ready = Decimal("0")
    in_production = Decimal("0")
    d1 = Decimal("0")
    held_ready = Decimal("0")
    held_production = Decimal("0")
    held_d1 = Decimal("0")
    positions_data = []

    for quant in quants:
        if quant.batch and quant.batch in expired_refs:
            continue

        qty = quant._quantity
        held = quant.held

        # Classify into breakdown buckets
        if quant.batch == "D-1":
            d1 += qty
            held_d1 += held
        elif quant.position and quant.position.kind == "process":
            # PROCESS position = production stage (forno, bancada, etc.)
            in_production += qty
            held_production += held
        elif quant.position and quant.position.is_saleable:
            ready += qty
            held_ready += held

        if quant.position:
            positions_data.append({
                "position_ref": quant.position.ref,
                "position_name": quant.position.name,
                "available": qty - held,
                "reserved": held,
                "batch": quant.batch or None,
            })

    total_held = held_ready + held_production + held_d1

    # total_available = ready stock minus holds minus safety margin
    total_available = max(ready - held_ready - safety_margin, Decimal("0"))

    # total_orderable = everything that can be reserved (ready + production, net of holds)
    total_orderable = max(
        ready + in_production - held_ready - held_production - safety_margin,
        Decimal("0"),
    )

    return {
        "sku": sku,
        "total_available": total_available,
        "total_orderable": total_orderable,
        "total_reserved": total_held,
        "breakdown": {
            "ready": ready - held_ready,
            "in_production": in_production - held_production,
            "d1": d1 - held_d1,
        },
        "is_planned": is_planned,
        "is_paused": False,
        "positions": positions_data,
    }


def availability_for_skus(
    skus: list[str],
    safety_margin: int = 0,
    *,
    allowed_positions: list[str] | None = None,
) -> dict[str, dict]:
    """
    Batch version of availability_for_sku() — same logic, few queries regardless of N.

    Returns {sku: availability_dict} for all requested SKUs. Functionally identical
    to calling availability_for_sku(sku, safety_margin=..., allowed_positions=...)
    for each SKU, but uses bulk DB queries to avoid N+1.
    """
    from shopman.offerman.models import Product
    from shopman.stockman.models import Batch

    if not skus:
        return {}

    zero = Decimal("0")
    zero_breakdown = {"ready": zero, "in_production": zero, "d1": zero}

    today = date.today()

    # ── Query 1: orderable SKUs (published + available) ──────────────────────
    orderable_skus: set[str] = set(
        Product.objects.filter(
            sku__in=skus, is_published=True, is_available=True,
        ).values_list("sku", flat=True)
    )

    # ── Query 2: expired batch refs grouped by SKU ────────────────────────────
    # Maps sku → set of expired batch refs
    expired_refs_by_sku: dict[str, set[str]] = {}
    for row in Batch.objects.filter(sku__in=skus, expiry_date__lt=today).values("sku", "ref"):
        expired_refs_by_sku.setdefault(row["sku"], set()).add(row["ref"])

    # ── Query 3: planned SKUs (has future quants) ─────────────────────────────
    planned_skus: set[str] = set(
        Quant.objects.filter(
            sku__in=skus, target_date__gt=today, _quantity__gt=0,
        ).values_list("sku", flat=True).distinct()
    )

    # ── Query 4: physical quants (current/past), select_related position ──────
    quant_qs = (
        Quant.objects.filter(sku__in=skus)
        .filter(Q(target_date__isnull=True) | Q(target_date__lte=today))
        .filter(_quantity__gt=0)
        .select_related("position")
    )
    if allowed_positions is not None:
        quant_qs = quant_qs.filter(position__ref__in=allowed_positions)

    # Fetch all matching quants
    all_quants = list(quant_qs)

    # ── Batch held amounts: one query across all quant PKs ────────────────────
    quant_ids = [q.pk for q in all_quants]
    now = timezone.now()
    held_by_quant: dict[int, Decimal] = {}
    if quant_ids:
        rows = (
            Hold.objects.filter(
                quant_id__in=quant_ids,
                status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))
            .values("quant_id")
            .annotate(total=Sum("quantity"))
        )
        for row in rows:
            held_by_quant[row["quant_id"]] = row["total"] or zero

    # ── Group quants by SKU and compute breakdown ─────────────────────────────
    quants_by_sku: dict[str, list] = {}
    for q in all_quants:
        quants_by_sku.setdefault(q.sku, []).append(q)

    result: dict[str, dict] = {}

    for sku in skus:
        # Product paused: return zeros (stock may exist but not for sale)
        if sku not in orderable_skus:
            result[sku] = {
                "sku": sku,
                "total_available": zero,
                "total_orderable": zero,
                "total_reserved": zero,
                "breakdown": dict(zero_breakdown),
                "is_planned": False,
                "is_paused": True,
                "positions": [],
            }
            continue

        expired_refs = expired_refs_by_sku.get(sku, set())
        is_planned = sku in planned_skus

        ready = Decimal("0")
        in_production = Decimal("0")
        d1 = Decimal("0")
        held_ready = Decimal("0")
        held_production = Decimal("0")
        held_d1 = Decimal("0")
        positions_data = []

        for quant in quants_by_sku.get(sku, []):
            if quant.batch and quant.batch in expired_refs:
                continue

            qty = quant._quantity
            held = held_by_quant.get(quant.pk, zero)

            # Classify into breakdown buckets (same logic as availability_for_sku)
            if quant.batch == "D-1":
                d1 += qty
                held_d1 += held
            elif quant.position and quant.position.kind == "process":
                in_production += qty
                held_production += held
            elif quant.position and quant.position.is_saleable:
                ready += qty
                held_ready += held

            if quant.position:
                positions_data.append({
                    "position_ref": quant.position.ref,
                    "position_name": quant.position.name,
                    "available": qty - held,
                    "reserved": held,
                    "batch": quant.batch or None,
                })

        total_held = held_ready + held_production + held_d1

        total_available = max(ready - held_ready - safety_margin, zero)
        total_orderable = max(
            ready + in_production - held_ready - held_production - safety_margin,
            zero,
        )

        result[sku] = {
            "sku": sku,
            "total_available": total_available,
            "total_orderable": total_orderable,
            "total_reserved": total_held,
            "breakdown": {
                "ready": ready - held_ready,
                "in_production": in_production - held_production,
                "d1": d1 - held_d1,
            },
            "is_planned": is_planned,
            "is_paused": False,
            "positions": positions_data,
        }

    return result


def _get_safety_margin(channel_ref: str | None) -> int:
    """Safety margin for channel. Defaults to 0; override via framework ChannelConfig.stock."""
    return 0


def _get_allowed_positions(channel_ref: str | None) -> list[str] | None:
    """Allowed stock positions for channel. None = all positions; override via framework ChannelConfig.stock."""
    return None


def availability_scope_for_channel(channel_ref: str | None) -> dict[str, int | list[str] | None]:
    """Único ponto para margem + posições ao calcular disponibilidade por canal.

    O catálogo (o que o canal “oferece”) vem da Listagem vinculada ao canal; estes
    parâmetros só restringem **de quais posições físicas** o estoque conta para esse
    canal (ex.: remoto sem ``ontem`` para D-1 só no balcão).
    """
    return {
        "safety_margin": _get_safety_margin(channel_ref),
        "allowed_positions": _get_allowed_positions(channel_ref),
    }
