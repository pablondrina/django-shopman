from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OrderingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.ordering"
    label = "ordering"
    verbose_name = _("Pedidos")

    def ready(self):
        from shopman.ordering import dispatch  # noqa: F401 — connect post_save signal
