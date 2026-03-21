"""Manychat app config."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ManychatConfig(AppConfig):
    name = "shopman.attending.contrib.manychat"
    label = "attending_manychat"
    verbose_name = _("ManyChat")
