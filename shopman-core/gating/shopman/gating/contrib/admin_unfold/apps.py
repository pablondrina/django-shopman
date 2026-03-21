from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class GatingAdminUnfoldConfig(AppConfig):
    name = "shopman.gating.contrib.admin_unfold"
    label = "gating_admin_unfold"
    verbose_name = _("Gating Admin (Unfold)")
