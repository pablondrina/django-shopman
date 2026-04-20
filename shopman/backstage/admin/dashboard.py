"""Unfold admin dashboard callback — operator dashboard widgets.

Data is built by ``shopman.backstage.projections.dashboard.build_dashboard()``.
This module only handles admin-specific table formatting (``format_html``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.urls import reverse
from django.utils.html import format_html

from shopman.backstage.projections.dashboard import build_dashboard

_OMOTENASHI_TAG = re.compile(r"\{%[-\s]*omotenashi\b")
_STOREFRONT_TEMPLATES = Path(__file__).parents[2] / "storefront" / "templates" / "storefront"


def _omotenashi_health() -> dict:
    """Compute Omotenashi copy health stats for the admin dashboard widget."""
    html_files = sorted(_STOREFRONT_TEMPLATES.rglob("*.html"))
    total = len(html_files)
    using = sum(
        1 for f in html_files if _OMOTENASHI_TAG.search(f.read_text(encoding="utf-8"))
    )
    pct = round(using / total * 100) if total else 0

    try:
        from shopman.shop.models import OmotenashiCopy

        active_overrides = OmotenashiCopy.objects.filter(active=True).count()
        recent_changes = list(
            OmotenashiCopy.history.order_by("-history_date")
            .values("key", "history_type", "history_date", "history_user__username")[:5]
        )
    except Exception:
        active_overrides = 0
        recent_changes = []

    return {
        "total_templates": total,
        "using_omotenashi": using,
        "pct": pct,
        "active_overrides": active_overrides,
        "recent_changes": recent_changes,
    }


# ── Main callback ────────────────────────────────────────────────────


def dashboard_callback(request, context):
    """Populate admin dashboard with KPIs, charts, and tables."""
    proj = build_dashboard()

    context.update({
        # KPI cards
        "order_summary": proj.order_summary,
        "revenue": proj.revenue,
        "production": proj.production,
        "kpi_stock_alerts": proj.kpi_stock_alerts,
        "kpi_operator_alerts": proj.kpi_operator_alerts,
        # Quick-link URLs
        "orders_url": reverse("admin:orderman_order_changelist"),
        # Charts (JSON for Chart.js)
        "chart_pedidos_status": proj.chart_pedidos_status,
        "chart_pedidos_status_options": json.dumps({"indexAxis": "y"}),
        "chart_vendas_7dias": proj.chart_vendas_7dias,
        # Tables (admin-specific format_html rendering)
        "table_pedidos_pendentes": _build_pending_orders_table(proj.pending_orders),
        "table_producao": _build_production_table(proj.production.wos),
        "table_estoque_baixo": _build_alerts_table(proj.stock_alerts),
        "recent_orders": proj.recent_orders,
        "table_recentes": _build_recent_orders_table(proj.recent_orders),
        "d1_stock": proj.d1_stock,
        "table_d1": _build_d1_table(proj.d1_stock) if proj.d1_stock else None,
        "operator_alerts": proj.operator_alerts,
        "table_operator_alerts": _build_operator_alerts_table(proj.operator_alerts),
        "production_suggestions": proj.production_suggestions,
        "table_sugestao_producao": _build_suggestions_table(proj.production_suggestions),
        "omotenashi_health": _omotenashi_health(),
    })
    return context


# ── Table builders ───────────────────────────────────────────────────
# These stay here: they produce format_html output for Unfold table widgets.

WO_BADGE = {"open": "bg-amber-400", "done": "bg-green-500", "void": "bg-red-500"}
WO_LABEL = {"open": "Aberta", "done": "Conclu\u00edda", "void": "Cancelada"}
SEVERITY_ICONS = {"warning": "\u26a0\ufe0f", "error": "\u274c", "critical": "\U0001f534"}


def _build_pending_orders_table(pending_orders):
    """Pending orders (new, confirmed, preparing)."""
    rows = []
    for o in pending_orders:
        rows.append([
            format_html('<a href="{}" class="font-medium">{}</a>', o.url, o.ref),
            format_html(
                '<span class="inline-block rounded px-2 py-0.5 text-xs font-medium text-white {}">{}</span>',
                o.badge_css,
                o.status_label,
            ),
            o.total_display,
            o.created_at_display,
        ])

    return {
        "headers": ["Pedido", "Status", "Total", "Hora"],
        "rows": rows,
    }


def _build_recent_orders_table(orders):
    """Full recent orders table."""
    rows = []
    for o in orders:
        rows.append([
            format_html('<a href="{}" class="font-medium">{}</a>', o.url, o.ref),
            format_html(
                '<span class="inline-block rounded px-2 py-0.5 text-xs font-medium text-white {}">{}</span>',
                o.badge_css,
                o.status_label,
            ),
            o.total_display,
            o.channel_name,
            o.created_at_display,
        ])

    return {
        "headers": ["Pedido", "Status", "Total", "Canal", "Hora"],
        "rows": rows,
    }


def _build_production_table(wos):
    """Work orders table with status badge."""
    rows = []
    for wo in wos:
        rows.append([
            format_html('<a href="{}" class="font-medium">{}</a>', wo.url, wo.ref),
            wo.output_sku,
            wo.quantity,
            format_html(
                '<span class="inline-block rounded px-2 py-0.5 text-xs font-medium text-white {}">{}</span>',
                WO_BADGE.get(wo.status, "bg-gray-500"),
                WO_LABEL.get(wo.status, wo.status),
            ),
        ])

    return {
        "headers": ["C\u00f3digo", "Produto", "Qtd", "Status"],
        "rows": rows,
    }


def _build_alerts_table(alerts):
    """Stock alerts table with deficit highlighted."""
    rows = []
    for a in alerts:
        rows.append([
            a.sku,
            format_html('<span class="font-medium text-red-600">{}</span>', a.current),
            a.minimum,
            format_html('<span class="font-medium text-red-600">{}</span>', a.deficit),
            a.position,
        ])

    return {
        "headers": ["SKU", "Atual", "M\u00ednimo", "D\u00e9ficit", "Posi\u00e7\u00e3o"],
        "rows": rows,
    }


def _build_d1_table(d1_rows):
    """D-1 stock table for dashboard."""
    rows = []
    for item in d1_rows:
        rows.append([
            item.sku,
            item.name,
            item.qty,
            item.entry_date_display,
        ])

    return {
        "headers": ["SKU", "Produto", "Qtd", "Entrada"],
        "rows": rows,
    }


def _build_operator_alerts_table(alerts):
    """Operator alerts table for dashboard."""
    rows = []
    for alert in alerts:
        icon = SEVERITY_ICONS.get(alert.severity, "")
        rows.append([
            f"{icon} {alert.severity.upper()}",
            alert.message[:100],
            alert.order_ref or "\u2014",
            alert.created_at_display,
        ])
    return {
        "headers": ["Severidade", "Mensagem", "Pedido", "Data"],
        "rows": rows,
    }


def _build_suggestions_table(suggestions):
    """Production suggestions table for dashboard."""
    rows = []
    for s in suggestions:
        rows.append([
            s.recipe_name,
            s.output_sku,
            format_html('<span class="font-medium">{}</span>', s.quantity),
            s.avg_demand,
            s.safety_pct or "\u2014",
        ])

    return {
        "headers": ["Receita", "Produto", "Sugerido", "M\u00e9dia", "Margem"],
        "rows": rows,
    }
