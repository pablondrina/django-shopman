from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CraftsmanAdminUnfoldConfig(AppConfig):
    name = "shopman.craftsman.contrib.admin_unfold"
    label = "craftsman_admin_unfold"
    verbose_name = _("Admin (Unfold)")
