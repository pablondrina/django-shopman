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
    _register_loyalty_handler()
    _register_checkout_defaults_handler()
    _register_pricing_modifiers()
    _register_checks()
    _register_stock_validator()
    _register_stock_signals()


def _register_stock_handlers() -> None:
    from shopman.handlers.stock import StockCommitHandler, StockHoldHandler

    backend = _load_stock_backend()
    if not backend:
        return

    for handler in [StockHoldHandler(backend=backend), StockCommitHandler(backend=backend)]:
        try:
            registry.register_directive_handler(handler)
        except ValueError:
            pass

    logger.info("shopman.setup: Registered stock handlers with %s.", type(backend).__name__)


def _register_payment_handlers() -> None:
    from shopman.handlers.payment import (
        CardCreateHandler,
        PaymentCaptureHandler,
        PaymentRefundHandler,
        PaymentTimeoutHandler,
        PixGenerateHandler,
        PixTimeoutHandler,
    )

    backend = _load_payment_backend()
    if not backend:
        return

    for handler in [
        CardCreateHandler(backend=backend),
        PaymentCaptureHandler(backend=backend),
        PaymentRefundHandler(backend=backend),
        PaymentTimeoutHandler(backend=backend),
        PixGenerateHandler(backend=backend),
        PixTimeoutHandler(backend=backend),
    ]:
        try:
            registry.register_directive_handler(handler)
        except ValueError:
            pass

    logger.info("shopman.setup: Registered payment handlers with %s.", type(backend).__name__)


def _register_notification_handlers() -> None:
    from shopman.backends.notification_console import ConsoleBackend
    from shopman.handlers.notification import NotificationSendHandler
    from shopman.notifications import register_backend

    try:
        registry.register_directive_handler(NotificationSendHandler())
    except ValueError:
        pass

    register_backend("console", ConsoleBackend())

    # Email backend
    from shopman.backends.notification_email import EmailBackend

    register_backend("email", EmailBackend())

    # SMS if configured (Twilio)
    twilio_sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
    if twilio_sid:
        try:
            from shopman.backends.notification_sms import TwilioSMSBackend

            sms_backend = TwilioSMSBackend(
                account_sid=twilio_sid,
                auth_token=getattr(settings, "TWILIO_AUTH_TOKEN", ""),
                from_number=getattr(settings, "TWILIO_FROM_NUMBER", ""),
            )
            register_backend("sms", sms_backend)
        except Exception:
            logger.debug("shopman.setup: SMS backend not available", exc_info=True)

    # Manychat if configured
    api_token = getattr(settings, "MANYCHAT_API_TOKEN", "")
    if api_token:
        try:
            from shopman.backends.notification_manychat import ManychatBackend, ManychatConfig

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
            logger.debug("shopman.setup: Manychat backend not available", exc_info=True)


def _register_confirmation_handler() -> None:
    from shopman.handlers.confirmation import ConfirmationTimeoutHandler

    try:
        registry.register_directive_handler(ConfirmationTimeoutHandler())
    except ValueError:
        pass


def _register_customer_handler() -> None:
    from shopman.handlers.customer import CustomerEnsureHandler

    try:
        registry.register_directive_handler(CustomerEnsureHandler())
    except ValueError:
        pass


def _register_fiscal_handlers() -> None:
    from shopman.handlers.fiscal import NFCeCancelHandler, NFCeEmitHandler

    backend = _load_fiscal_backend()
    if not backend:
        return

    for handler in [NFCeEmitHandler(backend=backend), NFCeCancelHandler(backend=backend)]:
        try:
            registry.register_directive_handler(handler)
        except ValueError:
            pass


def _register_accounting_handler() -> None:
    from shopman.handlers.accounting import PurchaseToPayableHandler

    backend = _load_accounting_backend()
    if not backend:
        return

    try:
        registry.register_directive_handler(PurchaseToPayableHandler(backend=backend))
    except ValueError:
        pass


def _register_return_handler() -> None:
    from shopman.handlers.returns import ReturnHandler

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
    from shopman.handlers.fulfillment import FulfillmentCreateHandler, FulfillmentUpdateHandler

    for handler in [FulfillmentCreateHandler(), FulfillmentUpdateHandler()]:
        try:
            registry.register_directive_handler(handler)
        except ValueError:
            pass


def _register_loyalty_handler() -> None:
    try:
        from shopman.handlers.loyalty import LoyaltyEarnHandler

        registry.register_directive_handler(LoyaltyEarnHandler())
        logger.info("shopman.setup: Registered loyalty handler.")
    except (ImportError, ValueError):
        logger.debug("shopman.setup: Loyalty handler not available")


