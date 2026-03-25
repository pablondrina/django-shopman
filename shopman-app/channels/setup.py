"""
Channels setup — registro centralizado de TODOS handlers, backends, checks.

Chamado por ChannelsConfig.ready(). Substitui os registros que antes
viviam nos AppConfig.ready() dos mini-apps.
"""

from __future__ import annotations

import importlib
import logging

from django.conf import settings
from shopman.ordering import registry

logger = logging.getLogger(__name__)


def register_all() -> None:
    """Registra todos os componentes no registry do ordering."""
    _register_stock_handlers()
    _register_payment_handlers()
    _register_notification_handlers()
    _register_confirmation_handler()
    _register_customer_handler()
    _register_fiscal_handlers()
    _register_accounting_handler()
    _register_return_handler()
    _register_fulfillment_handler()
    _register_pricing_modifiers()
    _register_checks()
    _register_stock_validator()
    _register_stock_signals()


def _register_stock_handlers() -> None:
    from channels.handlers.stock import StockCommitHandler, StockHoldHandler

    backend = _load_stock_backend()
    if not backend:
        return

    for handler in [StockHoldHandler(backend=backend), StockCommitHandler(backend=backend)]:
        try:
            registry.register_directive_handler(handler)
        except ValueError:
            pass

    logger.info("channels.setup: Registered stock handlers with %s.", type(backend).__name__)


def _register_payment_handlers() -> None:
    from channels.handlers.payment import (
        PaymentCaptureHandler,
        PaymentRefundHandler,
        PixGenerateHandler,
        PixTimeoutHandler,
    )

    backend = _load_payment_backend()
    if not backend:
        return

    for handler in [
        PaymentCaptureHandler(backend=backend),
        PaymentRefundHandler(backend=backend),
        PixGenerateHandler(backend=backend),
        PixTimeoutHandler(backend=backend),
    ]:
        try:
            registry.register_directive_handler(handler)
        except ValueError:
            pass

    logger.info("channels.setup: Registered payment handlers with %s.", type(backend).__name__)


def _register_notification_handlers() -> None:
    from channels.backends.notification_console import ConsoleBackend
    from channels.handlers.notification import NotificationSendHandler
    from channels.notifications import register_backend

    try:
        registry.register_directive_handler(NotificationSendHandler())
    except ValueError:
        pass

    register_backend("console", ConsoleBackend())

    # Manychat if configured
    api_token = getattr(settings, "MANYCHAT_API_TOKEN", "")
    if api_token:
        try:
            from channels.backends.notification_manychat import ManychatBackend, ManychatConfig

            config = ManychatConfig(
                api_token=api_token,
                flow_map=getattr(settings, "MANYCHAT_FLOW_MAP", {}),
            )

            resolver = None
            try:
                from shopman.customers.contrib.manychat.resolver import ManychatSubscriberResolver

                resolver = ManychatSubscriberResolver.resolve
            except ImportError:
                pass

            register_backend("manychat", ManychatBackend(config=config, resolver=resolver))
        except Exception:
            logger.debug("channels.setup: Manychat backend not available", exc_info=True)


def _register_confirmation_handler() -> None:
    from channels.handlers.confirmation import ConfirmationTimeoutHandler

    try:
        registry.register_directive_handler(ConfirmationTimeoutHandler())
    except ValueError:
        pass


def _register_customer_handler() -> None:
    from channels.handlers.customer import CustomerEnsureHandler

    try:
        registry.register_directive_handler(CustomerEnsureHandler())
    except ValueError:
        pass


def _register_fiscal_handlers() -> None:
    from channels.handlers.fiscal import NFCeCancelHandler, NFCeEmitHandler

    backend = _load_fiscal_backend()
    if not backend:
        return

    for handler in [NFCeEmitHandler(backend=backend), NFCeCancelHandler(backend=backend)]:
        try:
            registry.register_directive_handler(handler)
        except ValueError:
            pass


def _register_accounting_handler() -> None:
    from channels.handlers.accounting import PurchaseToPayableHandler

    backend = _load_accounting_backend()
    if not backend:
        return

    try:
        registry.register_directive_handler(PurchaseToPayableHandler(backend=backend))
    except ValueError:
        pass


def _register_return_handler() -> None:
    from channels.handlers.returns import ReturnHandler

    stock_backend = _load_stock_backend()
    payment_backend = _load_payment_backend()
    fiscal_backend = _load_fiscal_backend()

    try:
        registry.register_directive_handler(
            ReturnHandler(
                stock_backend=stock_backend,
                payment_backend=payment_backend,
                fiscal_backend=fiscal_backend,
            )
        )
    except ValueError:
        pass


def _register_fulfillment_handler() -> None:
    from channels.handlers.fulfillment import FulfillmentCreateHandler, FulfillmentUpdateHandler

    for handler in [FulfillmentCreateHandler(), FulfillmentUpdateHandler()]:
        try:
            registry.register_directive_handler(handler)
        except ValueError:
            pass


