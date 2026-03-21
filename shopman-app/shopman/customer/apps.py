"""
Django AppConfig para customer.

Registra:
- CustomerEnsureHandler no registry de diretivas
"""

from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CustomerConfig(AppConfig):
    name = "shopman.customer"
    label = "shopman_customer"
    verbose_name = _("Clientes")

    def ready(self):
        from shopman.ordering.registry import register_directive_handler

        from .handlers import CustomerEnsureHandler

        try:
            register_directive_handler(CustomerEnsureHandler())
        except ValueError:
            pass  # Already registered (reload)
