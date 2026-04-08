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
    _register_validators()
    _register_stock_signals()


def _register_notification_handlers() -> None:
    from shopman.adapters import notification_console, notification_email, notification_manychat
    from shopman.handlers.notification import NotificationSendHandler
    from shopman.notifications import register_backend

    try:
        registry.register_directive_handler(NotificationSendHandler())
    except ValueError:
        pass

    register_backend("console", notification_console)
    register_backend("email", notification_email)

    # SMS adapter (always registered — disabled at send time when Twilio not configured)
    try:
        from shopman.adapters import notification_sms
        register_backend("sms", notification_sms)
    except ImportError:
        logger.debug("shopman.setup: SMS adapter not available", exc_info=True)

    # Manychat adapter (always registered — disabled at send time when API token not configured)
    register_backend("manychat", notification_manychat)


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

    fiscal_backend = _load_fiscal_backend()

    try:
        registry.register_directive_handler(
            ReturnHandler(fiscal_backend=fiscal_backend)
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
        from shopman.handlers.loyalty import LoyaltyEarnHandler, LoyaltyRedeemHandler

        registry.register_directive_handler(LoyaltyEarnHandler())
        registry.register_directive_handler(LoyaltyRedeemHandler())
        logger.info("shopman.setup: Registered loyalty handlers.")
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
    from shopman.handlers.pricing import ItemPricingModifier, OfferingPricingBackend, SessionTotalModifier
    from shopman.modifiers import (
        D1DiscountModifier,
        DeliveryFeeModifier,
        DiscountModifier,
        EmployeeDiscountModifier,
        HappyHourModifier,
        LoyaltyRedeemModifier,
        ManualDiscountModifier,
    )

    backend = OfferingPricingBackend()
    modifiers = [
        ItemPricingModifier(backend=backend),
        D1DiscountModifier(),
        DiscountModifier(),
        SessionTotalModifier(),
        EmployeeDiscountModifier(),
        HappyHourModifier(),
        DeliveryFeeModifier(),
        LoyaltyRedeemModifier(),
        ManualDiscountModifier(),
    ]
    for modifier in modifiers:
        try:
            registry.register_modifier(modifier)
        except ValueError:
            pass

    logger.info("shopman.setup: Registered pricing modifiers.")


def _register_validators() -> None:
    """Registra validators de commit (rodam dentro do CommitService)."""
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


def _load_fiscal_backend():
    backend_path = getattr(settings, "SHOPMAN_FISCAL_BACKEND", None)
    if not backend_path:
        try:
            from shopman.tests._mocks.fiscal_mock import MockFiscalBackend

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
            from shopman.tests._mocks.accounting_mock import MockAccountingBackend

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
