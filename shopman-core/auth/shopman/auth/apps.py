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
            if not ds.BRIDGE_TOKEN_API_KEY:
                raise ImproperlyConfigured(
                    "AUTH['BRIDGE_TOKEN_API_KEY'] must be set in production. "
                    "The bridge token creation endpoint would be unauthenticated. "
                    "Set a strong random key, or if you intentionally don't use "
                    "bridge token creation, set AUTH['BRIDGE_TOKEN_API_KEY'] "
                    "to any non-empty value."
                )
