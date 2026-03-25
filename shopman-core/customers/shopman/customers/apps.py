from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CustomersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.customers"
    label = "customers"
    verbose_name = _("Gestão de Clientes")
