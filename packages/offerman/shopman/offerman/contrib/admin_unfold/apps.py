from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OffermanAdminUnfoldConfig(AppConfig):
    name = "shopman.offerman.contrib.admin_unfold"
    label = "offerman_admin_unfold"
    verbose_name = _("Admin (Unfold)")
