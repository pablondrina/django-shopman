"""POS adapter — wraps Backstage POS tab persistence with lazy imports."""

from __future__ import annotations


def upsert_tab(*, ref: str, label: str, display: str) -> dict:
    from shopman.backstage.models import POSTab

    tab, _ = POSTab.objects.update_or_create(
        ref=ref,
        defaults={
            "label": label or display,
            "is_active": True,
        },
    )
    return {"tab_ref": tab.ref, "tab_display": tab.display_ref}


def ensure_tab(*, ref: str, display: str) -> str:
    from shopman.backstage.models import POSTab

    tab, _ = POSTab.objects.get_or_create(ref=ref, defaults={"label": display})
    return tab.display_ref


def cash_shift_is_closed(shift_id) -> bool:
    """True se o turno de caixa referido já foi fechado (ou não existe mais)."""
    from shopman.backstage.models import CashShift

    try:
        shift = CashShift.objects.filter(pk=int(shift_id)).first()
    except (TypeError, ValueError):
        return False
    return bool(shift and shift.closed_at is not None)
