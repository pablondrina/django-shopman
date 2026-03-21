"""
Dashboard table helpers for Unfold admin.

Provides safe HTML builders for dashboard tables rendered via
``{% include "unfold/components/table.html" %}``.

Unfold's ``table.html`` renders cells with ``{{ cell }}`` (no ``|safe``),
so all HTML content must be pre-marked safe via ``format_html()`` or
``mark_safe()``. These helpers ensure that while keeping code DRY.

Usage in a dashboard callback::

    from shopman.utils.contrib.admin_unfold.tables import (
        DashboardTable,
        table_link,
        table_badge,
    )

    table = DashboardTable(
        headers=["Ref", "Canal", "Status", "Total"],
    )
    for order in orders:
        table.add_row([
            table_link(f"/admin/ordering/order/{order.pk}/change/", order.ref),
            order.channel.name,
            table_badge(order.get_status_display(), "green"),
            format_brl(order.total_q),
        ])

    context["my_table"] = table.as_dict()
"""

from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

# ── Color palettes ────────────────────────────────────────────────────

BADGE_COLORS = {
    "blue": "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    "green": "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
    "yellow": "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
    "red": "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    "gray": "bg-base-100 text-base-600 dark:bg-base-800 dark:text-base-400",
}


# ── Cell helpers (all return SafeText) ────────────────────────────────


def table_link(url, text, new_tab=False):
    """
    Render an admin-styled link cell.

    Returns ``SafeText`` — safe for use in Unfold dashboard tables.

    Args:
        url: Target URL (absolute or relative).
        text: Display text (will be escaped).
        new_tab: If True, opens in a new browser tab.
    """
    target = ' target="_blank" rel="noopener"' if new_tab else ""
    return format_html(
        '<a href="{}" class="text-primary-600 dark:text-primary-400 '
        'font-medium hover:underline"{}>{}</a>',
        url,
        mark_safe(target),
        text,
    )


def table_admin_link(model_name, pk, text, app_label=None):
    """
    Render an admin changform link from model info.

    Convenience wrapper around ``table_link`` that builds the URL
    from Django's admin URL resolver.

    Args:
        model_name: Model name (lowercase), e.g. ``"order"``.
        pk: Object primary key.
        text: Display text.
        app_label: App label, e.g. ``"ordering"``. If None, inferred
            from ``model_name`` (works for single-word models).
    """
    url_name = f"admin:{app_label}_{model_name}_change"
    url = reverse(url_name, args=[pk])
    return table_link(url, text)


def table_badge(text, color="gray"):
    """
    Render a colored badge cell.

    Returns ``SafeText`` — safe for use in Unfold dashboard tables.

    Args:
        text: Badge text (will be escaped).
        color: One of ``"blue"``, ``"green"``, ``"yellow"``,
            ``"red"``, ``"gray"``.
    """
    classes = BADGE_COLORS.get(color, BADGE_COLORS["gray"])
    return format_html(
        '<span class="inline-flex items-center px-2 py-0.5 '
        'rounded-md text-xs font-medium {}">{}</span>',
        classes,
        text,
    )


def table_text(text, muted=False):
    """
    Render a plain-text cell, optionally muted (gray).

    Returns ``SafeText`` — safe for use in Unfold dashboard tables.
    """
    if muted:
        return format_html(
            '<span class="text-base-400 dark:text-base-500">{}</span>',
            text,
        )
    return format_html("{}", text)


# ── Table builder ─────────────────────────────────────────────────────


class DashboardTable:
    """
    Fluent builder for Unfold dashboard tables.

    Produces the dict structure expected by
    ``{% include "unfold/components/table.html" %}``.

    Example::

        table = DashboardTable(headers=["Nome", "Valor"])
        table.add_row(["Pão Francês", table_badge("50", "green")])
        context["my_table"] = table.as_dict()

    Then in the template::

        {% include "unfold/components/table.html"
            with table=my_table card_included=1 striped=1 %}
    """

    def __init__(self, headers):
        self.headers = [str(h) for h in headers]
        self.rows = []

    def add_row(self, cells):
        """
        Append a row of cells.

        Each cell can be a plain string (auto-escaped by ``format_html``)
        or a ``SafeText`` from one of the cell helpers above.
        """
        safe_cells = []
        for cell in cells:
            if hasattr(cell, "__html__"):
                # Already SafeText (from format_html, mark_safe, etc.)
                safe_cells.append(cell)
            else:
                # Plain text — mark safe after escaping
                safe_cells.append(format_html("{}", cell))
            # Every cell must be SafeText so Unfold's {{ cell }} renders it
        self.rows.append(safe_cells)

    def as_dict(self):
        """
        Return the dict expected by Unfold's table.html component.

        Structure: ``{"headers": [...], "rows": [[...], ...]}``
        """
        return {
            "headers": self.headers,
            "rows": self.rows,
        }

    @property
    def is_empty(self):
        return len(self.rows) == 0
