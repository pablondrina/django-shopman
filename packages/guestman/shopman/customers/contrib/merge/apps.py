"""Merge app config."""

from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MergeConfig(AppConfig):
    name = "shopman.customers.contrib.merge"
    label = "customers_merge"
    verbose_name = _("Merge de Clientes")
