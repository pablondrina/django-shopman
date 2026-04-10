from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DoormanAdminUnfoldConfig(AppConfig):
    name = "shopman.doorman.contrib.admin_unfold"
    label = "doorman_admin_unfold"
    verbose_name = _("Doorman Admin (Unfold)")
