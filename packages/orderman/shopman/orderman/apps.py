from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OrdermanConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.orderman"
    label = "orderman"
    verbose_name = _("Pedidos")

    def ready(self):
        from shopman.orderman import dispatch  # noqa: F401 — connect post_save signal
