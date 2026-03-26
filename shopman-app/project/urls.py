"""URL configuration for the Shopman project."""

import logging

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

logger = logging.getLogger(__name__)


def _include_optional(route: str, module: str):
    """Include a URL module, logging a warning if it fails to import."""
    try:
        return [path(route, include(module))]
    except ImportError:
        logger.warning("Optional URL module %s not found, skipping.", module)
        return []


urlpatterns = [
    path("admin/", admin.site.urls),
    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # Storefront (web channel)
    path("", include("channels.web.urls")),
]

# ── Core APIs ──────────────────────────────────────────────────────

urlpatterns += _include_optional("api/ordering/", "shopman.ordering.api.urls")
urlpatterns += _include_optional("api/offering/", "shopman.offering.api.urls")
urlpatterns += _include_optional("api/stocking/", "shopman.stocking.api.urls")
urlpatterns += _include_optional("api/crafting/", "shopman.crafting.api.urls")
urlpatterns += _include_optional("api/customers/", "shopman.customers.api.urls")
urlpatterns += _include_optional("api/auth/", "shopman.auth.api.urls")
urlpatterns += _include_optional("auth/", "shopman.auth.urls")
urlpatterns += _include_optional("api/payments/", "shopman.payments.api.urls")

# ── Channels APIs ──────────────────────────────────────────────

urlpatterns += _include_optional("api/webhooks/", "channels.webhook_urls")
urlpatterns += _include_optional("api/", "channels.api.urls")
