from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AttendingAdminUnfoldConfig(AppConfig):
    name = "shopman.attending.contrib.admin_unfold"
    label = "attending_admin_unfold"
    verbose_name = _("Admin (Unfold)")
