"""URL configuration for the Shopman project."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/webhooks/", include("shopman.payment.urls")),
    path("api/accounting/", include("shopman.accounting.api.urls")),
    path("webhook/", include("shopman.webhook.urls")),
]
