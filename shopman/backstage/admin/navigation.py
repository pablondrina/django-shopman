"""Admin/Unfold navigation tuned for operational backoffice.

The sidebar is intentionally split between live operation shortcuts and
backoffice/audit tools. Operator cockpit links go to Backstage; CRUD/audit links
stay in Admin.
"""

from __future__ import annotations

import logging
from datetime import date

from django.urls import NoReverseMatch, reverse

logger = logging.getLogger(__name__)


def get_sidebar_navigation(request):
    """Return the canonical Admin sidebar for this Shopman installation."""
    return [
        _group("Operação ao vivo", "bolt", [
            _item(
                "Pedidos",
                "receipt_long",
                _url("admin_console_orders"),
                permission=_can_manage_orders,
                badge="shopman.backstage.admin.navigation.badge_new_orders",
                badge_variant="warning",
            ),
            _item(
                "Produção",
                "manufacturing",
                _url("admin_console_production"),
                permission=_can_access_production,
                badge="shopman.backstage.admin.navigation.badge_started_work_orders",
                badge_variant="info",
            ),
            _item(
                "Fechamento",
                "fact_check",
                _url("admin_console_day_closing"),
                permission=_can_close_day,
            ),
            _item(
                "POS",
                "point_of_sale",
                _url("backstage:pos"),
                permission=_can_operate_pos,
            ),
            _item(
                "KDS",
                "tv",
                _url("admin_console_kds"),
                permission=_can_operate_kds,
            ),
            _item(
                "Alertas ativos",
                "warning",
                _url("admin:backstage_operatoralert_changelist") + "?acknowledged__exact=0",
                permission=_can_view_operator_alerts,
                badge="shopman.backstage.admin.navigation.badge_operator_alerts",
                badge_variant="danger",
                badge_style="solid",
            ),
        ], collapsible=False),
        _group("Pedidos e canais", "hub", [
            _item("Histórico de pedidos", "assignment", _url("admin:orderman_order_changelist"), permission=_can_manage_orders),
            _item("Sessões abertas", "shopping_bag", _url("admin:orderman_session_changelist") + "?state__exact=open", permission=_can_manage_orders),
            _item("Diretivas pendentes", "playlist_add_check", _url("admin:orderman_directive_changelist") + "?status__exact=queued", permission=_can_manage_orders),
            _item("POS tabs", "confirmation_number", _url("admin:backstage_postab_changelist"), permission=_can_operate_pos),
            _item("Canais", "storefront", _url("admin:shop_channel_changelist"), permission=_is_staff),
        ]),
        _group("Produção", "factory", [
            _item("Painel", "monitoring", _url("admin_console_production_dashboard"), permission=_can_access_production),
            _item("Planejamento", "edit_calendar", _url("admin_console_production_planning"), permission=_can_access_production),
            _item("Produção", "manufacturing", _url("admin_console_production"), permission=_can_access_production),
            _item("Fichas técnicas", "menu_book", _url("admin:craftsman_recipe_changelist"), permission=_can_access_production),
            _item("Relatórios", "table_chart", _url("admin_console_production_reports"), permission=_can_view_production_reports),
        ]),
        _group("Estoque", "inventory_2", [
            _item("Saldos", "point_scan", _url("admin:stockman_quant_changelist"), permission=_is_staff),
            _item("Reservas", "keep", _url("admin:stockman_hold_changelist"), permission=_is_staff),
            _item("Movimentos", "swap_horiz", _url("admin:stockman_move_changelist"), permission=_is_staff),
            _item("Lotes", "science", _url("admin:stockman_batch_changelist"), permission=_is_staff),
            _item("Posições", "domain", _url("admin:stockman_position_changelist"), permission=_is_staff),
            _item("Alertas de estoque", "notification_important", _url("admin:stockman_stockalert_changelist"), permission=_is_staff),
        ]),
        _group("Catálogo e loja", "store", [
            _item("Produtos", "bakery_dining", _url("admin:offerman_product_changelist"), permission=_is_staff),
            _item("Coleções", "category", _url("admin:offerman_collection_changelist"), permission=_is_staff),
            _item("Listagens", "shoppingmode", _url("admin:offerman_listing_changelist"), permission=_is_staff),
            _item("Promoções", "sell", _url("admin:storefront_promotion_changelist"), permission=_is_staff),
            _item("Cupons", "confirmation_number", _url("admin:storefront_coupon_changelist"), permission=_is_staff),
            _item("Configuração da Loja", "tune", _url("admin:shop_shop_changelist"), permission=_is_staff),
        ]),
        _group("Clientes", "people", [
            _item("Clientes", "person_search", _url("admin:guestman_customer_changelist"), permission=_is_staff),
            _item("Grupos", "groups", _url("admin:guestman_customergroup_changelist"), permission=_is_staff),
            _item("Endereços", "location_on", _url("admin:guestman_customeraddress_changelist"), permission=_is_staff),
        ]),
        _group("Auditoria e acesso", "admin_panel_settings", [
            _item("Fechamentos", "event_available", _url("admin:backstage_dayclosing_changelist"), permission=_can_close_day),
            _item("Caixa POS", "payments", _url("admin:backstage_cashregistersession_changelist"), permission=_can_operate_pos),
            _item("Estações KDS", "settings_input_component", _url("admin:backstage_kdsinstance_changelist"), permission=_can_operate_kds),
            _item("Usuários", "person", _url("admin:auth_user_changelist"), permission=_is_superuser),
            _item("Grupos", "group", _url("admin:auth_group_changelist"), permission=_is_superuser),
        ]),
    ]


