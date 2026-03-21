"""
Shelflife validation — isolated, testable, reusable.

Determines whether a Quant is still valid for a given target date,
based on the product's shelflife (days the product remains usable).

Examples:
    - Croissant (shelflife=0): only valid on production day
    - Bolo (shelflife=3): valid for 3 days after production
    - Wine (shelflife=None): no expiration
"""

from datetime import date, timedelta

from django.db.models import Q


def is_valid_for_date(quant, product, target_date: date) -> bool:
    """
    Check if a specific quant is still valid for the target date.

    Args:
        quant: Quant instance (needs .target_date, .created_at)
        product: Product instance (needs .shelflife attribute or None)
        target_date: The date we want to use/sell the product

    Returns:
        True if the quant is still valid for the target date
    """
    shelflife = getattr(product, 'shelflife', None)

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
        product: Product instance (needs .shelflife attribute or None)
        target_date: The date we want to check validity for

    Returns:
        Filtered QuerySet
    """
    shelflife = getattr(product, 'shelflife', None)

    if shelflife is not None:
        min_production = target_date - timedelta(days=shelflife)
        return quants.filter(
            Q(target_date__isnull=True, created_at__date__gte=min_production)
            | Q(target_date__gte=min_production, target_date__lte=target_date)
        )

    return quants.filter(
        Q(target_date__isnull=True) | Q(target_date__lte=target_date)
    )
