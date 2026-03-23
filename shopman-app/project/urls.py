"""URL configuration for the Shopman project."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # Storefront (web channel)
    path("", include("channels.web.urls")),
]

# ── Core APIs ──────────────────────────────────────────────────────

try:
    urlpatterns += [path("api/ordering/", include("shopman.ordering.api.urls"))]
except ImportError:
    pass

try:
    urlpatterns += [path("api/offering/", include("shopman.offering.api.urls"))]
except ImportError:
    pass

try:
    urlpatterns += [path("api/stocking/", include("shopman.stocking.api.urls"))]
except ImportError:
    pass

try:
    urlpatterns += [path("api/crafting/", include("shopman.crafting.api.urls"))]
except ImportError:
    pass

try:
    urlpatterns += [path("api/attending/", include("shopman.attending.api.urls"))]
except ImportError:
    pass

# ── Orchestrator APIs ──────────────────────────────────────────────

try:
    urlpatterns += [path("api/webhooks/", include("shopman.payment.urls"))]
except ImportError:
    pass

try:
    urlpatterns += [path("api/accounting/", include("shopman.accounting.api.urls"))]
except ImportError:
    pass

try:
    urlpatterns += [path("webhook/", include("shopman.webhook.urls"))]
except ImportError:
    pass
