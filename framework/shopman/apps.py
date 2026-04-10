"""
Django AppConfig for the Shopman orchestrator.

Wiring:
  1. Handler/modifier/validator registration via shopman.handlers.register_all()
  2. Rules engine boot + cache invalidation signal
  3. Core signal order_changed → flows.dispatch()
  4. Core signal production_changed → production_flows.dispatch_production()
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
        # 0. Register system checks
        import shopman.checks  # noqa: F401

        # 1. Register handlers, modifiers, validators
        self._register_handlers()

        # 2. Boot rules engine + connect cache invalidation
        self._register_rules()

        # 3. Connect order_changed → flows.dispatch
        self._connect_flow_signal()

        # 4. Connect production_changed → production flows
        self._connect_production_flow_signal()

    def _register_handlers(self):
        """Register all directive handlers, modifiers, validators, and stock signals.

        Required components raise on failure.
        Optional components are silent when not configured; fatal when configured-but-wrong.
        See shopman.handlers.ALL_HANDLERS for the complete list.
        """
        from shopman.handlers import register_all
        register_all()
        logger.info("ShopmanConfig: handlers registered.")

    def _register_rules(self):
        """Boot the rules engine and connect RuleConfig cache invalidation."""
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

    def _connect_flow_signal(self):
        """Connect Core signal order_changed → flows.dispatch().

        This replaces the old channels.hooks.on_order_lifecycle signal handler.
        The old handler is NOT connected — channels app is not in INSTALLED_APPS.
        """
        from shopman.flows import dispatch
        from shopman.orderman.signals import order_changed

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
        from shopman.craftsman.signals import production_changed
        from shopman.production_flows import on_production_changed_receiver

        production_changed.connect(
            on_production_changed_receiver,
            dispatch_uid="shopman.production_flows.on_production_changed",
            weak=False,
        )
        logger.info("ShopmanConfig: production flow signal connected.")
