"""Google product taxonomy — lenient validation.

Google Merchant accepts ``google_product_category`` either as a numeric id
(e.g. ``2271``) or as the full ``>``-separated path (e.g.
``Food, Beverages & Tobacco > Food Items > Bakery``). The full taxonomy is ~5k
rows; per SOCIAL-PIM-SPECS decision #3 we validate **leniently** now (shape only)
and can embed the CSV for strict validation later.
"""

from __future__ import annotations


def is_valid_google_category(value: str) -> bool:
    """Shape check: empty (allowed), a numeric id, or a ``>``-separated path."""
    value = (value or "").strip()
    if not value:
        return True
    if value.isdigit():
        return True
    # Path form: at least one segment, non-empty parts.
    parts = [p.strip() for p in value.split(">")]
    return all(parts) and len(parts) >= 1


def google_category_error(value: str) -> str:
    """Return an operator-facing error, or empty string when valid."""
    if is_valid_google_category(value):
        return ""
    return (
        "Categoria Google inválida: use o ID numérico (ex.: 2271) ou o caminho "
        "completo separado por ' > ' (ex.: 'Food, Beverages & Tobacco > Food Items > Bakery')."
    )
