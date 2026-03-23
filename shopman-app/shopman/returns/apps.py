"""
Django AppConfig para shopman.returns.

Registra o handler de diretiva para devoluções:
- ReturnHandler (topic: return.process)

Os backends (stock, payment, fiscal) são resolvidos via settings:
- SHOPMAN_STOCK_BACKEND
- SHOPMAN_PAYMENT_BACKEND
- SHOPMAN_FISCAL_BACKEND
"""

from __future__ import annotations

import importlib
import logging

from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


def _load_backend(setting_name: str, default_path: str | None = None):
    """Instancia um backend a partir de um setting."""
    backend_path = getattr(settings, setting_name, default_path)
    if not backend_path:
        return None
    module_path, class_name = backend_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()


class ReturnsConfig(AppConfig):
    name = "shopman.returns"
    label = "shopman_returns"
    verbose_name = _("Devoluções")

    def ready(self):
        from shopman.ordering.registry import register_directive_handler

        from .handlers import ReturnHandler

        try:
            stock_backend = _load_backend(
                "SHOPMAN_STOCK_BACKEND",
                "shopman.inventory.adapters.noop.NoopStockBackend",
            )
            payment_backend = _load_backend(
                "SHOPMAN_PAYMENT_BACKEND",
                "shopman.payment.adapters.mock.MockPaymentBackend",
            )
            fiscal_backend = _load_backend("SHOPMAN_FISCAL_BACKEND")
        except Exception:
            logger.warning(
                "ReturnsConfig: Could not load backends. ReturnHandler will NOT be registered.",
                exc_info=True,
            )
            return

        handler = ReturnHandler(
            stock_backend=stock_backend,
            payment_backend=payment_backend,
            fiscal_backend=fiscal_backend,
        )

        try:
            register_directive_handler(handler)
        except ValueError:
            pass  # Already registered (reload)

        logger.info("ReturnsConfig: Registered ReturnHandler.")
