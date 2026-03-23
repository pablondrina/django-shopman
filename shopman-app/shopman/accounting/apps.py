"""
Django AppConfig para accounting.

Registra:
- PurchaseToPayableHandler (topic: accounting.create_payable)

O backend e resolvido automaticamente:
1. Se SHOPMAN_ACCOUNTING_BACKEND esta definido em settings, usa esse dotted path.
2. Senao, usa MockAccountingBackend.
"""

from __future__ import annotations

import importlib
import logging

from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

DEFAULT_ACCOUNTING_BACKEND = "shopman.accounting.backends.mock.MockAccountingBackend"


def _load_backend():
    """Instancia o AccountingBackend a partir do setting."""
    backend_path = getattr(
        settings, "SHOPMAN_ACCOUNTING_BACKEND", DEFAULT_ACCOUNTING_BACKEND,
    )
    module_path, class_name = backend_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()


class AccountingConfig(AppConfig):
    name = "shopman.accounting"
    label = "shopman_accounting"
    verbose_name = _("Contabilidade")

    def ready(self):
        from shopman.ordering.registry import register_directive_handler

        from .handlers import PurchaseToPayableHandler

        try:
            backend = _load_backend()
        except Exception:
            logger.warning(
                "AccountingConfig: Could not load accounting backend. "
                "Accounting handlers will NOT be registered.",
                exc_info=True,
            )
            return

        try:
            register_directive_handler(PurchaseToPayableHandler(backend=backend))
        except ValueError:
            pass  # Already registered (reload)

        logger.info(
            "AccountingConfig: Registered PurchaseToPayableHandler with %s.",
            type(backend).__name__,
        )
