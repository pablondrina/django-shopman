from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StockingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.stocking"
    label = "stocking"
    verbose_name = _("Gestão de Estoque")
