import logging

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger("gating")


class GatingConfig(AppConfig):
    name = "shopman.gating"
    label = "gating"
    verbose_name = _("Gestão do Acesso")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Import signals to register handlers
        from . import signals  # noqa: F401

        # Enforce API key in production
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        from .conf import get_gating_settings

        if not settings.DEBUG:
            ds = get_gating_settings()
            if not ds.BRIDGE_TOKEN_API_KEY:
                raise ImproperlyConfigured(
                    "GATING['BRIDGE_TOKEN_API_KEY'] must be set in production. "
                    "The bridge token creation endpoint would be unauthenticated. "
                    "Set a strong random key, or if you intentionally don't use "
                    "bridge token creation, set GATING['BRIDGE_TOKEN_API_KEY'] "
                    "to any non-empty value."
                )