def badge_new_orders(request) -> str:
    from shopman.orderman.models import Order

    return str(Order.objects.filter(status=Order.Status.NEW).count())


def badge_started_work_orders(request) -> str:
    from shopman.craftsman.models import WorkOrder

    today = date.today()
    return str(WorkOrder.objects.filter(target_date=today, status=WorkOrder.Status.STARTED).count())


def badge_operator_alerts(request) -> str:
    from shopman.backstage.models import OperatorAlert

    return str(OperatorAlert.objects.filter(acknowledged=False).count())


def _group(title: str, icon: str, items: list[dict], *, collapsible: bool = True) -> dict:
    return {
        "title": title,
        "icon": icon,
        "separator": True,
        "collapsible": collapsible,
        "items": items,
    }


def _item(
    title: str,
    icon: str,
    link: str,
    *,
    permission,
    badge: str | None = None,
    badge_variant: str = "primary",
    badge_style: str = "soft",
) -> dict:
    item = {
        "title": title,
        "icon": icon,
        "link": link,
        "permission": permission,
    }
    if badge:
        item.update({
            "badge": badge,
            "badge_variant": badge_variant,
            "badge_style": badge_style,
        })
    return item


def _url(name: str) -> str:
    try:
        return reverse(name)
    except NoReverseMatch:
        return "#"


def _is_staff(request) -> bool:
    return bool(getattr(request.user, "is_staff", False))


def _is_superuser(request) -> bool:
    return bool(getattr(request.user, "is_superuser", False))


def _can_manage_orders(request) -> bool:
    return _is_superuser(request) or request.user.has_perm("shop.manage_orders")


def _can_access_production(request) -> bool:
    if _is_superuser(request) or request.user.has_perm("shop.manage_production"):
        return True
    try:
        from shopman.backstage.projections.production import resolve_production_access

        return resolve_production_access(request.user).can_access_board
    except Exception:
        logger.warning("admin_navigation_production_access_failed", exc_info=True)
        return False


def _can_view_production_reports(request) -> bool:
    return (
        _can_access_production(request)
        or request.user.has_perm("backstage.view_production_reports")
    )


def _can_close_day(request) -> bool:
    return _is_superuser(request) or request.user.has_perm("backstage.perform_closing")


def _can_operate_pos(request) -> bool:
    return _is_superuser(request) or request.user.has_perm("backstage.operate_pos")


def _can_operate_kds(request) -> bool:
    return _is_superuser(request) or request.user.has_perm("backstage.operate_kds")


def _can_view_operator_alerts(request) -> bool:
    return _is_staff(request) and (
        _is_superuser(request)
        or _can_manage_orders(request)
        or _can_access_production(request)
        or _can_operate_pos(request)
        or _can_operate_kds(request)
    )
