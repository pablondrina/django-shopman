"""
Django AppConfig for the Shopman orchestrator.

Wiring:
  1. Handler/modifier/validator registration via shopman.handlers.register_all()
  2. Rules engine boot + cache invalidation signal
  3. Core signal order_changed → lifecycle.dispatch()
  4. Core signal production_changed → production_lifecycle.dispatch_production()
"""

from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ShopmanConfig(AppConfig):
    name = "shopman.shop"
    label = "shop"
    verbose_name = "Shopman"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # 0. Register system checks
        import shopman.shop.checks  # noqa: F401

        # 1. Register handlers, modifiers, validators
        self._register_handlers()

        # 2. Boot rules engine + connect cache invalidation
        self._register_rules()

        # 3. Connect order_changed → lifecycle.dispatch
        self._connect_flow_signal()

        # 4. Connect production_changed → production_lifecycle.dispatch_production
        self._connect_production_flow_signal()

    def _register_handlers(self):
        """Register all directive handlers, modifiers, validators, and stock signals.

        Required components raise on failure.
        Optional components are silent when not configured; fatal when configured-but-wrong.
        See shopman.handlers.ALL_HANDLERS for the complete list.
        """
        from shopman.shop.handlers import register_all
        register_all()
        logger.info("ShopmanConfig: handlers registered.")

    def _register_rules(self):
        """Wire rule cache invalidation and defer DB-backed bootstrap until DB is ready."""
        from django.db.backends.signals import connection_created
        from django.db.models.signals import post_save

        from shopman.shop.models import RuleConfig
        from shopman.shop.rules.engine import bootstrap_active_rules, invalidate_rules_cache

        connection_created.connect(
            lambda sender, connection, **kwargs: bootstrap_active_rules(),
            dispatch_uid="shopman.shop.rules.bootstrap_on_connection",
            weak=False,
        )

        post_save.connect(
            invalidate_rules_cache,
            sender=RuleConfig,
            dispatch_uid="shopman.shop.rules.invalidate_cache",
        )
        logger.info("ShopmanConfig: rules engine wired.")

    def _connect_flow_signal(self):
        """Connect Core signal order_changed → lifecycle.dispatch().

        This replaces the old channels.hooks.on_order_lifecycle signal handler.
        The old handler is NOT connected — channels app is not in INSTALLED_APPS.
        """
        from shopman.shop.lifecycle import dispatch
        from shopman.orderman.signals import order_changed

        def on_order_changed(sender, order, event_type, actor, **kwargs):
            if event_type == "created":
                dispatch(order, "on_commit")
            elif event_type == "status_changed":
                dispatch(order, f"on_{order.status}")

        order_changed.connect(
            on_order_changed,
            dispatch_uid="shopman.shop.lifecycle.on_order_changed",
            weak=False,
        )
        logger.info("ShopmanConfig: flow signal connected.")

    def _connect_production_flow_signal(self):
        """Connect Core signal production_changed → production_lifecycle.dispatch_production()."""
        from shopman.craftsman.signals import production_changed
        from shopman.shop.production_lifecycle import on_production_changed_receiver

        production_changed.connect(
            on_production_changed_receiver,
            dispatch_uid="shopman.shop.production_lifecycle.on_production_changed",
            weak=False,
        )
        logger.info("ShopmanConfig: production flow signal connected.")
