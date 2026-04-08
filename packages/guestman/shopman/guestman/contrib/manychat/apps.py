"""Manychat app config."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ManychatConfig(AppConfig):
    name = "shopman.guestman.contrib.manychat"
    label = "guestman_manychat"
    verbose_name = _("ManyChat")
