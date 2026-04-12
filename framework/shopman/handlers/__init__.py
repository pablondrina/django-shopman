"""
Directive handlers, modifiers, validators registered at app boot.

ALL_HANDLERS is the authoritative flat list of every component this framework
registers — no separation between "core" and "optional". Optional components
have their own guard (missing setting → skip silently; present but broken → raise).

register_all() is called once by ShopmanConfig.ready().

Boot rules:
  - Required component fails  → raise (visible, never silent)
  - Optional, not configured  → skip silently
  - Optional, configured-but-wrong → raise (operator made a mistake)
"""

from __future__ import annotations

import importlib
import logging

from django.conf import settings

from shopman.orderman import registry

logger = logging.getLogger(__name__)

# ── ALL_HANDLERS — single source of truth ──

ALL_HANDLERS = [
    # Lifecycle
    "shopman.handlers.confirmation.ConfirmationTimeoutHandler",
    # Fulfillment
    "shopman.handlers.fulfillment.FulfillmentCreateHandler",
    "shopman.handlers.fulfillment.FulfillmentUpdateHandler",
    # Notification
    "shopman.handlers.notification.NotificationSendHandler",
    # Returns
    "shopman.handlers.returns.ReturnHandler",
    # Loyalty
    "shopman.handlers.loyalty.LoyaltyEarnHandler",
    "shopman.handlers.loyalty.LoyaltyRedeemHandler",
    # Fiscal (requires SHOPMAN_FISCAL_BACKEND)
    "shopman.handlers.fiscal.NFCeEmitHandler",
    "shopman.handlers.fiscal.NFCeCancelHandler",
    # Accounting (requires SHOPMAN_ACCOUNTING_BACKEND)
    "shopman.handlers.accounting.PurchaseToPayableHandler",
    # Pricing modifiers
    "shopman.handlers.pricing.ItemPricingModifier",
    "shopman.handlers.pricing.OffermanPricingBackend",
    "shopman.handlers.pricing.SessionTotalModifier",
    # Validators
    "shopman.rules.validation.DeliveryZoneRule",
    # Pricing modifiers (via shopman.modifiers)
    "shopman.modifiers.DeliveryFeeModifier",
    "shopman.modifiers.DiscountModifier",
    "shopman.modifiers.EmployeeDiscountModifier",
    "shopman.modifiers.LoyaltyRedeemModifier",
    "shopman.modifiers.ManualDiscountModifier",
    # Instance-specific modifiers loaded via SHOPMAN_INSTANCE_MODIFIERS
]


# ── register_all ──


def register_all() -> None:
    """Register all directive handlers, modifiers, validators, and signals."""
    _register_notification_handlers()
    _register_confirmation_handler()
    _register_customer_strategies()
    _register_fiscal_handlers()
    _register_accounting_handler()
    _register_return_handler()
    _register_fulfillment_handler()
    _register_loyalty_handler()
    _register_pricing_modifiers()
    _register_validators()
    _register_stock_signals()


# ── Individual registrations ──


def _register_notification_handlers() -> None:
    from shopman.adapters import notification_console, notification_email, notification_manychat
    from shopman.handlers.notification import NotificationSendHandler
    from shopman.notifications import register_backend

    registry.register_directive_handler(NotificationSendHandler())
    register_backend("console", notification_console)
    register_backend("email", notification_email)
    register_backend("manychat", notification_manychat)

    sms_path = getattr(settings, "SHOPMAN_SMS_ADAPTER", None)
    if sms_path:
        from shopman.adapters import notification_sms
        register_backend("sms", notification_sms)
    else:
        try:
            from shopman.adapters import notification_sms
            register_backend("sms", notification_sms)
        except ImportError:
            pass


def _register_confirmation_handler() -> None:
    from shopman.handlers.confirmation import ConfirmationTimeoutHandler
    registry.register_directive_handler(ConfirmationTimeoutHandler())


def _register_customer_strategies() -> None:
    """Import instance-specific customer strategy modules from SHOPMAN_CUSTOMER_STRATEGY_MODULES.

    Each module is expected to call register_strategy() at module level.
    If the setting is present, a missing or broken module is fatal (configured-but-wrong).
    """
    strategy_modules = getattr(settings, "SHOPMAN_CUSTOMER_STRATEGY_MODULES", [])
    for module_path in strategy_modules:
        importlib.import_module(module_path)
        logger.info("shopman.handlers: loaded customer strategies from %s", module_path)