def _register_pricing_modifiers() -> None:
    from channels.backends.pricing import CatalogPricingBackend
    from channels.handlers.pricing import ItemPricingModifier, SessionTotalModifier
    from shop.modifiers import (
        CouponModifier,
        D1DiscountModifier,
        EmployeeDiscountModifier,
        HappyHourModifier,
        PromotionModifier,
    )

    backend = CatalogPricingBackend()
    modifiers = [
        ItemPricingModifier(backend=backend),
        D1DiscountModifier(),
        PromotionModifier(),
        CouponModifier(),
        SessionTotalModifier(),
        EmployeeDiscountModifier(),
        HappyHourModifier(),
    ]
    for modifier in modifiers:
        try:
            registry.register_modifier(modifier)
        except ValueError:
            pass

    logger.info("channels.setup: Registered pricing modifiers.")


def _register_checks() -> None:
    from channels.handlers.stock import StockCheck

    try:
        registry.register_check(StockCheck())
    except (ValueError, AttributeError):
        pass


def _register_stock_validator() -> None:
    """Registra StockCheckValidator (valida checks no commit)."""
    try:

        class StockCheckValidator:
            code = "stock_check"
            stage = "commit"

            def validate(self, *, channel, session, ctx):
                required_checks = channel.config.get("required_checks_on_commit", [])
                if "stock" not in required_checks:
                    return
                if not session.items:
                    return
                checks = (session.data or {}).get("checks", {})
                stock_check = checks.get("stock")
                if not stock_check:
                    from shopman.ordering.exceptions import ValidationError

                    raise ValidationError(code="missing_stock_check", message="Stock check obrigatório para este canal")
                if stock_check.get("rev") != session.rev:
                    from shopman.ordering.exceptions import ValidationError

                    raise ValidationError(code="stale_stock_check", message="Stock check desatualizado")
                result = stock_check.get("result", {})
                holds = result.get("holds", [])
                if not holds:
                    from shopman.ordering.exceptions import ValidationError

                    raise ValidationError(code="no_holds", message="Nenhuma reserva de estoque encontrada")

        registry.register_validator(StockCheckValidator())
    except (ValueError, TypeError):
        pass


def _register_stock_signals() -> None:
    """Connect stock hold materialization + production voided signals."""
    try:
        from shopman.stocking.signals import holds_materialized

        from channels.handlers._stock_receivers import on_holds_materialized

        holds_materialized.connect(on_holds_materialized, weak=False)
        logger.info("channels.setup: Connected holds_materialized receiver.")
    except ImportError:
        logger.debug("channels.setup: stocking signals not available")

    try:
        from shopman.crafting.signals import production_changed

        from channels.handlers._stock_receivers import on_production_voided

        production_changed.connect(on_production_voided, weak=False)
        logger.info("channels.setup: Connected production_changed receiver (voided).")
    except ImportError:
        logger.debug("channels.setup: crafting signals not available")


# ── Backend loaders ──


def _load_stock_backend():
    backend_path = getattr(settings, "SHOPMAN_STOCK_BACKEND", None)
    if backend_path:
        return _import_class(backend_path)()

    try:
        from shopman.stocking import stock  # noqa: F401

        from channels.backends.stock import StockingBackend

        def _product_resolver(sku: str):
            from shopman.offering.models import Product

            return Product.objects.get(sku=sku)

        return StockingBackend(product_resolver=_product_resolver)
    except ImportError:
        pass

    from channels.backends.stock import NoopStockBackend

    return NoopStockBackend()


def _load_payment_backend():
    backend_path = getattr(settings, "SHOPMAN_PAYMENT_BACKEND", "channels.backends.payment_mock.MockPaymentBackend")
    try:
        return _import_class(backend_path)()
    except Exception:
        logger.warning("channels.setup: Could not load payment backend", exc_info=True)
        return None


def _load_fiscal_backend():
    backend_path = getattr(settings, "SHOPMAN_FISCAL_BACKEND", None)
    if not backend_path:
        try:
            from channels.backends.fiscal_mock import MockFiscalBackend

            return MockFiscalBackend()
        except ImportError:
            return None
    try:
        return _import_class(backend_path)()
    except Exception:
        logger.warning("channels.setup: Could not load fiscal backend", exc_info=True)
        return None


def _load_accounting_backend():
    backend_path = getattr(settings, "SHOPMAN_ACCOUNTING_BACKEND", None)
    if not backend_path:
        try:
            from channels.backends.accounting_mock import MockAccountingBackend

            return MockAccountingBackend()
        except ImportError:
            return None
    try:
        return _import_class(backend_path)()
    except Exception:
        logger.warning("channels.setup: Could not load accounting backend", exc_info=True)
        return None


def _import_class(dotted_path: str):
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)
