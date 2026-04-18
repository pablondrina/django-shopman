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
    "shopman.shop.handlers.confirmation.ConfirmationTimeoutHandler",
    "shopman.shop.handlers.confirmation.StaleNewOrderAlertHandler",
    # Mock PIX (dev/test only; only fires when payment_mock scheduled a directive)
    "shopman.shop.handlers.mock_pix.MockPixConfirmHandler",
    # Fulfillment
    "shopman.shop.handlers.fulfillment.FulfillmentCreateHandler",
    "shopman.shop.handlers.fulfillment.FulfillmentUpdateHandler",
    # Notification
    "shopman.shop.handlers.notification.NotificationSendHandler",
    # Returns
    "shopman.shop.handlers.returns.ReturnHandler",
    # Loyalty
    "shopman.shop.handlers.loyalty.LoyaltyEarnHandler",
    "shopman.shop.handlers.loyalty.LoyaltyRedeemHandler",
    # Fiscal (requires SHOPMAN_FISCAL_BACKEND)
    "shopman.shop.handlers.fiscal.NFCeEmitHandler",
    "shopman.shop.handlers.fiscal.NFCeCancelHandler",
    # Accounting (requires SHOPMAN_ACCOUNTING_BACKEND)
    "shopman.shop.handlers.accounting.PurchaseToPayableHandler",
    # Pricing modifiers
    "shopman.shop.handlers.pricing.ItemPricingModifier",
    "shopman.shop.handlers.pricing.OffermanPricingBackend",
    "shopman.shop.handlers.pricing.SessionTotalModifier",
    # Validators
    "shopman.shop.rules.validation.DeliveryZoneRule",
    # Pricing modifiers (via shopman.modifiers)
    "shopman.shop.modifiers.DeliveryFeeModifier",
    "shopman.shop.modifiers.DiscountModifier",
    "shopman.shop.modifiers.EmployeeDiscountModifier",
    "shopman.shop.modifiers.LoyaltyRedeemModifier",
    "shopman.shop.modifiers.ManualDiscountModifier",
    # Instance-specific modifiers loaded via SHOPMAN_INSTANCE_MODIFIERS
]


# ── register_all ──


def register_all() -> None:
    """Register all directive handlers, modifiers, validators, and signals."""
    _register_notification_handlers()
    _register_confirmation_handler()
    _register_mock_pix_handler()
    _register_customer_strategies()
    _register_fiscal_handlers()
    _register_accounting_handler()
    _register_return_handler()
    _register_fulfillment_handler()
    _register_loyalty_handler()
    _register_pricing_modifiers()
    _register_validators()
    _register_stock_signals()
    _register_sse_emitters()
    _register_catalog_projection_handler()
    _register_catalog_signals()


# ── Individual registrations ──


def _register_notification_handlers() -> None:
    from shopman.shop.adapters import notification_console, notification_email, notification_manychat
    from shopman.shop.handlers.notification import NotificationSendHandler
    from shopman.shop.notifications import register_backend

    registry.register_directive_handler(NotificationSendHandler())
    register_backend("console", notification_console)
    register_backend("email", notification_email)
    register_backend("manychat", notification_manychat)

    sms_path = getattr(settings, "SHOPMAN_SMS_ADAPTER", None)
    if sms_path:
        from shopman.shop.adapters import notification_sms
        register_backend("sms", notification_sms)
    else:
        try:
            from shopman.shop.adapters import notification_sms
            register_backend("sms", notification_sms)
        except ImportError:
            pass


def _register_confirmation_handler() -> None:
    from shopman.shop.handlers.confirmation import (
        ConfirmationTimeoutHandler,
        StaleNewOrderAlertHandler,
    )
    registry.register_directive_handler(ConfirmationTimeoutHandler())
    registry.register_directive_handler(StaleNewOrderAlertHandler())


