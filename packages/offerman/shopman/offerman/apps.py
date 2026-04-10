from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OffermanConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.offerman"
    label = "offerman"
    verbose_name = _("Catálogo de Produtos")
