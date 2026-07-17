"""Admin/Unfold navigation tuned for operational backoffice.

The sidebar is intentionally split between live operation shortcuts and
backoffice/audit tools. Operator cockpit links go to Backstage; CRUD/audit links
stay in Admin.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from shopman.backstage import permissions

logger = logging.getLogger(__name__)


def _pos_base_url() -> str:
    """Base absoluta do PDV (superfície Nuxt). Vazio ⇒ item de PDV oculto.

    O PDV migrou para Nuxt (surfaces/pos-nuxt, headless via
    api/v1/backstage/pos/*); não há rota Django. O link do operador aponta para a
    superfície Nuxt, configurável por deployment (como SHOPMAN_STOREFRONT_BASE_URL).
    """
    return (getattr(settings, "SHOPMAN_POS_BASE_URL", "") or "").rstrip("/")


def _orders_base_url() -> str:
    """Base absoluta do Gestor de Pedidos (surfaces/orders-nuxt). Vazio ⇒ oculto."""
    return (getattr(settings, "SHOPMAN_ORDERS_BASE_URL", "") or "").rstrip("/")


def _kds_base_url() -> str:
    """Base absoluta do KDS (surfaces/kds-nuxt). Vazio ⇒ oculto."""
    return (getattr(settings, "SHOPMAN_KDS_BASE_URL", "") or "").rstrip("/")


def _production_base_url() -> str:
    """Base absoluta da Produção (surfaces/production-nuxt). Vazio ⇒ oculto."""
    return (getattr(settings, "SHOPMAN_PRODUCTION_BASE_URL", "") or "").rstrip("/")


def get_sidebar_navigation(request):
    """Return the canonical Admin sidebar for this Shopman installation.

    Pedidos/POS/KDS são apps Nuxt headless dedicados (sem rota Django): só
    aparecem quando a base URL do deployment está configurada (evita link morto).
    O histórico/CRUD de pedidos segue no grupo "Pedidos e canais".
    """
    live_items = []
    orders_url = _orders_base_url()
    if orders_url:
        live_items.append(
            _item(
                "Pedidos",
                "receipt_long",
                orders_url,
                permission=_can_manage_orders,
                badge="shopman.backstage.admin.navigation.badge_new_orders",
                badge_variant="warning",
            )
        )
    live_items.append(
        _item(
            "Produção",
            "manufacturing",
            _url("admin_console_production"),
            permission=_can_access_production,
            badge="shopman.backstage.admin.navigation.badge_started_work_orders",
            badge_variant="info",
        )
    )
    live_items.append(
        _item(
            "Fechamento",
            "fact_check",
            _url("admin_console_day_closing"),
            permission=_can_close_day,
        )
    )
    pos_url = _pos_base_url()
    if pos_url:
        live_items.append(_item("POS", "point_of_sale", pos_url, permission=_can_operate_pos))
    kds_url = _kds_base_url()
    if kds_url:
        live_items.append(_item("KDS", "tv", kds_url, permission=_can_operate_kds))
    production_url = _production_base_url()
    if production_url:
        live_items.append(
            _item(
                "Produção ao vivo",
                "factory",
                production_url,
                permission=_can_operate_production,
            )
        )
    live_items.append(
        _item(
            "Alertas ativos",
            "warning",
            _url("admin:backstage_operatoralert_changelist") + "?acknowledged__exact=0",
            permission=_can_view_operator_alerts,
            badge="shopman.backstage.admin.navigation.badge_operator_alerts",
            badge_variant="danger",
            badge_style="solid",
        )
    )
    return [
        _group("Operação ao vivo", "bolt", live_items, collapsible=False),
        _group("Pedidos e canais", "hub", [
            _item("Histórico de pedidos", "assignment", _url("admin:orderman_order_changelist"), permission=_can_manage_orders),
            _item("Sessões abertas", "shopping_bag", _url("admin:orderman_session_changelist") + "?state__exact=open", permission=_can_manage_orders),
            _item("Diretivas pendentes", "playlist_add_check", _url("admin:orderman_directive_changelist") + "?status__exact=queued", permission=_can_manage_orders),
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
        _group("Catálogo", "store", [
            _item("Produtos", "bakery_dining", _url("admin:offerman_product_changelist"), permission=_is_staff),
            _item("Coleções", "category", _url("admin:offerman_collection_changelist"), permission=_is_staff),
            _item("Listagens", "shoppingmode", _url("admin:offerman_listing_changelist"), permission=_is_staff),
        ]),
        _group("Clientes", "people", [
            _item("Clientes", "person_search", _url("admin:guestman_customer_changelist"), permission=_is_staff),
            _item("Endereços", "location_on", _url("admin:guestman_customeraddress_changelist"), permission=_is_staff),
            _item("Contas de fidelidade", "loyalty", _url("admin:customer_loyalty_loyaltyaccount_changelist"), permission=_is_staff),
        ]),
        # Tudo que é CONFIGURAÇÃO da loja num lugar óbvio e descobrível.
        # Colapsável para não competir com a operação do dia a dia.
        # Ordem por subtema (§3 do ADMIN-CONFIG-OMOTENASHI-PLAN): loja & canais →
        # preços & promoções → entrega → fidelidade/segmentação → conteúdo &
        # mensagens → estação/operação. A config de fidelidade vive dentro da
        # "Configuração da Loja" (fieldset), por isso não tem item próprio aqui.
        _group("Configurações", "settings", [
            _item("Loja & contato", "store", _url("admin:shop_shop_changelist"), permission=_is_staff),
            _item("Marca & aparência", "palette", _url("admin:shop_shopappearance_changelist"), permission=_is_staff),
            _item("Horários & operação", "schedule", _url("admin:shop_shopoperation_changelist"), permission=_is_staff),
            _item("Cardápio", "restaurant_menu", _url("admin:shop_shopmenu_changelist"), permission=_is_staff),
            _item("Pedidos & entrega", "local_shipping", _url("admin:shop_shopordering_changelist"), permission=_is_staff),
            _item("Fidelidade", "loyalty", _url("admin:shop_shoployalty_changelist"), permission=_is_staff),
            _item("PDV & alertas", "point_of_sale", _url("admin:shop_shoppos_changelist"), permission=_is_staff),
            _item("Produção", "manufacturing", _url("admin:shop_shopproduction_changelist"), permission=_is_staff),
            _item("Integrações", "extension", _url("admin:shop_shopintegrations_changelist"), permission=_is_staff),
            _item("Canais", "storefront", _url("admin:shop_channel_changelist"), permission=_is_staff),
            _item("Promoções", "sell", _url("admin:storefront_promotion_changelist"), permission=_is_staff),
            _item("Cupons", "confirmation_number", _url("admin:storefront_coupon_changelist"), permission=_is_staff),
            _item("Regras de preço", "price_change", _url("admin:shop_ruleconfig_changelist"), permission=_is_staff),
            _item("Faixas de distância", "straighten", _url("admin:storefront_deliverydistanceband_changelist"), permission=_is_staff),
            _item("Zonas de entrega", "pin_drop", _url("admin:storefront_deliveryzone_changelist"), permission=_is_staff),
            _item("Grupos de clientes", "groups", _url("admin:guestman_customergroup_changelist"), permission=_is_staff),
            _item("Copy Omotenashi", "format_quote", _url("admin_console_copy_catalog"), permission=_is_staff),
            _item("Templates de notificação", "mail", _url("admin:shop_notificationtemplate_changelist"), permission=_is_staff),
            _item("Estações KDS", "settings_input_component", _url("admin:backstage_kdsinstance_changelist"), permission=_can_operate_kds),
            _item("POS tabs", "confirmation_number", _url("admin:backstage_postab_changelist"), permission=_can_operate_pos),
        ]),
        _group("Auditoria e acesso", "admin_panel_settings", [
            _item("Fechamentos", "event_available", _url("admin:backstage_dayclosing_changelist"), permission=_can_close_day),
            _item("Pagamentos", "credit_card", _url("admin:payman_paymentintent_changelist"), permission=_can_manage_orders),
            _item("Turnos de Caixa", "payments", _url("admin:backstage_cashshift_changelist"), permission=_can_operate_pos),
            _item("Usuários", "person", _url("admin:auth_user_changelist"), permission=_is_superuser),
            _item("Grupos", "group", _url("admin:auth_group_changelist"), permission=_is_superuser),
        ]),
    ]


def badge_new_orders(request) -> str:
    from shopman.orderman.models import Order

    return str(Order.objects.filter(status=Order.Status.NEW).count())


def badge_started_work_orders(request) -> str:
    from shopman.craftsman.models import WorkOrder

    today = timezone.localdate()
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


# Request-oriented adapters over the canonical predicates. The sidebar speaks
# ``request``; the rules live once in shopman.backstage.permissions.
def _is_staff(request) -> bool:
    return permissions.is_staff(request.user)


def _is_superuser(request) -> bool:
    return permissions.is_superuser(request.user)


def _can_manage_orders(request) -> bool:
    return permissions.can_manage_orders(request.user)


def _can_access_production(request) -> bool:
    return permissions.can_access_production(request.user)


def _can_view_production_reports(request) -> bool:
    return permissions.can_view_production_reports(request.user)


def _can_close_day(request) -> bool:
    return permissions.can_close_day(request.user)


def _can_operate_pos(request) -> bool:
    return permissions.can_operate_pos(request.user)


def _can_operate_kds(request) -> bool:
    return permissions.can_operate_kds(request.user)


def _can_operate_production(request) -> bool:
    return permissions.can_operate_production(request.user)


def _can_view_operator_alerts(request) -> bool:
    return permissions.can_view_operator_alerts(request.user)
