"""Unfold admin dashboard callback — operator dashboard widgets."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.html import format_html

# ── Status maps (shared) ─────────────────────────────────────────────

STATUS_LABELS = {
    "new": "Novo",
    "confirmed": "Confirmado",
    "preparing": "Em Preparo",
    "ready": "Pronto",
    "dispatched": "Despachado",
    "delivered": "Entregue",
    "completed": "Conclu\u00eddo",
    "cancelled": "Cancelado",
    "returned": "Devolvido",
}

STATUS_CHART_COLORS = {
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

STATUS_BADGE_CSS = {
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


# ── Main callback ────────────────────────────────────────────────────


def dashboard_callback(request, context):
    """Populate admin dashboard with KPIs, charts, and tables."""
    today = date.today()
    yesterday = today - timedelta(days=1)

    order_summary = _order_summary(today)
    revenue = _revenue(today, yesterday)
    production = _production(today)
    stock_alerts = _stock_alerts()
    recent_orders = _recent_orders()

    d1_stock = _d1_stock()
    operator_alerts = _operator_alerts()
    suggestions = _production_suggestions(today + timedelta(days=1))

    context.update({
        # KPI cards
        "order_summary": order_summary,
        "revenue": revenue,
        "production": production,
        "kpi_stock_alerts": len(stock_alerts),
        "kpi_operator_alerts": operator_alerts["count"],
        # Quick-link URLs
        "orders_url": reverse("admin:orderman_order_changelist"),
        # Charts (JSON for Chart.js)
        "chart_pedidos_status": _chart_orders_by_status(today),
        "chart_pedidos_status_options": json.dumps({"indexAxis": "y"}),
        "chart_vendas_7dias": _chart_sales_7days(today),
        # Tables
        "table_pedidos_pendentes": _build_pending_orders_table(today),
        "table_producao": _build_production_table(production.get("wos", [])),
        "table_estoque_baixo": _build_alerts_table(stock_alerts),
        # Recent orders (full table, not just pending)
        "recent_orders": recent_orders,
        "table_recentes": _build_recent_orders_table(recent_orders),
        # D-1 stock
        "d1_stock": d1_stock,
        "table_d1": _build_d1_table(d1_stock) if d1_stock else None,
        # Operator alerts
        "operator_alerts": operator_alerts["items"],
        "table_operator_alerts": _build_operator_alerts_table(operator_alerts["items"]),
        # Production suggestions
        "production_suggestions": suggestions,
        "table_sugestao_producao": _build_suggestions_table(suggestions),
    })
    return context


# ── KPI: Order summary ───────────────────────────────────────────────


def _order_summary(today):
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

    cards = []
    for status, label in STATUS_LABELS.items():
        count = by_status.get(status, 0)
        if count > 0:
            cards.append({
                "status": status,
                "label": label,
                "count": count,
                "color": STATUS_CHART_COLORS.get(status, "#6B7280"),
                "url": f'{reverse("admin:orderman_order_changelist")}?status__exact={status}',
            })

    return {"total": total, "new_count": new_count, "cards": cards}


# ── KPI: Revenue with yesterday comparison ───────────────────────────


def _revenue(today, yesterday):
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

    return {
        "today_q": today_q,
        "today_display": _format_brl(today_q),
        "yesterday_q": yesterday_q,
        "yesterday_display": _format_brl(yesterday_q),
        "trend_up": today_q >= yesterday_q,
        "has_yesterday": yesterday_q > 0,
    }


# ── KPI: Production with progress ───────────────────────────────────


def _production(today):
    try:
        from shopman.craftsman.models import WorkOrder
    except ImportError:
        return {"open": 0, "done": 0, "total": 0, "progress": 0, "wos": [], "tracker": []}

    wo_today = WorkOrder.objects.filter(created_at__date=today)
    total = wo_today.count()
    done = wo_today.filter(status="done").count()
    open_count = wo_today.filter(status="open").count()
    progress = int((done / total * 100) if total > 0 else 0)

    # Tracker: per-WO colored blocks
    tracker = []
    for wo in wo_today.order_by("ref"):
        if wo.status == "done":
            tracker.append({"color": "bg-green-500", "tooltip": f"{wo.ref}: Conclu\u00edda"})
        elif wo.started_at:
            tracker.append({"color": "bg-blue-500", "tooltip": f"{wo.ref}: Em preparo"})
        elif wo.status == "void":
            tracker.append({"color": "bg-red-500", "tooltip": f"{wo.ref}: Cancelada"})
        else:
            tracker.append({"color": "bg-amber-400", "tooltip": f"{wo.ref}: Pendente"})

    # WO list for table
    wos = []
    for wo in wo_today.order_by("status", "ref")[:10]:
        wos.append({
            "ref": wo.ref,
            "output_ref": wo.output_ref,
            "quantity": wo.quantity,
            "status": wo.status,
            "url": reverse("admin:craftsman_workorder_change", args=[wo.pk]),
        })

    return {
        "open": open_count,
        "done": done,
        "total": total,
        "progress": progress,
        "wos": wos,
        "tracker": tracker,
    }


# ── KPI: Stock alerts ───────────────────────────────────────────────


def _stock_alerts():
    try:
        from shopman.stockman.models import Quant, StockAlert
    except ImportError:
        return []

    alerts = StockAlert.objects.filter(is_active=True)
    rows = []
    for alert in alerts[:10]:
        quant_qs = Quant.objects.filter(sku=alert.sku)
        if alert.position_id:
            quant_qs = quant_qs.filter(position=alert.position)

        total_qty = quant_qs.aggregate(total=Sum("_quantity"))["total"] or Decimal("0")

        if total_qty < alert.min_quantity:
            rows.append({
                "sku": alert.sku,
                "current": total_qty,
                "minimum": alert.min_quantity,
                "deficit": alert.min_quantity - total_qty,
                "position": str(alert.position) if alert.position else "Todas",
            })

    return rows


# ── Recent orders (full list) ────────────────────────────────────────


def _recent_orders():
    from shopman.orderman.models import Order

    orders = (
        Order.objects
        
        .order_by("-created_at")[:10]
    )
    return [
        {
            "ref": o.ref,
            "status": o.status,
            "status_label": STATUS_LABELS.get(o.status, o.status),
            "total_display": _format_brl(o.total_q),
            "channel_name": o.channel_ref or "\u2014",
            "created_at": o.created_at,
            "url": reverse("admin:orderman_order_change", args=[o.pk]),
        }
        for o in orders
    ]


# ── Charts ───────────────────────────────────────────────────────────


def _chart_orders_by_status(today):
    """Bar chart: orders by status (horizontal)."""
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


def _chart_sales_7days(today):
    """Line chart: sales trend over last 7 days."""
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


# ── Table builders ───────────────────────────────────────────────────


def _build_pending_orders_table(today):
    """Pending orders (new, confirmed, preparing)."""
    from shopman.orderman.models import Order

    pending = (
        Order.objects
        .filter(status__in=["new", "confirmed", "preparing"])
        
        .order_by("-created_at")[:8]
    )
    rows = []
    for o in pending:
        if o.created_at and o.created_at.date() == today:
            time_str = o.created_at.strftime("%H:%M")
        elif o.created_at:
            time_str = o.created_at.strftime("%d/%m %H:%M")
        else:
            time_str = "\u2014"

        rows.append([
            format_html(
                '<a href="{}" class="font-medium">{}</a>',
                reverse("admin:orderman_order_change", args=[o.pk]),
                o.ref,
            ),
            format_html(
                '<span class="inline-block rounded px-2 py-0.5 text-xs font-medium text-white {}">{}</span>',
                STATUS_BADGE_CSS.get(o.status, "bg-gray-500"),
                STATUS_LABELS.get(o.status, o.status),
            ),
            _format_brl(o.total_q) if o.total_q else "\u2014",
            time_str,
        ])

    return {
        "headers": ["Pedido", "Status", "Total", "Hora"],
        "rows": rows,
    }


def _build_recent_orders_table(orders):
    """Full recent orders table."""
    rows = []
    for o in orders:
        css = STATUS_BADGE_CSS.get(o["status"], "bg-gray-500")
        rows.append([
            format_html('<a href="{}" class="font-medium">{}</a>', o["url"], o["ref"]),
            format_html(
                '<span class="inline-block rounded px-2 py-0.5 text-xs font-medium text-white {}">{}</span>',
                css,
                o["status_label"],
            ),
            o["total_display"],
            o["channel_name"],
            date_format(o["created_at"], "H:i") if o["created_at"] else "\u2014",
        ])

    return {
        "headers": ["Pedido", "Status", "Total", "Canal", "Hora"],
        "rows": rows,
    }


def _build_production_table(wos):
    """Work orders table with status badge."""
    WO_BADGE = {"open": "bg-amber-400", "done": "bg-green-500", "void": "bg-red-500"}
    WO_LABEL = {"open": "Aberta", "done": "Conclu\u00edda", "void": "Cancelada"}

    rows = []
    for wo in wos:
        rows.append([
            format_html('<a href="{}" class="font-medium">{}</a>', wo["url"], wo["code"]),
            wo["output_ref"],
            str(wo["quantity"]),
            format_html(
                '<span class="inline-block rounded px-2 py-0.5 text-xs font-medium text-white {}">{}</span>',
                WO_BADGE.get(wo["status"], "bg-gray-500"),
                WO_LABEL.get(wo["status"], wo["status"]),
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
            a["sku"],
            format_html('<span class="font-medium text-red-600">{}</span>', str(a["current"])),
            str(a["minimum"]),
            format_html('<span class="font-medium text-red-600">{}</span>', str(a["deficit"])),
            a["position"],
        ])

    return {
        "headers": ["SKU", "Atual", "M\u00ednimo", "D\u00e9ficit", "Posi\u00e7\u00e3o"],
        "rows": rows,
    }


# ── D-1 stock ────────────────────────────────────────────────────────


def _d1_stock():
    """Fetch D-1 stock in position 'ontem'."""
    try:
        from shopman.stockman import Move, Position, Quant
    except ImportError:
        return []

    ontem_pos = Position.objects.filter(ref="ontem").first()
    if not ontem_pos:
        return []

    quants = Quant.objects.filter(position=ontem_pos, _quantity__gt=0)
    if not quants.exists():
        return []

    rows = []
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

        rows.append({
            "sku": quant.sku,
            "name": name,
            "qty": quant._quantity,
            "entry_date": entry_date,
        })

    return rows


def _build_d1_table(d1_rows):
    """D-1 stock table for dashboard."""
    rows = []
    for item in d1_rows:
        entry_str = date_format(item["entry_date"], "d/m") if item["entry_date"] else "\u2014"
        rows.append([
            item["sku"],
            item["name"],
            str(item["qty"]),
            entry_str,
        ])

    return {
        "headers": ["SKU", "Produto", "Qtd", "Entrada"],
        "rows": rows,
    }


# ── Operator Alerts ──────────────────────────────────────────────────


def _operator_alerts():
    """Fetch unacknowledged operator alerts."""
    try:
        from shopman.models import OperatorAlert

        qs = OperatorAlert.objects.filter(acknowledged=False).order_by("-created_at")[:20]
        items = list(qs.values("id", "type", "severity", "message", "order_ref", "created_at"))
        return {"count": qs.count(), "items": items}
    except Exception:
        return {"count": 0, "items": []}


def _build_operator_alerts_table(alerts):
    """Operator alerts table for dashboard."""
    severity_icons = {"warning": "\u26a0\ufe0f", "error": "\u274c", "critical": "\U0001f534"}
    rows = []
    for alert in alerts:
        created = alert.get("created_at")
        time_str = date_format(created, "d/m H:i") if created else "\u2014"
        icon = severity_icons.get(alert.get("severity", ""), "")
        rows.append([
            f"{icon} {alert.get('severity', '').upper()}",
            alert.get("message", "")[:100],
            alert.get("order_ref", "") or "\u2014",
            time_str,
        ])
    return {
        "headers": ["Severidade", "Mensagem", "Pedido", "Data"],
        "rows": rows,
    }


# ── Production Suggestions ──────────────────────────────────────────


def _production_suggestions(target_date):
    """Fetch production suggestions for target_date via CraftService.suggest()."""
    try:
        from shopman.craftsman.service import CraftService as craft
    except ImportError:
        return []

    try:
        suggestions = craft.suggest(date=target_date)
    except Exception:
        return []

    rows = []
    for s in suggestions:
        basis = s.basis or {}
        rows.append({
            "recipe_code": s.recipe.code,
            "recipe_name": s.recipe.name,
            "output_ref": s.recipe.output_ref,
            "quantity": s.quantity,
            "avg_demand": basis.get("avg_demand", Decimal("0")),
            "committed": basis.get("committed", Decimal("0")),
            "safety_pct": basis.get("safety_pct", Decimal("0")),
            "sample_size": basis.get("sample_size", 0),
        })
    return rows


def _build_suggestions_table(suggestions):
    """Production suggestions table for dashboard."""
    rows = []
    for s in suggestions:
        avg = s["avg_demand"]
        safety = s["safety_pct"]
        rows.append([
            s["recipe_name"],
            s["output_ref"],
            format_html(
                '<span class="font-medium">{}</span>',
                str(s["quantity"]),
            ),
            f"{avg:.1f}",
            f"{safety:.0%}" if safety else "\u2014",
        ])

    return {
        "headers": ["Receita", "Produto", "Sugerido", "M\u00e9dia", "Margem"],
        "rows": rows,
    }


# ── Helpers ──────────────────────────────────────────────────────────


def _format_brl(centavos):
    """Format centavos as BRL string (pt-BR: R$ 1.500,00)."""
    if not centavos:
        return "R$ 0,00"
    value = centavos / 100
    formatted = f"{value:,.2f}"
    # pt-BR: thousand sep = dot, decimal sep = comma
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"
