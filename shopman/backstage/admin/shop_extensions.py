"""Backstage ShopAdmin registration.

Operator workflows live under the ``backstage:`` namespace. ShopAdmin is
re-registered here only to preserve the existing admin customization point.
"""

from __future__ import annotations

from django.contrib import admin

from shopman.shop.admin.shop import ShopAdmin
from shopman.shop.models import Shop

admin.site.unregister(Shop)


@admin.register(Shop)
class ShopAdminWithBackstageURLs(ShopAdmin):
    pass
