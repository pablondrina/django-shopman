from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BuymanAdminUnfoldConfig(AppConfig):
    name = "shopman.buyman.contrib.admin_unfold"
    label = "buyman_admin_unfold"
    verbose_name = _("Admin (Unfold)")
