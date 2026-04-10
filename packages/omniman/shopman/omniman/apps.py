from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OmnimanConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.omniman"
    label = "omniman"
    verbose_name = _("Pedidos")

    def ready(self):
        from shopman.omniman import dispatch  # noqa: F401 — connect post_save signal
