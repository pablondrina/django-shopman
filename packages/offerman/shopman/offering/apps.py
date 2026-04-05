from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OfferingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.offering"
    label = "offering"
    verbose_name = _("Catálogo de Produtos")
