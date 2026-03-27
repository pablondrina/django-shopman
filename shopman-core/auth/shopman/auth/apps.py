import logging

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger("shopman.auth")


class AuthConfig(AppConfig):
    name = "shopman.auth"
    label = "shopman_auth"
    verbose_name = _("Gestão do Acesso")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Import signals to register handlers
        from . import signals  # noqa: F401

        # Enforce API key in production
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        from .conf import get_auth_settings

        if not settings.DEBUG:
            ds = get_auth_settings()

            if not ds.ACCESS_LINK_API_KEY:
                raise ImproperlyConfigured(
                    "AUTH['ACCESS_LINK_API_KEY'] must be set in production. "
                    "The access link creation endpoint would be unauthenticated. "
                    "Set a strong random key, or if you intentionally don't use "
                    "access link creation, set AUTH['ACCESS_LINK_API_KEY'] "
                    "to any non-empty value."
                )

            # ConsoleSender must not be used in production
            if ds.MESSAGE_SENDER_CLASS == "shopman.auth.senders.ConsoleSender":
                raise ImproperlyConfigured(
                    "AUTH['MESSAGE_SENDER_CLASS'] is set to ConsoleSender. "
                    "This prints OTP codes to stdout and must NOT be used in "
                    "production. Configure a real sender (WhatsApp, SMS, Email) "
                    "or set AUTH['DELIVERY_CHAIN']."
                )

            # DEFAULT_DOMAIN must not be localhost
            if "localhost" in ds.DEFAULT_DOMAIN or "127.0.0.1" in ds.DEFAULT_DOMAIN:
                raise ImproperlyConfigured(
                    f"AUTH['DEFAULT_DOMAIN'] is '{ds.DEFAULT_DOMAIN}'. "
                    "Set it to your production domain (e.g. 'shop.example.com')."
                )
