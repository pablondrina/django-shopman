"""
Django AppConfig para identification (orquestrador de identidade de cliente).

Registra:
- CustomerEnsureHandler no registry de diretivas
"""

from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class IdentificationConfig(AppConfig):
    name = "shopman.identification"
    label = "shopman_identification"
    verbose_name = _("Identificação")

    def ready(self):
        from shopman.ordering.registry import register_directive_handler

        from .handlers import CustomerEnsureHandler

        try:
            register_directive_handler(CustomerEnsureHandler())
        except ValueError:
            pass  # Already registered (reload)
