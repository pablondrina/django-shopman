"""Backstage extensions to ShopAdmin — production + closing admin URLs.

Re-registers Shop with the backstage-specific URL patterns so that
admin:shop_production and admin:shop_closing resolve correctly.
"""

from __future__ import annotations

from django.contrib import admin
from django.urls import path

from shopman.shop.admin.shop import ShopAdmin
from shopman.shop.models import Shop

from shopman.backstage.views.closing import closing_view
from shopman.backstage.views.production import production_view, production_void_view

admin.site.unregister(Shop)


@admin.register(Shop)
class ShopAdminWithBackstageURLs(ShopAdmin):
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "production/",
                self.admin_site.admin_view(
                    lambda request: production_view(request, self.admin_site)
                ),
                name="shop_production",
            ),
            path(
                "production/void/",
                self.admin_site.admin_view(
                    lambda request: production_void_view(request, self.admin_site)
                ),
                name="shop_production_void",
            ),
            path(
                "closing/",
                self.admin_site.admin_view(
                    lambda request: closing_view(request, self.admin_site)
                ),
                name="shop_closing",
            ),
        ]
        return custom + urls
