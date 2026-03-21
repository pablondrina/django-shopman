from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CraftsmanAdminUnfoldConfig(AppConfig):
    name = "shopman.crafting.contrib.admin_unfold"
    label = "crafting_admin_unfold"
    verbose_name = _("Admin (Unfold)")
