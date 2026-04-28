"""Shared operator context for backstage surfaces."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Sum
from django.utils import timezone

from shopman.backstage.services import alerts as alert_service


@dataclass(frozen=True)
class OperatorKpisToday:
    orders_count: int = 0
    revenue_q: int = 0
    production_planned_orders: int = 0
    production_started_orders: int = 0
    production_finished_orders: int = 0


@dataclass(frozen=True)
class OperatorPermissions:
    can_operate_pos: bool = False
    can_operate_kds: bool = False
    can_manage_orders: bool = False
    can_access_production: bool = False


@dataclass(frozen=True)
class OperatorContext:
    is_active: bool = False
    event_scope: str = "main"
    shift_state: str = "closed"
    shift_cash_session_id: int | None = None
    active_alerts_count: int = 0
    critical_alerts_count: int = 0
    kpis_today: OperatorKpisToday = OperatorKpisToday()
    position_default_ref: str = ""
    permissions: OperatorPermissions = OperatorPermissions()


def build_operator_context(request) -> OperatorContext:
    """Build a lightweight, shared context for operator-facing templates."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_staff:
        return OperatorContext()

    cash_session = _open_cash_session(user)
    active_alerts_count, critical_alerts_count = _alert_counts()
    kpis = _kpis_today()
    default_position_ref = _default_position_ref()
    event_scope = _event_scope()

    return OperatorContext(
        is_active=True,
        event_scope=event_scope,
        shift_state="open" if cash_session else "closed",
        shift_cash_session_id=getattr(cash_session, "pk", None),
        active_alerts_count=active_alerts_count,
        critical_alerts_count=critical_alerts_count,
        kpis_today=kpis,
        position_default_ref=default_position_ref,
        permissions=_permissions(user),
    )


def _open_cash_session(user):
    from shopman.backstage.models import CashRegisterSession

    return CashRegisterSession.get_open_for_operator(user)


def _alert_counts() -> tuple[int, int]:
    counts = alert_service.active_counts()
    return counts.active, counts.critical


def _kpis_today() -> OperatorKpisToday:
    today = timezone.localdate()
    return OperatorKpisToday(
        orders_count=_orders_count(today),
        revenue_q=_orders_revenue_q(today),
        production_planned_orders=_work_orders_count(today, "planned"),
        production_started_orders=_work_orders_count(today, "started"),
        production_finished_orders=_work_orders_count(today, "finished"),
    )


def _orders_count(day) -> int:
    from shopman.orderman.models import Order

    return (
        Order.objects.filter(created_at__date=day)
        .exclude(status__in=[Order.Status.CANCELLED, Order.Status.RETURNED])
        .count()
    )


def _orders_revenue_q(day) -> int:
    from shopman.orderman.models import Order

    total = (
        Order.objects.filter(created_at__date=day)
        .exclude(status__in=[Order.Status.CANCELLED, Order.Status.RETURNED])
        .aggregate(total=Sum("total_q"))["total"]
        or 0
    )
    return int(total)


def _work_orders_count(day, status: str) -> int:
    from shopman.craftsman.models import WorkOrder

    return WorkOrder.objects.filter(target_date=day, status=status).count()


def _default_position_ref() -> str:
    from shopman.stockman.models import Position

    position = Position.objects.filter(is_default=True).only("ref").first()
    return position.ref if position else ""


def _event_scope() -> str:
    from shopman.shop.models import Shop

    shop = Shop.objects.only("pk").first()
    return f"shop-{shop.pk}" if shop else "main"


def _permissions(user) -> OperatorPermissions:
    from shopman.backstage.projections.production import resolve_production_access

    production_access = resolve_production_access(user)
    return OperatorPermissions(
        can_operate_pos=user.has_perm("backstage.operate_pos"),
        can_operate_kds=user.has_perm("backstage.operate_kds"),
        can_manage_orders=user.has_perm("shop.manage_orders"),
        can_access_production=production_access.can_access_board,
    )
