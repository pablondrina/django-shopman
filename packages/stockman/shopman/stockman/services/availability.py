"""
Disponibilidade por SKU/canal — lógica compartilhada entre API REST e orquestrador.

Não importar de ``shopman.stockman.api.views``; views importam daqui.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone
from shopman.stockman.adapters.sku_validation import get_sku_validator
from shopman.stockman.models import Hold, Quant
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.protocols.sku import PromiseDecision
from shopman.stockman.services.scope import quants_eligible_for

STARTED_BATCH = "started"


def _policy_promisable_qty(
    availability_policy: str,
    *,
    available: Decimal,
    expected: Decimal,
    planned: Decimal,
) -> Decimal:
    """Return the effective promise scope allowed by the offer policy."""
    if availability_policy == "stock_only":
        return available
    return expected + planned


def sku_exists(sku: str) -> bool:
    """Check if a SKU exists via the configured validator contract."""
    validator = get_sku_validator()
    result = validator.validate_sku(sku)
    return result.valid


def _sku_is_sellable(sku: str) -> bool:
    """Check if a SKU is commercially sellable via the offering contract."""
    validator = get_sku_validator()
    result = validator.validate_sku(sku)
    return result.valid and result.is_published and result.is_sellable


def _sku_availability_policy(sku: str) -> str:
    """Return the configured availability policy for a SKU."""
    validator = get_sku_validator()
    info = validator.get_sku_info(sku)
    if info is None:
        return "planned_ok"
    return info.availability_policy or "planned_ok"


def _planned_supply_for_target(sku: str, target: date) -> Decimal:
    """Quantity expected from future-dated quants up to the target date."""
    today = date.today()
    if target <= today:
        return Decimal("0")
    return (
        Quant.objects.filter(
            sku=sku,
            target_date__gt=today,
            target_date__lte=target,
            _quantity__gt=0,
        ).aggregate(total=Sum("_quantity"))["total"]
        or Decimal("0")
    )


_ZERO_BREAKDOWN: dict = {
    "ready": Decimal("0"),
    "in_production": Decimal("0"),
    "planned": Decimal("0"),
    "d1": Decimal("0"),
}


def _zero_availability_dict(
    sku: str,
    availability_policy: str,
    safety_margin: int,
    *,
    is_paused: bool,
    is_tracked: bool = False,
) -> dict:
    """Shape for SKUs with no orderable stock (paused or missing).

    Shared by ``availability_for_sku`` and ``availability_for_skus`` so every
    caller sees the exact same key set regardless of which entrypoint they
    hit.
    """
    zero = Decimal("0")
    return {
        "sku": sku,
        "availability_policy": availability_policy,
        "total_available": zero,
        "total_promisable": zero,
        "total_reserved": zero,
        "available": zero,
        "expected": zero,
        "planned": zero,
        "ready_physical": zero,
        "held_ready": zero,
        "safety_margin": safety_margin,
        "breakdown": dict(_ZERO_BREAKDOWN),
        "is_planned": False,
        "is_paused": is_paused,
        "is_tracked": is_tracked,
        "positions": [],
    }


def _build_availability_dict(
    *,
    sku: str,
    availability_policy: str,
    ready: Decimal,
    in_production: Decimal,
    planned: Decimal,
    d1: Decimal,
    held_ready: Decimal,
    held_production: Decimal,
    held_planned: Decimal,
    held_d1: Decimal,
    safety_margin: int,
    is_planned: bool,
    positions_data: list,
    is_tracked: bool = True,
) -> dict:
    """Assemble the canonical availability dict from pre-computed buckets.

    Keeps the clamping / policy arithmetic in a single place so both the
    single-SKU and batch entrypoints stay shape-identical.
    """
    zero = Decimal("0")
    total_held = held_ready + held_production + held_planned + held_d1
    available = max(ready - held_ready - safety_margin, zero)
    expected = max(
        ready + in_production - held_ready - held_production - safety_margin,
        zero,
    )
    planned_clamped = max(planned - held_planned, zero)
    total_promisable = _policy_promisable_qty(
        availability_policy,
        available=available,
        expected=expected,
        planned=planned_clamped,
    )
    return {
        "sku": sku,
        "availability_policy": availability_policy,
        "total_available": available,
        "total_promisable": total_promisable,
        "total_reserved": total_held,
        "available": available,
        "expected": expected,
        "planned": planned_clamped,
        "ready_physical": ready,
        "held_ready": held_ready,
        "safety_margin": safety_margin,
        "breakdown": {
            "ready": ready - held_ready,
            "in_production": in_production - held_production,
            "planned": planned_clamped - held_planned,
            "d1": d1 - held_d1,
        },
        "is_planned": is_planned,
        "is_paused": False,
        "is_tracked": is_tracked,
        "positions": positions_data,
    }


def availability_for_sku(
    sku: str,
    position=None,
    safety_margin: int = 0,
    *,
    target_date: date | None = None,
    allowed_positions: list[str] | None = None,
    excluded_positions: list[str] | None = None,
) -> dict:
    """
    Build availability dict for a SKU with breakdown.

    Breakdown categories:
    - ready: Position.is_saleable=True, batch != "D-1"
    - in_production: Position.is_saleable=False (e.g. producao)
    - d1: batch == "D-1" (yesterday's leftovers)

    total_available = ready - held - safety_margin (only saleable stock).
    is_planned = True if any quant has a future target_date.

    If the offering contract marks the SKU as not orderable,
    returns zeros for orderable/available — stock may exist but is not for sale.

    ``allowed_positions`` / ``excluded_positions``: narrow the scope to
    channel-visible quants. Ignored when ``position`` is set (single-position
    query).
    """
    sellable = _sku_is_sellable(sku)
    availability_policy = _sku_availability_policy(sku)

    # If product is paused, return zeros (stock exists but not for sale)
    if not sellable:
        return _zero_availability_dict(
            sku, availability_policy, safety_margin, is_paused=True,
        )

    target = target_date or date.today()

    is_tracked = Quant.objects.filter(sku=sku).exists()

    planned_supply = _planned_supply_for_target(sku, target)
    is_planned = planned_supply > 0

    if position:
        quants = (
            Quant.objects.filter(sku=sku, position=position, _quantity__gt=0)
            .filter(Q(target_date__isnull=True) | Q(target_date__lte=target))
            .select_related("position")
        )
    else:
        quants = quants_eligible_for(
            sku,
            target_date=target,
            allowed_positions=allowed_positions,
            excluded_positions=excluded_positions,
        )

    ready = Decimal("0")
    in_production = Decimal("0")
    planned = Decimal("0")
    d1 = Decimal("0")
    held_ready = Decimal("0")
    held_production = Decimal("0")
    held_planned = Decimal("0")
    held_d1 = Decimal("0")
    positions_data = []

    for quant in quants:
        qty = quant._quantity
        held = quant.held

        # Classify into breakdown buckets
        if quant.batch == STARTED_BATCH:
            in_production += qty
            held_production += held
        elif quant.is_future:
            planned += qty
            held_planned += held
        elif quant.batch == "D-1":
            d1 += qty
            held_d1 += held
        elif quant.position and (
            quant.position.kind == "process" or not quant.position.is_saleable
        ):
            # Operational stock not yet saleable: explicit process positions or
            # non-saleable production areas.
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

    return _build_availability_dict(
        sku=sku,
        availability_policy=availability_policy,
        ready=ready,
        in_production=in_production,
        planned=planned,
        d1=d1,
        held_ready=held_ready,
        held_production=held_production,
        held_planned=held_planned,
        held_d1=held_d1,
        safety_margin=safety_margin,
        is_planned=is_planned,
        positions_data=positions_data,
        is_tracked=is_tracked,
    )


def promise_decision_for_sku(
    sku: str,
    qty: Decimal,
    *,
    target_date: date | None = None,
    safety_margin: int = 0,
    allowed_positions: list[str] | None = None,
    excluded_positions: list[str] | None = None,
) -> PromiseDecision:
    """Return an explicit operational promise decision for a SKU."""
    qty_d = Decimal(str(qty))
    info = availability_for_sku(
        sku,
        target_date=target_date,
        safety_margin=safety_margin,
        allowed_positions=allowed_positions,
        excluded_positions=excluded_positions,
    )
    available_qty = info["total_promisable"]
    availability_policy = info.get("availability_policy", "planned_ok")
    is_paused = info.get("is_paused", False)
    if is_paused:
        approved = False
        effective_available_qty = Decimal("0")
    elif availability_policy == "demand_ok":
        approved = True
        effective_available_qty = max(available_qty, qty_d)
    else:
        approved = qty_d <= available_qty
        effective_available_qty = available_qty

    reason_code = None
    if not approved:
        reason_code = "paused" if is_paused else "insufficient_supply"

    return PromiseDecision(
        approved=approved,
        sku=sku,
        requested_qty=qty_d,
        target_date=target_date,
        availability_policy=availability_policy,
        reason_code=reason_code,
        available_qty=effective_available_qty,
        available=info.get("available", Decimal("0")),
        expected=info.get("expected", Decimal("0")),
        planned=info.get("planned", Decimal("0")),
        is_planned=info.get("is_planned", False),
        is_paused=is_paused,
    )


def availability_for_skus(
    skus: list[str],
    safety_margin: int = 0,
    *,
    target_date: date | None = None,
    allowed_positions: list[str] | None = None,
    excluded_positions: list[str] | None = None,
) -> dict[str, dict]:
    """
    Batch version of availability_for_sku() — same logic, few queries regardless of N.

    Returns {sku: availability_dict} for all requested SKUs. Functionally
    identical to calling availability_for_sku() per SKU: shares the canonical
    scope gate (shelflife, batch expiry, position allow/deny, target_date) via
    per-SKU Python filtering on top of a bulk quant fetch.
    """
    from types import SimpleNamespace

    from shopman.stockman.models import Batch
    from shopman.stockman.shelflife import is_valid_for_date

    if not skus:
        return {}

    zero = Decimal("0")

    today = date.today()
    target = target_date or today

    # ── Query 1: orderable SKUs from the offering contract ───────────────────
    validator = get_sku_validator()
    validations = validator.validate_skus(skus)
    sku_infos = {sku: validator.get_sku_info(sku) for sku in skus}
    orderable_skus: set[str] = {
        sku
        for sku, validation in validations.items()
        if validation.valid and validation.is_published and validation.is_sellable
    }
    shelflife_by_sku: dict[str, int | None] = {
        sku: (info.shelflife_days if info is not None else None)
        for sku, info in sku_infos.items()
    }

    # ── Query 2: expired batch refs grouped by SKU ────────────────────────────
    # Maps sku → set of expired batch refs
    expired_refs_by_sku: dict[str, set[str]] = {}
    for row in Batch.objects.filter(sku__in=skus, expiry_date__lt=target).values("sku", "ref"):
        expired_refs_by_sku.setdefault(row["sku"], set()).add(row["ref"])

    # ── Query 3: planned SKUs (has future quants) ─────────────────────────────
    planned_skus: set[str] = set(
        Quant.objects.filter(
            sku__in=skus,
            target_date__gt=today,
            target_date__lte=target,
            _quantity__gt=0,
        ).values_list("sku", flat=True).distinct()
    )

    # ── Query 3b: which SKUs have ANY Quant at all (scope-independent) ────────
    tracked_skus: set[str] = set(
        Quant.objects.filter(sku__in=skus)
        .values_list("sku", flat=True)
        .distinct()
    )

    # ── Query 4: physical quants (current/past), select_related position ──────
    quant_qs = (
        Quant.objects.filter(sku__in=skus)
        .filter(Q(target_date__isnull=True) | Q(target_date__lte=target))
        .filter(_quantity__gt=0)
        .select_related("position")
    )
    if allowed_positions is not None:
        quant_qs = quant_qs.filter(position__ref__in=allowed_positions)
    if excluded_positions:
        quant_qs = quant_qs.exclude(position__ref__in=excluded_positions)

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
            availability_policy = (
                sku_infos.get(sku).availability_policy
                if sku_infos.get(sku) is not None
                else "planned_ok"
            )
            result[sku] = _zero_availability_dict(
                sku, availability_policy, safety_margin, is_paused=True,
                is_tracked=(sku in tracked_skus),
            )
            continue

        expired_refs = expired_refs_by_sku.get(sku, set())
        is_planned = sku in planned_skus
        availability_policy = (
            sku_infos.get(sku).availability_policy
            if sku_infos.get(sku) is not None
            else "planned_ok"
        )

        ready = Decimal("0")
        in_production = Decimal("0")
        planned = Decimal("0")
        d1 = Decimal("0")
        held_ready = Decimal("0")
        held_production = Decimal("0")
        held_planned = Decimal("0")
        held_d1 = Decimal("0")
        positions_data = []

        shelflife_ns = SimpleNamespace(
            sku=sku, shelf_life_days=shelflife_by_sku.get(sku),
        )

        for quant in quants_by_sku.get(sku, []):
            if quant.batch and quant.batch in expired_refs:
                continue
            if not is_valid_for_date(quant, shelflife_ns, target):
                continue

            qty = quant._quantity
            held = held_by_quant.get(quant.pk, zero)

            # Classify into breakdown buckets (same logic as availability_for_sku)
            if quant.batch == STARTED_BATCH:
                in_production += qty
                held_production += held
            elif quant.is_future:
                planned += qty
                held_planned += held
            elif quant.batch == "D-1":
                d1 += qty
                held_d1 += held
            elif quant.position and (
                quant.position.kind == "process" or not quant.position.is_saleable
            ):
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

        result[sku] = _build_availability_dict(
            sku=sku,
            availability_policy=availability_policy,
            ready=ready,
            in_production=in_production,
            planned=planned,
            d1=d1,
            held_ready=held_ready,
            held_production=held_production,
            held_planned=held_planned,
            held_d1=held_d1,
            safety_margin=safety_margin,
            is_planned=is_planned,
            positions_data=positions_data,
            is_tracked=(sku in tracked_skus),
        )

    return result


def availability_scope_for_channel(channel_ref: str | None) -> dict[str, int | list[str] | None]:
    """Único ponto para margem + posições ao calcular disponibilidade por canal.

    O catálogo (o que o canal "oferece") vem da Listagem vinculada ao canal; estes
    parâmetros só restringem **de quais posições físicas** o estoque conta para esse
    canal (ex.: remoto sem ``ontem`` para D-1 só no balcão).

    Restrições por canal (safety_margin, allowed_positions) são aplicadas pelo
    orquestrador shopman.shop antes de chamar stockman — stockman retorna os
    defaults seguros (sem restrição) e delega ao caller quando necessário.
    """
    return {"safety_margin": 0, "allowed_positions": None}
