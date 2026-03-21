from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OfferingAdminUnfoldConfig(AppConfig):
    name = "shopman.offering.contrib.admin_unfold"
    label = "offering_admin_unfold"
    verbose_name = _("Admin (Unfold)")
