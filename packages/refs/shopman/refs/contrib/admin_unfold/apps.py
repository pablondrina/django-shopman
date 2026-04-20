from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RefsAdminUnfoldConfig(AppConfig):
    name = "shopman.refs.contrib.admin_unfold"
    label = "refs_admin_unfold"
    verbose_name = _("Admin (Unfold)")
