from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CraftsmanConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.craftsman"
    label = "craftsman"
    verbose_name = _("Produção")
