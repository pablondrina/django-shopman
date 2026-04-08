"""URL configuration for the Shopman project."""

import logging

from django.conf import settings
from django.conf.urls.static import static
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
    path("", include("shopman.web.urls")),
]

# ── Core APIs ──────────────────────────────────────────────────────

urlpatterns += _include_optional("api/ordering/", "shopman.omniman.api.urls")
urlpatterns += _include_optional("api/offering/", "shopman.offerman.api.urls")
urlpatterns += _include_optional("api/stocking/", "shopman.stockman.api.urls")
urlpatterns += _include_optional("api/crafting/", "shopman.craftsman.api.urls")
urlpatterns += _include_optional("api/customers/", "shopman.guestman.api.urls")
urlpatterns += _include_optional("api/auth/", "shopman.doorman.api.urls")
urlpatterns += _include_optional("auth/", "shopman.doorman.urls")
urlpatterns += _include_optional("api/payments/", "shopman.payman.api.urls")

urlpatterns += _include_optional("api/webhooks/", "shopman.webhooks.urls")
urlpatterns += _include_optional("api/", "shopman.api.urls")

# ── Media files (dev only) ────────────────────────────────────────

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
