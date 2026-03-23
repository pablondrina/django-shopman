"""
Django AppConfig para stock.

Registra:
- StockHoldHandler (topic: stock.hold)
- StockCommitHandler (topic: stock.commit)

O backend é resolvido automaticamente:
1. Se SHOPMAN_STOCK_BACKEND está definido em settings, usa esse dotted path.
2. Se Stockman está instalado, usa StockmanBackend com product_resolver do Offerman.
3. Senão, usa NoopStockBackend.
"""

from __future__ import annotations

import importlib
import logging

from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


def _load_backend():
    """Instancia o StockBackend a partir do setting ou auto-detect."""
    # 1. Explicit setting
    backend_path = getattr(settings, "SHOPMAN_STOCK_BACKEND", None)
    if backend_path:
        module_path, class_name = backend_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls()

    # 2. Auto-detect Stockman
    try:
        from shopman.stocking import stock  # noqa: F401

        from .adapters.stockman import StockmanBackend

        def _product_resolver(sku: str):
            from shopman.offering.models import Product

            return Product.objects.get(sku=sku)

        return StockmanBackend(product_resolver=_product_resolver)
    except ImportError:
        pass

    # 3. Fallback to Noop
    from .adapters.noop import NoopStockBackend

    return NoopStockBackend()


class StockConfig(AppConfig):
    name = "shopman.stock"
    label = "shopman_stock"
    verbose_name = _("Estoque")

    def ready(self):
        from shopman.ordering.registry import register_directive_handler, register_validator

        from .handlers import StockCommitHandler, StockHoldHandler
        from .validator import StockCheckValidator

        try:
            backend = _load_backend()
        except Exception:
            logger.warning(
                "StockConfig: Could not load stock backend. "
                "Stock handlers will NOT be registered.",
                exc_info=True,
            )
            return

        handlers = [
            StockHoldHandler(backend=backend),
            StockCommitHandler(backend=backend),
        ]

        for handler in handlers:
            try:
                register_directive_handler(handler)
            except ValueError:
                pass  # Already registered (reload)

        # Register commit validator
        try:
            register_validator(StockCheckValidator())
        except ValueError:
            pass  # Already registered (reload)

        logger.info(
            "StockConfig: Registered %d stock handlers with %s.",
            len(handlers),
            type(backend).__name__,
        )

        # Connect signal receivers (holds_materialized from Stockman)
        try:
            from .receivers import connect_signals
            connect_signals()
        except Exception:
            logger.debug(
                "StockConfig: Could not connect stock signal receivers.",
                exc_info=True,
            )
