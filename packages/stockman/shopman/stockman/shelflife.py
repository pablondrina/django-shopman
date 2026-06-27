"""
Shelflife validation — isolated, testable, reusable.

Determines whether a Quant is still valid for a given target date,
based on the product's shelf_life_days (days the product remains usable).

Examples:
    - Croissant (shelf_life_days=0): only valid on production day
    - Bolo (shelf_life_days=3): valid for 3 days after production
    - Wine (shelf_life_days=None): no expiration
"""

from datetime import date, timedelta

from django.db.models import Q


def is_valid_for_date(quant, product, target_date: date) -> bool:
    """
    Check if a specific quant is still valid for the target date.

    Args:
        quant: Quant instance (needs .target_date, .created_at)
        product: Product instance (needs .shelf_life_days attribute or None)
        target_date: The date we want to use/sell the product

    Returns:
        True if the quant is still valid for the target date
    """
    shelflife = getattr(product, 'shelf_life_days', None)

    if shelflife is None:
        # No expiration — physical stock or planned up to target
        if quant.target_date is None:
            return True
        return quant.target_date <= target_date

    min_production = target_date - timedelta(days=shelflife)

    if quant.target_date is None:
        # Physical stock: check creation date
        return quant.created_at.date() >= min_production

    # Planned stock: must be within shelflife window
    return min_production <= quant.target_date <= target_date


def filter_valid_quants(quants, product, target_date: date):
    """
    Filter a Quant queryset to only include quants valid for the target date.

    This is the queryset-level version of is_valid_for_date — used for
    bulk queries (available(), hold(), etc.).

    Args:
        quants: Quant QuerySet
        product: Product instance (needs .shelf_life_days attribute or None)
        target_date: The date we want to check validity for

    Returns:
        Filtered QuerySet
    """
    shelflife = getattr(product, 'shelf_life_days', None)

    if shelflife is not None:
        min_production = target_date - timedelta(days=shelflife)
        return quants.filter(
            Q(target_date__isnull=True, created_at__date__gte=min_production)
            | Q(target_date__gte=min_production, target_date__lte=target_date)
        )

    return quants.filter(
        Q(target_date__isnull=True) | Q(target_date__lte=target_date)
    )


# ── Lot consistency (Batch.expiry_date × Product.shelf_life_days) ────────────


def shelf_life_days_for(sku: str) -> int | None:
    """Resolve a SKU's ``shelf_life_days`` via the injected SkuValidator.

    Uses the same dependency-injection seam as availability (no Offerman import —
    Core packages stay independent). ``None`` = non-perishable or unknown.
    """
    from shopman.stockman.adapters.sku_validation import get_sku_validator

    info = get_sku_validator().get_sku_info(sku)
    return getattr(info, "shelflife_days", None) if info is not None else None


def batch_window_check(sku: str, production_date, expiry_date) -> tuple[str | None, str | None]:
    """Check a lot's dates against the product's shelf life.

    Returns ``(error, warning)``:

    - ``error`` — an impossible date (expiry before production). Always blocks.
    - ``warning`` — the lot claims a longer life than ``shelf_life_days`` allows.
      Surfaced as a non-blocking warning by default; escalated to an error only
      when ``STOCKMAN['STRICT_SHELF_LIFE_WINDOW']`` is on.

    No-op when either date is missing or the product is non-perishable
    (``shelf_life_days is None``).
    """
    if not production_date or not expiry_date:
        return None, None
    if expiry_date < production_date:
        return "Validade não pode ser anterior à data de produção.", None
    shelf = shelf_life_days_for(sku)
    if shelf is None:
        return None, None
    max_expiry = production_date + timedelta(days=shelf)
    if expiry_date > max_expiry:
        return None, (
            f"Validade {expiry_date:%d/%m/%Y} excede a janela do produto "
            f"(produção + {shelf}d = {max_expiry:%d/%m/%Y})."
        )
    return None, None
