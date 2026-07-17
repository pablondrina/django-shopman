"""URL configuration for the Shopman project."""

import logging

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from shopman.backstage.admin_console.production import (
    production_commitments_view,
    production_console_view,
    production_dashboard_view,
    production_planning_view,
    production_reports_view,
    production_weighing_view,
)
from shopman.backstage.views.two_factor import admin_2fa_verify
from shopman.shop.views.health import HealthCheckView, ReadyCheckView

logger = logging.getLogger(__name__)

# No custom handler404: the legacy operator shell (gestor/base.html + gestor/404.html)
# was retired with the production app cutover (OPERATOR-APPS-PLAN Fase 4). Operator
# surfaces are dedicated Nuxt apps; Django serves the API + Admin (which has its own
# 404). Django's default handler covers the rest.


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
    # Pedidos migraram p/ o app Nuxt dedicado (Gestor — surfaces/orders-nuxt)
    # via api/v1/backstage/orders/*; o console Admin de pedidos foi removido
    # (OPERATOR-APPS-PLAN Fase 2).
    path(
        "admin/operacao/producao/",
        admin.site.admin_view(production_console_view),
        name="admin_console_production",
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
    path("admin/2fa/verify/", admin_2fa_verify, name="admin_2fa_verify"),
    path("admin/", admin.site.urls),
    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("", include("shopman.backstage.urls")),
]

# ── Core APIs ──────────────────────────────────────────────────────
#
# Os ViewSets de CRUD dos pacotes do kernel (orderman, offerman, stockman,
# craftsman, guestman, payman) NÃO são montados no deployment. Eles herdam o
# default DRF `IsAuthenticated`, e clientes do storefront viram usuários Django
# autenticados (login OTP chama `login()`), então expô-los deixaria qualquer
# cliente logado ler/mutar dados do kernel — sessões e comandas do POS, base de
# PII, ledger de estoque, BOM (segredo de negócio), payment intents. Nenhuma
# superfície os consome: os apps Nuxt entram por `api/v1/` (storefront) e
# `api/v1/backstage/` (projections gateadas por permissão). Guardrail que trava
# a re-introdução: shopman/shop/tests/test_api_perimeter.py.
#
# Se um desses ganhar consumidor real, ele volta COM permissão explícita
# (IsAdminUser/DjangoModelPermissions) e o guardrail é atualizado deliberadamente.

urlpatterns += _include_optional("api/auth/", "shopman.doorman.api.urls")
urlpatterns += _include_optional("auth/", "shopman.doorman.urls")

urlpatterns += _include_optional("api/webhooks/", "shopman.shop.webhooks.urls")
# ManyChat inbound webhook (subscriber sync). HMAC + replay gated; without
# MANYCHAT_WEBHOOK_SECRET it fails CLOSED outside DEBUG (rejects unsigned payloads);
# only local dev (DEBUG) skips the signature. The conversational ORDER flow
# (intent/confirm endpoints) is owned by MANYCHAT-CONVERSACIONAL-PLAN, not this route.
urlpatterns += _include_optional(
    "api/webhooks/manychat/", "shopman.guestman.contrib.manychat.urls"
)
urlpatterns += _include_optional("api/v1/", "shopman.storefront.api.urls")
urlpatterns += _include_optional("api/v1/backstage/", "shopman.backstage.api.urls")

# Menuboard — superfície display pública (quadro-negro numa TV), tempo real via SSE.
urlpatterns += _include_optional("", "shopman.shop.menuboard_urls")

# Fiscal — DANFE NFC-e (cupom de operador, imprimível). Gated a staff na view.
urlpatterns += _include_optional("", "shopman.shop.fiscal_urls")

# ── Media files (dev only) ────────────────────────────────────────

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