def _register_fiscal_handlers() -> None:
    backend = _load_optional_backend("SHOPMAN_FISCAL_BACKEND", "fiscal")
    if not backend:
        return
    from shopman.handlers.fiscal import NFCeCancelHandler, NFCeEmitHandler
    registry.register_directive_handler(NFCeEmitHandler(backend=backend))
    registry.register_directive_handler(NFCeCancelHandler(backend=backend))


def _register_accounting_handler() -> None:
    backend = _load_optional_backend("SHOPMAN_ACCOUNTING_BACKEND", "accounting")
    if not backend:
        return
    from shopman.handlers.accounting import PurchaseToPayableHandler
    registry.register_directive_handler(PurchaseToPayableHandler(backend=backend))


def _register_return_handler() -> None:
    fiscal_backend = _load_optional_backend("SHOPMAN_FISCAL_BACKEND", "fiscal")
    from shopman.handlers.returns import ReturnHandler
    registry.register_directive_handler(ReturnHandler(fiscal_backend=fiscal_backend))


def _register_fulfillment_handler() -> None:
    from shopman.handlers.fulfillment import FulfillmentCreateHandler, FulfillmentUpdateHandler
    registry.register_directive_handler(FulfillmentCreateHandler())
    registry.register_directive_handler(FulfillmentUpdateHandler())


def _register_loyalty_handler() -> None:
    from shopman.handlers.loyalty import LoyaltyEarnHandler, LoyaltyRedeemHandler
    registry.register_directive_handler(LoyaltyEarnHandler())
    registry.register_directive_handler(LoyaltyRedeemHandler())


def _register_pricing_modifiers() -> None:
    from shopman.handlers.pricing import ItemPricingModifier, OffermanPricingBackend, SessionTotalModifier
    from shopman.modifiers import (
        DeliveryFeeModifier,
        DiscountModifier,
        EmployeeDiscountModifier,
        LoyaltyRedeemModifier,
        ManualDiscountModifier,
    )

    backend = OffermanPricingBackend()
    for modifier in [
        ItemPricingModifier(backend=backend),
        DiscountModifier(),
        SessionTotalModifier(),
        EmployeeDiscountModifier(),
        DeliveryFeeModifier(),
        LoyaltyRedeemModifier(),
        ManualDiscountModifier(),
    ]:
        registry.register_modifier(modifier)

    # Instance-specific modifiers (D-1, Happy Hour, etc.)
    _register_instance_modifiers()


def _register_instance_modifiers() -> None:
    """Load instance-specific modifiers from SHOPMAN_INSTANCE_MODIFIERS setting.

    Each entry is a dotted path to a modifier class. If the setting is present,
    a broken path is fatal (configured-but-wrong).
    """
    modifier_paths = getattr(settings, "SHOPMAN_INSTANCE_MODIFIERS", [])
    for path in modifier_paths:
        module_path, class_name = path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        modifier_class = getattr(module, class_name)
        registry.register_modifier(modifier_class())
        logger.info("shopman.handlers: loaded instance modifier %s", path)


def _register_validators() -> None:
    from shopman.rules.validation import DeliveryZoneRule
    registry.register_validator(DeliveryZoneRule())


def _register_stock_signals() -> None:
    from shopman.handlers._stock_receivers import on_holds_materialized
    from shopman.stockman.signals import holds_materialized
    holds_materialized.connect(on_holds_materialized, weak=False)
    logger.info("shopman.handlers: connected holds_materialized receiver.")

    try:
        from shopman.craftsman.signals import production_changed
        from shopman.handlers._stock_receivers import on_production_voided
        production_changed.connect(on_production_voided, weak=False)

        import shopman.craftsman.contrib.stockman.handlers  # noqa: F401
        logger.info("shopman.handlers: loaded craftsman→stockman signal handlers.")
    except ImportError:
        pass


# ── Backend loader ──


def _load_optional_backend(setting_key: str, label: str):
    """Load an optional backend class from a dotted path in settings.

    Returns None if the setting is absent (not configured → silent).
    Raises if the setting is present but the class cannot be loaded (configured-but-wrong → fatal).
    """
    dotted_path = getattr(settings, setting_key, None)
    if not dotted_path:
        return None
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)()
