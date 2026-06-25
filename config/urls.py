"""URL configuration for the Shopman project."""

import logging

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from shopman.backstage.admin_console.closing import day_closing_console_view
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
    # Pedidos migraram p/ o app Nuxt dedicado (Gestor — surfaces/orders-uithing-nuxt)
    # via api/v1/backstage/orders/*; o console Admin de pedidos foi removido
    # (OPERATOR-APPS-PLAN Fase 2).
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
        "admin/operacao/fechamento/",
        admin.site.admin_view(day_closing_console_view),
        name="admin_console_day_closing",
    ),
    path("admin/", admin.site.urls),
    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
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
urlpatterns += _include_optional("api/v1/backstage/", "shopman.backstage.api.urls")

# ── Media files (dev only) ────────────────────────────────────────

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
