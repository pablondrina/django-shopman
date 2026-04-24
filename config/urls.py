"""URL configuration for the Shopman project."""

import logging

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

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
