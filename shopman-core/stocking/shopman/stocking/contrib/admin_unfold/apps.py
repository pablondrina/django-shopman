from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StockmanAdminUnfoldConfig(AppConfig):
    name = "shopman.stocking.contrib.admin_unfold"
    label = "stocking_admin_unfold"
    verbose_name = _("Admin (Unfold)")
