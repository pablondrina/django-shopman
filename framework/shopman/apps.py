"""
Django AppConfig for the Shopman orchestrator.

Wiring:
  1. Core signal order_changed → flows.dispatch()
  2. Core signal production_changed → production_flows.dispatch_production()
  3. Handler/modifier/check registration via shopman.setup
  4. Stock signals (Core ↔ Core bridge)
"""

from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ShopmanConfig(AppConfig):
    name = "shopman"
    verbose_name = "Shopman"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # 1. Register handlers, modifiers, checks via channels.setup
        # (temporary — these will be migrated to shopman/ in R8)
        self._register_handlers()

        # 2. Register active validator rules from RuleConfig DB
        self._register_rules()

        # 3. Connect order_changed → flows.dispatch (NEW — replaces channels.hooks)
        self._connect_flow_signal()

        # 4. Connect production_changed → production flows (WP-S5)
        self._connect_production_flow_signal()

    def _register_handlers(self):
        """Register all directive handlers, modifiers, checks, and stock signals.

        Uses channels.setup.register_all() which registers:
        - Stock handlers (StockHoldHandler, StockCommitHandler)
        - Payment handlers (Pix, Card, Capture, Refund, Timeout)
        - Notification handler + backends
        - Confirmation timeout handler
        - Customer ensure handler
        - Fiscal handlers (NFCe emit/cancel)
        - Accounting handler
        - Return handler
        - Fulfillment handlers
        - Loyalty handler
        - Checkout defaults handler
        - Pricing modifiers (Item, D1, Discount, SessionTotal, Employee, HappyHour)
        - Stock check + validator
        - Stock signals (holds_materialized, production_changed, crafting→stocking)
        """
        try:
            from shopman.setup import register_all
            register_all()
            logger.info("ShopmanConfig: handlers registered via shopman.setup.")
        except Exception:
            logger.warning("ShopmanConfig: handler registration failed.", exc_info=True)

    def _register_rules(self):
        """Register active validator rules and connect cache invalidation signal."""
        try:
            from django.db.models.signals import post_save

            from shopman.models import RuleConfig
            from shopman.rules.engine import invalidate_rules_cache, register_active_rules

            register_active_rules()

            post_save.connect(
                invalidate_rules_cache,
                sender=RuleConfig,
                dispatch_uid="shopman.rules.invalidate_cache",
            )
            logger.info("ShopmanConfig: rules engine booted.")
        except Exception:
            logger.warning("ShopmanConfig: rules engine boot failed.", exc_info=True)

    def _connect_flow_signal(self):
        """Connect Core signal order_changed → flows.dispatch().

        This replaces the old channels.hooks.on_order_lifecycle signal handler.
        The old handler is NOT connected — channels app is not in INSTALLED_APPS.
        """
        from shopman.flows import dispatch
        from shopman.ordering.signals import order_changed

        def on_order_changed(sender, order, event_type, actor, **kwargs):
            if event_type == "created":
                dispatch(order, "on_commit")
            elif event_type == "status_changed":
                dispatch(order, f"on_{order.status}")

        order_changed.connect(
            on_order_changed,
            dispatch_uid="shopman.flows.on_order_changed",
            weak=False,
        )
        logger.info("ShopmanConfig: flow signal connected.")

    def _connect_production_flow_signal(self):
        """Connect Core signal production_changed → production_flows.dispatch_production()."""
        from shopman.crafting.signals import production_changed
        from shopman.production_flows import on_production_changed_receiver

        production_changed.connect(
            on_production_changed_receiver,
            dispatch_uid="shopman.production_flows.on_production_changed",
            weak=False,
        )
        logger.info("ShopmanConfig: production flow signal connected.")
