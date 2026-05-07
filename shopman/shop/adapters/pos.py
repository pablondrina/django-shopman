"""POS adapter — wraps Backstage POS tab persistence with lazy imports."""

from __future__ import annotations


def upsert_tab(*, code: str, label: str, display: str) -> dict:
    from shopman.backstage.models import POSTab

    tab, _ = POSTab.objects.update_or_create(
        code=code,
        defaults={
            "label": label or display,
            "is_active": True,
        },
    )
    return {"tab_code": tab.code, "tab_display": tab.display_code}


def ensure_tab(*, code: str, display: str) -> None:
    from shopman.backstage.models import POSTab

    POSTab.objects.get_or_create(code=code, defaults={"label": display})
