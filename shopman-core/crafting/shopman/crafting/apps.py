from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CraftingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.crafting"
    label = "crafting"
    verbose_name = _("Produção")
