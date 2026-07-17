"""Unfold admin dashboard callback — landing de configuração e auditoria.

O Admin é CRUD mínimo + configurações: a operação ao vivo mora nos apps Nuxt
(Gestor/PDV/KDS/Fournil). O dashboard reúne atalhos de configuração, trilhas
de auditoria, saúde da copy omotenashi e os dados de atenção (alertas de
estoque, alertas do operador, estoque D-1 pendente de fechamento).

Data is built by ``shopman.backstage.projections.dashboard.build_dashboard()``.
This module only handles admin-specific table formatting (``format_html``).
"""

from __future__ import annotations

import logging

from django.urls import reverse
from django.utils.html import format_html

from shopman.backstage.projections.dashboard import build_dashboard
from shopman.shop.services import pos_links

logger = logging.getLogger(__name__)


def _omotenashi_health() -> dict:
    """Compute Omotenashi copy health stats for the admin dashboard widget.

    A superfície do cliente é o storefront Nuxt (headless): o sinal de saúde
    aqui é o registro de copy (overrides ativos + alterações recentes).
    """
    try:
        from shopman.shop.models import OmotenashiCopy

        active_overrides = OmotenashiCopy.objects.filter(active=True).count()
        recent_changes = list(
            OmotenashiCopy.history.order_by("-history_date")
            .values("key", "history_type", "history_date", "history_user__username")[:5]
        )
    except Exception:
        logger.debug("omotenashi_health_query_failed", exc_info=True)
        active_overrides = 0
        recent_changes = []

    return {
        "active_overrides": active_overrides,
        "recent_changes": recent_changes,
    }


def _day_closing_url() -> str:
    """Deep-link do fechamento do dia na antesala do PDV; vazio ⇒ link oculto."""
    return pos_links.pos_url(pos_links.path_day_closing())


def _config_links() -> list[dict]:
    """Atalhos canônicos de configuração (o papel do Admin)."""
    return [
        {
            "label": "Loja & contato",
            "url": reverse("admin:shop_shop_changelist"),
            "icon": "storefront",
        },
        {
            # TODO(PR #110): quando o catálogo de copy ganhar rota própria em
            # /admin/configuracao/copy/, apontar este atalho para ela.
            "label": "Catálogo de copy",
            "url": reverse("admin:shop_omotenashicopy_changelist"),
            "icon": "edit_note",
        },
        {
            "label": "Templates de notificação",
            "url": reverse("admin:shop_notificationtemplate_changelist"),
            "icon": "notifications",
        },
        {
            "label": "Regras de preço",
            "url": reverse("admin:shop_ruleconfig_changelist"),
            "icon": "rule",
        },
        {
            "label": "Canais",
            "url": reverse("admin:shop_channel_changelist"),
            "icon": "hub",
        },
    ]


def _audit_links() -> list[dict]:
    """Trilhas readonly de auditoria (fechamentos, pagamentos, turnos)."""
    return [
        {
            "label": "Fechamentos",
            "url": reverse("admin:backstage_dayclosing_changelist"),
            "icon": "event_available",
        },
        {
            "label": "Pagamentos",
            "url": reverse("admin:payman_paymentintent_changelist"),
            "icon": "payments",
        },
        {
            "label": "Turnos de caixa",
            "url": reverse("admin:backstage_cashshift_changelist"),
            "icon": "point_of_sale",
        },
    ]


# ── Main callback ────────────────────────────────────────────────────


def dashboard_callback(request, context):
    """Populate admin dashboard with config shortcuts, audit trails and alerts."""
    proj = build_dashboard()

    context.update({
        # Config + auditoria
        "config_links": _config_links(),
        "audit_links": _audit_links(),
        "omotenashi_health": _omotenashi_health(),
        # Atenção (alertas e D-1)
        "kpi_stock_alerts": proj.kpi_stock_alerts,
        "kpi_operator_alerts": proj.kpi_operator_alerts,
        "table_estoque_baixo": _build_alerts_table(proj.stock_alerts),
        "operator_alerts": proj.operator_alerts,
        "table_operator_alerts": _build_operator_alerts_table(proj.operator_alerts),
        "d1_stock": proj.d1_stock,
        "table_d1": _build_d1_table(proj.d1_stock) if proj.d1_stock else None,
        # Fechamento do DIA vive na antesala do PDV (env-gated como o item da sidebar).
        "day_closing_url": _day_closing_url(),
    })
    return context


# ── Table builders ───────────────────────────────────────────────────
# These stay here: they produce format_html output for Unfold table widgets.

SEVERITY_ICONS = {"warning": "⚠️", "error": "❌", "critical": "\U0001f534"}


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
        "headers": ["SKU", "Atual", "Mínimo", "Déficit", "Posição"],
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
            alert.order_ref or "—",
            alert.created_at_display,
        ])
    return {
        "headers": ["Severidade", "Mensagem", "Pedido", "Data"],
        "rows": rows,
    }
