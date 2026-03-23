"""
Django AppConfig para fiscal.

Registra:
- NFCeEmitHandler   (topic: fiscal.emit_nfce)
- NFCeCancelHandler (topic: fiscal.cancel_nfce)

O backend e resolvido automaticamente:
1. Se SHOPMAN_FISCAL_BACKEND esta definido em settings, usa esse dotted path.
2. Senao, usa MockFiscalBackend.
"""

from __future__ import annotations

import importlib
import logging

from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

DEFAULT_FISCAL_BACKEND = "shopman.fiscal.backends.mock.MockFiscalBackend"


def _load_backend():
    """Instancia o FiscalBackend a partir do setting."""
    backend_path = getattr(
        settings, "SHOPMAN_FISCAL_BACKEND", DEFAULT_FISCAL_BACKEND,
    )
    module_path, class_name = backend_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()


class FiscalConfig(AppConfig):
    name = "shopman.fiscal"
    label = "shopman_fiscal"
    verbose_name = _("Fiscal")

    def ready(self):
        from shopman.ordering.registry import register_directive_handler

        from .handlers import NFCeCancelHandler, NFCeEmitHandler

        try:
            backend = _load_backend()
        except Exception:
            logger.warning(
                "FiscalConfig: Could not load fiscal backend. "
                "Fiscal handlers will NOT be registered.",
                exc_info=True,
            )
            return

        handlers = [
            NFCeEmitHandler(backend=backend),
            NFCeCancelHandler(backend=backend),
        ]

        for handler in handlers:
            try:
                register_directive_handler(handler)
            except ValueError:
                pass  # Already registered (reload)

        logger.info(
            "FiscalConfig: Registered %d fiscal handlers with %s.",
            len(handlers),
            type(backend).__name__,
        )
