from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StockmanAdminUnfoldConfig(AppConfig):
    name = "shopman.stockman.contrib.admin_unfold"
    label = "stockman_admin_unfold"
    verbose_name = _("Admin (Unfold)")
