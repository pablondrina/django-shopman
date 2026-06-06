from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PaymanAdminUnfoldConfig(AppConfig):
    name = "shopman.payman.contrib.admin_unfold"
    label = "payman_admin_unfold"
    verbose_name = _("Admin (Unfold)")