def _register_checkout_defaults_handler() -> None:
    try:
        from shopman.handlers.checkout_defaults import CheckoutInferDefaultsHandler

        registry.register_directive_handler(CheckoutInferDefaultsHandler())
        logger.info("shopman.setup: Registered checkout defaults handler.")
    except (ImportError, ValueError):
        logger.debug("shopman.setup: Checkout defaults handler not available")


def _register_pricing_modifiers() -> None:
    from shopman.backends.pricing import OfferingBackend
    from shopman.handlers.pricing import ItemPricingModifier, SessionTotalModifier
    from shopman.modifiers import (
        D1DiscountModifier,
        DeliveryFeeModifier,
        DiscountModifier,
        EmployeeDiscountModifier,
        HappyHourModifier,
    )

    backend = OfferingBackend()
    modifiers = [
        ItemPricingModifier(backend=backend),
        D1DiscountModifier(),
        DiscountModifier(),
        SessionTotalModifier(),
        EmployeeDiscountModifier(),
        HappyHourModifier(),
        DeliveryFeeModifier(),
    ]
    for modifier in modifiers:
        try:
            registry.register_modifier(modifier)
        except ValueError:
            pass

    logger.info("shopman.setup: Registered pricing modifiers.")


def _register_checks() -> None:
    from shopman.handlers.stock import StockCheck

    try:
        registry.register_check(StockCheck())
    except (ValueError, AttributeError):
        pass


def _register_stock_validator() -> None:
    """Registra StockCheckValidator (valida checks no commit)."""
    from shopman.handlers.stock import StockCheckValidator

    try:
        registry.register_validator(StockCheckValidator())
    except (ValueError, TypeError):
        pass

    # Delivery zone — bloqueia commit quando endereço não atendido
    from shopman.rules.validation import DeliveryZoneRule

    try:
        registry.register_validator(DeliveryZoneRule())
    except (ValueError, TypeError):
        pass


def _register_stock_signals() -> None:
    """Connect stock hold materialization + production voided signals."""
    try:
        from shopman.handlers._stock_receivers import on_holds_materialized
        from shopman.stocking.signals import holds_materialized

        holds_materialized.connect(on_holds_materialized, weak=False)
        logger.info("shopman.setup: Connected holds_materialized receiver.")
    except ImportError:
        logger.debug("shopman.setup: stocking signals not available")

    try:
        from shopman.crafting.signals import production_changed
        from shopman.handlers._stock_receivers import on_production_voided

        production_changed.connect(on_production_voided, weak=False)
        logger.info("shopman.setup: Connected production_changed receiver (voided).")

        # Import core-level handler — the @receiver decorator auto-connects
        # planned/adjusted/closed/voided → Stocking quant management
        import shopman.crafting.contrib.stocking.handlers  # noqa: F401

        logger.info("shopman.setup: Loaded crafting→stocking signal handlers.")
    except ImportError:
        logger.debug("shopman.setup: crafting signals not available")


# ── Backend loaders ──


def _load_stock_backend():
    backend_path = getattr(settings, "SHOPMAN_STOCK_BACKEND", None)
    if backend_path:
        return _import_class(backend_path)()

    try:
        from shopman.backends.stock import StockingBackend
        from shopman.stocking import stock  # noqa: F401

        def _product_resolver(sku: str):
            from shopman.offering.models import Product

            return Product.objects.get(sku=sku)

        return StockingBackend(product_resolver=_product_resolver)
    except ImportError:
        pass

    from shopman.backends.stock import NoopStockBackend

    return NoopStockBackend()


def _load_payment_backend():
    backend_path = getattr(settings, "SHOPMAN_PAYMENT_BACKEND", "shopman.backends.payment_mock.MockPaymentBackend")
    try:
        return _import_class(backend_path)()
    except Exception:
        logger.warning("shopman.setup: Could not load payment backend", exc_info=True)
        return None


def _load_fiscal_backend():
    backend_path = getattr(settings, "SHOPMAN_FISCAL_BACKEND", None)
    if not backend_path:
        try:
            from shopman.backends.fiscal_mock import MockFiscalBackend

            return MockFiscalBackend()
        except ImportError:
            return None
    try:
        return _import_class(backend_path)()
    except Exception:
        logger.warning("shopman.setup: Could not load fiscal backend", exc_info=True)
        return None


def _load_accounting_backend():
    backend_path = getattr(settings, "SHOPMAN_ACCOUNTING_BACKEND", None)
    if not backend_path:
        try:
            from shopman.backends.accounting_mock import MockAccountingBackend

            return MockAccountingBackend()
        except ImportError:
            return None
    try:
        return _import_class(backend_path)()
    except Exception:
        logger.warning("shopman.setup: Could not load accounting backend", exc_info=True)
        return None


def _import_class(dotted_path: str):
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)
