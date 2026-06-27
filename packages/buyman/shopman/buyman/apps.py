from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BuymanConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.buyman"
    label = "buyman"
    verbose_name = _("Compras")
