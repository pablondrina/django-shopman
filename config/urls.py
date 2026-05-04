"""URL configuration for the Shopman project."""

import logging

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from shopman.backstage.admin_console.closing import day_closing_console_view
from shopman.backstage.admin_console.kds import (
    kds_console_display_view,
    kds_console_index_view,
    kds_console_ticket_list_view,
    kds_expedition_action_view,
    kds_ticket_check_view,
    kds_ticket_done_view,
)
from shopman.backstage.admin_console.orders import (
    order_advance_view,
    order_confirm_view,
    order_detail_view,
    order_reject_view,
    orders_console_list_view,
    orders_console_view,
)
from shopman.backstage.admin_console.production import (
    production_commitments_view,
    production_console_bulk_create_view,
    production_console_view,
    production_dashboard_view,
    production_planning_view,
    production_reports_view,
    production_weighing_view,
)
from shopman.shop.views.health import HealthCheckView, ReadyCheckView

logger = logging.getLogger(__name__)

handler404 = "shopman.backstage.views.errors.custom_404"


def _include_optional(route: str, module: str):
    """Include a URL module, logging a warning if it fails to import."""
    try:
        return [path(route, include(module))]
    except ImportError:
        logger.warning("Optional URL module %s not found, skipping.", module)
        return []


urlpatterns = [
    # Health / readiness probes — público, sem auth, no topo para precedência.
    path("health/", HealthCheckView.as_view(), name="health"),
    path("ready/", ReadyCheckView.as_view(), name="ready"),
    path(
        "admin/operacao/pedidos/",
        admin.site.admin_view(orders_console_view),
        name="admin_console_orders",
    ),
    path(
        "admin/operacao/pedidos/lista/",
        admin.site.admin_view(orders_console_list_view),
        name="admin_console_orders_list",
    ),
    path(
        "admin/operacao/pedidos/<str:ref>/",
        admin.site.admin_view(order_detail_view),
        name="admin_console_order_detail",
    ),
    path(
        "admin/operacao/pedidos/<str:ref>/confirmar/",
        admin.site.admin_view(order_confirm_view),
        name="admin_console_order_confirm",
    ),
    path(
        "admin/operacao/pedidos/<str:ref>/avancar/",
        admin.site.admin_view(order_advance_view),
        name="admin_console_order_advance",
    ),
    path(
        "admin/operacao/pedidos/<str:ref>/rejeitar/",
        admin.site.admin_view(order_reject_view),
        name="admin_console_order_reject",
    ),
    path(
        "admin/operacao/producao/",
        admin.site.admin_view(production_console_view),
        name="admin_console_production",
    ),
    path(
        "admin/operacao/producao/criar/",
        admin.site.admin_view(production_console_bulk_create_view),
        name="admin_console_production_bulk_create",
    ),
    path(
        "admin/operacao/producao/planejamento/",
        admin.site.admin_view(production_planning_view),
        name="admin_console_production_planning",
    ),
    path(
        "admin/operacao/producao/painel/",
        admin.site.admin_view(production_dashboard_view),
        name="admin_console_production_dashboard",
    ),
    path(
        "admin/operacao/producao/relatorios/",
        admin.site.admin_view(production_reports_view),
        name="admin_console_production_reports",
    ),
    path(
        "admin/operacao/producao/pesagem/",
        admin.site.admin_view(production_weighing_view),
        name="admin_console_production_weighing",
    ),
    path(
        "admin/operacao/producao/<slug:wo_ref>/compromissos/",
        admin.site.admin_view(production_commitments_view),
        name="admin_console_production_work_order_commitments",
    ),
    path(
        "admin/operacao/kds/",
        admin.site.admin_view(kds_console_index_view),
        name="admin_console_kds",
    ),
    path(
        "admin/operacao/fechamento/",
        admin.site.admin_view(day_closing_console_view),
        name="admin_console_day_closing",
    ),
    path(
        "admin/operacao/kds/<slug:ref>/",
        admin.site.admin_view(kds_console_display_view),
        name="admin_console_kds_display",
    ),
    path(
        "admin/operacao/kds/<slug:ref>/tickets/",
        admin.site.admin_view(kds_console_ticket_list_view),
        name="admin_console_kds_tickets",
    ),
    path(
        "admin/operacao/kds/ticket/<int:pk>/conferir/",
        admin.site.admin_view(kds_ticket_check_view),
        name="admin_console_kds_ticket_check",
    ),
    path(
        "admin/operacao/kds/ticket/<int:pk>/pronto/",
        admin.site.admin_view(kds_ticket_done_view),
        name="admin_console_kds_ticket_done",
    ),
    path(
        "admin/operacao/kds/expedicao/<int:pk>/acao/",
        admin.site.admin_view(kds_expedition_action_view),
        name="admin_console_kds_expedition_action",
    ),
    path("admin/", admin.site.urls),
    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("", include("shopman.storefront.urls")),
    path("", include("shopman.backstage.urls")),
]

# ── Core APIs ──────────────────────────────────────────────────────

urlpatterns += _include_optional("api/orderman/", "shopman.orderman.api.urls")
urlpatterns += _include_optional("api/offerman/", "shopman.offerman.api.urls")
urlpatterns += _include_optional("api/stockman/", "shopman.stockman.api.urls")
urlpatterns += _include_optional("api/craftsman/", "shopman.craftsman.api.urls")
urlpatterns += _include_optional("api/customers/", "shopman.guestman.api.urls")
urlpatterns += _include_optional("api/auth/", "shopman.doorman.api.urls")
urlpatterns += _include_optional("auth/", "shopman.doorman.urls")
urlpatterns += _include_optional("api/payments/", "shopman.payman.api.urls")

urlpatterns += _include_optional("api/webhooks/", "shopman.shop.webhooks.urls")
urlpatterns += _include_optional("api/v1/", "shopman.storefront.api.urls")

# ── Media files (dev only) ────────────────────────────────────────

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
