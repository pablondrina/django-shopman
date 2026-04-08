from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CustomersAdminUnfoldConfig(AppConfig):
    name = "shopman.guestman.contrib.admin_unfold"
    label = "guestman_admin_unfold"
    verbose_name = _("Admin (Unfold)")
