"""Django AppConfig for the Shopman storefront (customer-facing surface)."""

from __future__ import annotations

from django.apps import AppConfig


class StorefrontConfig(AppConfig):
    name = "shopman.storefront"
    label = "storefront"
    verbose_name = "Storefront"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Stock-back alerts: react to Stockman Move arrivals to notify waiters.
        from django.db.models.signals import post_save
        from shopman.stockman.models import Move

        from shopman.storefront.handlers import on_move_for_stock_alerts

        post_save.connect(
            on_move_for_stock_alerts,
            sender=Move,
            dispatch_uid="storefront.stock_alerts.on_move",
            weak=False,
        )
