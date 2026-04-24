"""DashboardProjection — read models for the admin dashboard (Fase 5).

Translates operational KPIs, charts, and table data into immutable
projections. Replaces the inline data building in
``shopman.shop.admin.dashboard.dashboard_callback``.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.urls import reverse

logger = logging.getLogger(__name__)


# ── Status maps ────────────────────────────────────────────────────────

STATUS_LABELS: dict[str, str] = {
    "new": "Novo",
    "confirmed": "Confirmado",
    "preparing": "Em Preparo",
    "ready": "Pronto",
    "dispatched": "Despachado",
    "delivered": "Entregue",
    "completed": "Concluído",
    "cancelled": "Cancelado",
    "returned": "Devolvido",
}

STATUS_CHART_COLORS: dict[str, str] = {
    "new": "#5EB1EF",
    "confirmed": "#5EB1EF",
    "preparing": "#E2A336",
    "ready": "#5BB98B",
    "dispatched": "#E2A336",
    "delivered": "#5BB98B",
    "completed": "#5BB98B",
    "cancelled": "#EB8E90",
    "returned": "#6B7280",
}

STATUS_BADGE_CSS: dict[str, str] = {
    "new": "bg-blue-500",
    "confirmed": "bg-emerald-500",
    "preparing": "bg-amber-500",
    "ready": "bg-violet-500",
    "dispatched": "bg-indigo-500",
    "delivered": "bg-green-600",
    "completed": "bg-green-700",
    "cancelled": "bg-red-500",
    "returned": "bg-gray-500",
}


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OrderStatusCardProjection:
    """A single status card in the orders KPI section."""

    status: str
    label: str
    count: int
    color: str
    url: str


@dataclass(frozen=True)
class OrderSummaryKPIProjection:
    """Orders KPI for today."""

    total: int
    new_count: int
    cards: tuple[OrderStatusCardProjection, ...]


@dataclass(frozen=True)
class RevenueKPIProjection:
    """Revenue KPI: today vs yesterday."""

    today_q: int
    today_display: str
    yesterday_q: int
    yesterday_display: str
    trend_up: bool
    has_yesterday: bool


@dataclass(frozen=True)
class WorkOrderTrackerProjection:
    """A single tracker block for a work order."""

    color: str
    tooltip: str


@dataclass(frozen=True)
class WorkOrderRowProjection:
    """A work order row for the production table."""

    ref: str
    output_sku: str
    quantity: str
    status: str
    url: str


@dataclass(frozen=True)
class ProductionKPIProjection:
    """Production KPI for today."""

    open: int
    done: int
    total: int
    progress: int
    wos: tuple[WorkOrderRowProjection, ...]
    tracker: tuple[WorkOrderTrackerProjection, ...]


@dataclass(frozen=True)
class StockAlertRowProjection:
    """A stock alert row."""

    sku: str
    current: str
    minimum: str
    deficit: str
    position: str


@dataclass(frozen=True)
class RecentOrderProjection:
    """A recent order for the dashboard table."""

    ref: str
    status: str
    status_label: str
    badge_css: str
    total_display: str
    channel_name: str
    created_at_display: str
    url: str


@dataclass(frozen=True)
class D1StockRowProjection:
    """A D-1 stock row."""

    sku: str
    name: str
    qty: str
    entry_date_display: str


@dataclass(frozen=True)
class OperatorAlertProjection:
    """An unacknowledged operator alert."""

    pk: int
    type: str
    severity: str
    message: str
    order_ref: str
    created_at_display: str


@dataclass(frozen=True)
class ProductionSuggestionProjection:
    """A production suggestion row."""

    recipe_ref: str
    recipe_name: str
    output_sku: str
    quantity: str
    avg_demand: str
    committed: str
    safety_pct: str
    sample_size: int


@dataclass(frozen=True)
class DashboardProjection:
    """Top-level read model for the admin dashboard."""

    # KPI sections
    order_summary: OrderSummaryKPIProjection
    revenue: RevenueKPIProjection
    production: ProductionKPIProjection
    stock_alerts: tuple[StockAlertRowProjection, ...]
    kpi_stock_alerts: int
    kpi_operator_alerts: int

    # Charts (JSON strings for Chart.js)
    chart_pedidos_status: str
    chart_vendas_7dias: str

    # Data rows
    pending_orders: tuple[RecentOrderProjection, ...]
    recent_orders: tuple[RecentOrderProjection, ...]
    d1_stock: tuple[D1StockRowProjection, ...]
    operator_alerts: tuple[OperatorAlertProjection, ...]
    production_suggestions: tuple[ProductionSuggestionProjection, ...]


# ── Builder ────────────────────────────────────────────────────────────


def build_dashboard() -> DashboardProjection:
    """Build the admin dashboard projection."""
    today = date.today()
    yesterday = today - timedelta(days=1)

    order_summary = _order_summary(today)
    revenue = _revenue(today, yesterday)
    production = _production(today)
    stock_alerts = _stock_alerts()
    pending_orders = _pending_orders(today)
    recent_orders = _recent_orders()
    d1_stock = _d1_stock()
    operator_alerts = _operator_alerts()
    suggestions = _production_suggestions(today + timedelta(days=1))

    return DashboardProjection(
        order_summary=order_summary,
        revenue=revenue,
        production=production,
        stock_alerts=tuple(stock_alerts),
        kpi_stock_alerts=len(stock_alerts),
        kpi_operator_alerts=len(operator_alerts),
        chart_pedidos_status=_chart_orders_by_status(today),
        chart_vendas_7dias=_chart_sales_7days(today),
        pending_orders=tuple(pending_orders),
        recent_orders=tuple(recent_orders),
        d1_stock=tuple(d1_stock),
        operator_alerts=tuple(operator_alerts),
        production_suggestions=tuple(suggestions),
    )


# ── KPI builders ───────────────────────────────────────────────────────


def _order_summary(today: date) -> OrderSummaryKPIProjection:
    from shopman.orderman.models import Order

    qs = (
        Order.objects
        .filter(created_at__date=today)
        .values("status")
        .annotate(count=Count("id"))
    )
    by_status = {row["status"]: row["count"] for row in qs}
    total = sum(by_status.values())
    new_count = by_status.get("new", 0)

    cards: list[OrderStatusCardProjection] = []
    for status, label in STATUS_LABELS.items():
        count = by_status.get(status, 0)
        if count > 0:
            cards.append(OrderStatusCardProjection(
                status=status,
                label=label,
                count=count,
                color=STATUS_CHART_COLORS.get(status, "#6B7280"),
                url=f'{reverse("admin:orderman_order_changelist")}?status__exact={status}',
            ))

    return OrderSummaryKPIProjection(total=total, new_count=new_count, cards=tuple(cards))


def _revenue(today: date, yesterday: date) -> RevenueKPIProjection:
    from shopman.orderman.models import Order

    confirmed_statuses = [
        "confirmed", "preparing", "ready",
        "dispatched", "delivered", "completed",
    ]
    today_q = (
        Order.objects
        .filter(created_at__date=today, status__in=confirmed_statuses)
        .aggregate(total=Sum("total_q"))
    )["total"] or 0

    yesterday_q = (
        Order.objects
        .filter(created_at__date=yesterday, status__in=confirmed_statuses)
        .aggregate(total=Sum("total_q"))
    )["total"] or 0

    return RevenueKPIProjection(
        today_q=today_q,
        today_display=_format_brl(today_q),
        yesterday_q=yesterday_q,
        yesterday_display=_format_brl(yesterday_q),
        trend_up=today_q >= yesterday_q,
        has_yesterday=yesterday_q > 0,
    )


def _production(today: date) -> ProductionKPIProjection:
    try:
        from shopman.craftsman.models import WorkOrder
    except ImportError:
        return ProductionKPIProjection(
            open=0, done=0, total=0, progress=0, wos=(), tracker=(),
        )

    wo_today = WorkOrder.objects.filter(created_at__date=today)
    total = wo_today.count()
    done = wo_today.filter(status="finished").count()
    open_count = wo_today.filter(status__in=["planned", "started"]).count()
    progress = int((done / total * 100) if total > 0 else 0)

    tracker: list[WorkOrderTrackerProjection] = []
    for wo in wo_today.order_by("ref"):
        if wo.status == "finished":
            tracker.append(WorkOrderTrackerProjection(
                color="bg-green-500", tooltip=f"{wo.ref}: Concluída",
            ))
        elif wo.started_at:
            tracker.append(WorkOrderTrackerProjection(
                color="bg-blue-500", tooltip=f"{wo.ref}: Em preparo",
            ))
        elif wo.status == "void":
            tracker.append(WorkOrderTrackerProjection(
                color="bg-red-500", tooltip=f"{wo.ref}: Cancelada",
            ))
        else:
            tracker.append(WorkOrderTrackerProjection(
                color="bg-amber-400", tooltip=f"{wo.ref}: Pendente",
            ))

    wos: list[WorkOrderRowProjection] = []
    for wo in wo_today.order_by("status", "ref")[:10]:
        wos.append(WorkOrderRowProjection(
            ref=wo.ref,
            output_sku=wo.output_sku,
            quantity=str(wo.quantity),
            status=wo.status,
            url=reverse("admin:craftsman_workorder_change", args=[wo.pk]),
        ))

    return ProductionKPIProjection(
        open=open_count,
        done=done,
        total=total,
        progress=progress,
        wos=tuple(wos),
        tracker=tuple(tracker),
    )


def _stock_alerts() -> list[StockAlertRowProjection]:
    try:
        from shopman.stockman.models import Quant, StockAlert
    except ImportError:
        return []

    alerts = StockAlert.objects.filter(is_active=True)
    rows: list[StockAlertRowProjection] = []
    for alert in alerts[:10]:
        quant_qs = Quant.objects.filter(sku=alert.sku)
        if alert.position_id:
            quant_qs = quant_qs.filter(position=alert.position)

        total_qty = quant_qs.aggregate(total=Sum("_quantity"))["total"] or Decimal("0")

        if total_qty < alert.min_quantity:
            rows.append(StockAlertRowProjection(
                sku=alert.sku,
                current=str(total_qty),
                minimum=str(alert.min_quantity),
                deficit=str(alert.min_quantity - total_qty),
                position=str(alert.position) if alert.position else "Todas",
            ))

    return rows


def _pending_orders(today: date) -> list[RecentOrderProjection]:
    from django.utils.formats import date_format
    from shopman.orderman.models import Order

    pending = (
        Order.objects
        .filter(status__in=["new", "confirmed", "preparing"])
        .order_by("-created_at")[:8]
    )
    return [
        RecentOrderProjection(
            ref=o.ref,
            status=o.status,
            status_label=STATUS_LABELS.get(o.status, o.status),
            badge_css=STATUS_BADGE_CSS.get(o.status, "bg-gray-500"),
            total_display=_format_brl(o.total_q),
            channel_name=o.channel_ref or "\u2014",
            created_at_display=(
                o.created_at.strftime("%H:%M")
                if o.created_at and o.created_at.date() == today
                else (date_format(o.created_at, "d/m H:i") if o.created_at else "\u2014")
            ),
            url=reverse("admin:orderman_order_change", args=[o.pk]),
        )
        for o in pending
    ]


def _recent_orders() -> list[RecentOrderProjection]:
    from django.utils.formats import date_format
    from shopman.orderman.models import Order

    orders = Order.objects.order_by("-created_at")[:10]
    return [
        RecentOrderProjection(
            ref=o.ref,
            status=o.status,
            status_label=STATUS_LABELS.get(o.status, o.status),
            badge_css=STATUS_BADGE_CSS.get(o.status, "bg-gray-500"),
            total_display=_format_brl(o.total_q),
            channel_name=o.channel_ref or "\u2014",
            created_at_display=date_format(o.created_at, "H:i") if o.created_at else "\u2014",
            url=reverse("admin:orderman_order_change", args=[o.pk]),
        )
        for o in orders
    ]


def _d1_stock() -> list[D1StockRowProjection]:
    try:
        from shopman.stockman import Move, Position, Quant
    except ImportError:
        return []

    from django.utils.formats import date_format

    ontem_pos = Position.objects.filter(ref="ontem").first()
    if not ontem_pos:
        return []

    quants = Quant.objects.filter(position=ontem_pos, _quantity__gt=0)
    if not quants.exists():
        return []

    rows: list[D1StockRowProjection] = []
    for quant in quants:
        last_move = (
            Move.objects.filter(quant=quant, reason__startswith="d1:")
            .order_by("-timestamp")
            .first()
        )
        entry_date = last_move.timestamp.date() if last_move else None

        try:
            from shopman.offerman.models import Product
            product = Product.objects.get(sku=quant.sku)
            name = product.name
        except Exception:
            name = quant.sku

        rows.append(D1StockRowProjection(
            sku=quant.sku,
            name=name,
            qty=str(quant._quantity),
            entry_date_display=date_format(entry_date, "d/m") if entry_date else "\u2014",
        ))

    return rows


def _operator_alerts() -> list[OperatorAlertProjection]:
    try:
        from django.utils.formats import date_format

        from shopman.backstage.models import OperatorAlert

        qs = OperatorAlert.objects.filter(acknowledged=False).order_by("-created_at")[:20]
        return [
            OperatorAlertProjection(
                pk=a.id,
                type=a.type,
                severity=a.severity,
                message=a.message,
                order_ref=a.order_ref or "",
                created_at_display=date_format(a.created_at, "d/m H:i") if a.created_at else "\u2014",
            )
            for a in qs
        ]
    except Exception:
        return []


def _production_suggestions(target_date: date) -> list[ProductionSuggestionProjection]:
    try:
        from shopman.craftsman.service import CraftService as craft
    except ImportError:
        return []

    try:
        suggestions = craft.suggest(date=target_date)
    except Exception:
        return []

    rows: list[ProductionSuggestionProjection] = []
    for s in suggestions:
        basis = s.basis or {}
        avg = basis.get("avg_demand", Decimal("0"))
        safety = basis.get("safety_pct", Decimal("0"))
        rows.append(ProductionSuggestionProjection(
            recipe_ref=s.recipe.ref,
            recipe_name=s.recipe.name,
            output_sku=s.recipe.output_sku,
            quantity=str(s.quantity),
            avg_demand=f"{avg:.1f}" if avg else "0",
            committed=str(basis.get("committed", Decimal("0"))),
            safety_pct=f"{safety:.0%}" if safety else "\u2014",
            sample_size=basis.get("sample_size", 0),
        ))
    return rows


# ── Charts ─────────────────────────────────────────────────────────────


def _chart_orders_by_status(today: date) -> str:
    from shopman.orderman.models import Order

    orders_today = Order.objects.filter(created_at__date=today)

    labels = []
    counts = []
    colors = []
    for status, label in STATUS_LABELS.items():
        count = orders_today.filter(status=status).count()
        if count > 0:
            labels.append(label)
            counts.append(count)
            colors.append(STATUS_CHART_COLORS.get(status, "#6B7280"))

    if not labels:
        return ""

    return json.dumps({
        "labels": labels,
        "datasets": [{
            "label": "Pedidos",
            "data": counts,
            "backgroundColor": colors,
            "borderRadius": 4,
        }],
    })


def _chart_sales_7days(today: date) -> str:
    from shopman.orderman.models import Order

    week_ago = today - timedelta(days=6)
    labels = []
    data = []

    for i in range(7):
        day = week_ago + timedelta(days=i)
        labels.append(day.strftime("%d/%m"))
        day_total = (
            Order.objects
            .filter(created_at__date=day)
            .aggregate(total=Sum("total_q"))
        )["total"] or 0
        data.append(round(day_total / 100, 2))

    if not any(v > 0 for v in data):
        return ""

    return json.dumps({
        "labels": labels,
        "datasets": [{
            "label": "Vendas (R$)",
            "data": data,
            "borderColor": "#5EB1EF",
            "backgroundColor": "rgba(94, 177, 239, 0.1)",
            "fill": True,
            "tension": 0.3,
        }],
    })


# ── Helpers ────────────────────────────────────────────────────────────


def _format_brl(centavos: int | None) -> str:
    if not centavos:
        return "R$ 0,00"
    value = centavos / 100
    formatted = f"{value:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"
