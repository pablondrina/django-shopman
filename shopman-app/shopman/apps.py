"""Django AppConfig for the Shopman orchestrator."""

from django.apps import AppConfig


class ShopmanConfig(AppConfig):
    name = "shopman"
    verbose_name = "Shopman"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        pass  # Handler registration will be added in WP-6+
