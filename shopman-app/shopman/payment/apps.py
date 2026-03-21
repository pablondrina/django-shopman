"""
Django AppConfig para payment.

Registra os handlers de diretiva para pagamento:
- PaymentCaptureHandler  (topic: payment.capture)
- PaymentRefundHandler   (topic: payment.refund)
- PixGenerateHandler     (topic: pix.generate)
- PixTimeoutHandler      (topic: pix.timeout)

O backend é resolvido via setting SHOPMAN_PAYMENT_BACKEND (dotted path).
Default: "shopman.payment.adapters.mock.MockPaymentBackend"
"""

from __future__ import annotations

import importlib
import logging

from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

DEFAULT_PAYMENT_BACKEND = "shopman.payment.adapters.mock.MockPaymentBackend"


def _load_backend():
    """Instancia o PaymentBackend a partir do setting."""
    backend_path = getattr(settings, "SHOPMAN_PAYMENT_BACKEND", DEFAULT_PAYMENT_BACKEND)
    module_path, class_name = backend_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()


class PaymentConfig(AppConfig):
    name = "shopman.payment"
    label = "shopman_payment"
    verbose_name = _("Pagamentos")

    def ready(self):
        from shopman.ordering.registry import register_directive_handler

        from .handlers import (
            PaymentCaptureHandler,
            PaymentRefundHandler,
            PixGenerateHandler,
            PixTimeoutHandler,
        )

        try:
            backend = _load_backend()
        except Exception:
            logger.warning(
                "PaymentConfig: Could not load payment backend from setting "
                "SHOPMAN_PAYMENT_BACKEND. Payment handlers will NOT be registered.",
                exc_info=True,
            )
            return

        handlers = [
            PaymentCaptureHandler(backend=backend),
            PaymentRefundHandler(backend=backend),
            PixGenerateHandler(backend=backend),
            PixTimeoutHandler(backend=backend),
        ]

        for handler in handlers:
            try:
                register_directive_handler(handler)
            except ValueError:
                pass  # Já registrado (reload)

        logger.info(
            "PaymentConfig: Registered %d payment handlers with %s.",
            len(handlers),
            type(backend).__name__,
        )
