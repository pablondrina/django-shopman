"""
Django AppConfig for shopman.refs.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RefsConfig(AppConfig):
    name = "shopman.refs"
    label = "refs"
    verbose_name = _("Referencias")
    default_auto_field = "django.db.models.BigAutoField"
