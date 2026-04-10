from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PaymanConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shopman.payman"
    label = "payman"
    verbose_name = _("Pagamentos")