def _register_mock_pix_handler() -> None:
    """Register the mock PIX confirmation handler whenever the PIX payment
    adapter resolves to ``shopman.shop.adapters.payment_mock``.

    The handler is harmless if no directive ever fires (mock mode off), but
    gating registration on the adapter choice keeps production environments
    free of a handler whose topic nothing ever publishes.
    """
    pix_adapter = getattr(settings, "SHOPMAN_PAYMENT_ADAPTERS", {}).get("pix", "")
    if pix_adapter != "shopman.shop.adapters.payment_mock":
        return
    from shopman.shop.handlers.mock_pix import MockPixConfirmHandler
    registry.register_directive_handler(MockPixConfirmHandler())


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
    from shopman.shop.handlers.fiscal import NFCeCancelHandler, NFCeEmitHandler
    registry.register_directive_handler(NFCeEmitHandler(backend=backend))
    registry.register_directive_handler(NFCeCancelHandler(backend=backend))


def _register_accounting_handler() -> None:
    backend = _load_optional_backend("SHOPMAN_ACCOUNTING_BACKEND", "accounting")
    if not backend:
        return
    from shopman.shop.handlers.accounting import PurchaseToPayableHandler
    registry.register_directive_handler(PurchaseToPayableHandler(backend=backend))


def _register_return_handler() -> None:
    fiscal_backend = _load_optional_backend("SHOPMAN_FISCAL_BACKEND", "fiscal")
    from shopman.shop.handlers.returns import ReturnHandler
    registry.register_directive_handler(ReturnHandler(fiscal_backend=fiscal_backend))


def _register_fulfillment_handler() -> None:
    from shopman.shop.handlers.fulfillment import FulfillmentCreateHandler, FulfillmentUpdateHandler
    registry.register_directive_handler(FulfillmentCreateHandler())
    registry.register_directive_handler(FulfillmentUpdateHandler())


def _register_loyalty_handler() -> None:
    from shopman.shop.handlers.loyalty import LoyaltyEarnHandler, LoyaltyRedeemHandler
    registry.register_directive_handler(LoyaltyEarnHandler())
    registry.register_directive_handler(LoyaltyRedeemHandler())


def _register_pricing_modifiers() -> None:
    from shopman.shop.handlers.pricing import ItemPricingModifier, OffermanPricingBackend, SessionTotalModifier
    from shopman.shop.modifiers import (
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
    from shopman.shop.rules.validation import DeliveryZoneRule
    registry.register_validator(DeliveryZoneRule())


def _register_sse_emitters() -> None:
    """Wire SSE push emitters (WP-AV-10).

    Signals fire on Hold/Move/Product/ListingItem changes and publish to the
    per-channel SSE stream so storefront and POS clients refresh their badges
    without polling.
    """
    from shopman.shop.handlers._sse_emitters import _connect

    _connect()


def _register_stock_signals() -> None:
    from shopman.stockman.signals import holds_materialized

    from shopman.shop.handlers._stock_receivers import on_holds_materialized
    holds_materialized.connect(on_holds_materialized, weak=False)
    logger.info("shopman.handlers: connected holds_materialized receiver.")

    try:
        from shopman.craftsman.signals import production_changed

        from shopman.shop.handlers._stock_receivers import on_production_voided
        production_changed.connect(on_production_voided, weak=False)

        import shopman.craftsman.contrib.stockman.handlers  # noqa: F401
        logger.info("shopman.handlers: loaded craftsman→stockman signal handlers.")
    except ImportError:
        pass


def _register_catalog_projection_handler() -> None:
    """Register CatalogProjectHandler for each configured projection adapter."""
    adapter_map = getattr(settings, "SHOPMAN_CATALOG_PROJECTION_ADAPTERS", {})
    if not adapter_map:
        return
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    for listing_ref, dotted_path in adapter_map.items():
        module_path, class_name = dotted_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        backend_cls = getattr(module, class_name)
        registry.register_directive_handler(CatalogProjectHandler(backend=backend_cls()))
        logger.info("shopman.handlers: registered CatalogProjectHandler for %s", listing_ref)


def _register_catalog_signals() -> None:
    """Wire Offerman product_created / price_changed → catalog projection directives."""
    try:
        from shopman.offerman.signals import price_changed, product_created

        from shopman.shop.handlers.catalog_projection import on_price_changed, on_product_created
        product_created.connect(on_product_created, weak=False)
        price_changed.connect(on_price_changed, weak=False)
        logger.info("shopman.handlers: connected offerman catalog projection signals.")
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
