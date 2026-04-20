"""Django AppConfig for the Shopman storefront (customer-facing surface)."""

from __future__ import annotations

from django.apps import AppConfig


class StorefrontConfig(AppConfig):
    name = "shopman.storefront"
    label = "storefront"
    verbose_name = "Storefront"
    default_auto_field = "django.db.models.BigAutoField"
