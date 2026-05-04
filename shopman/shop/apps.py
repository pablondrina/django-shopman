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
        self._connect_lifecycle_signal()

        # 4. Connect production_changed → production_lifecycle.dispatch_production
        self._connect_production_lifecycle_signal()

        # 5. Connect Recipe post_save → materialize Product ingredients + nutrition
        self._connect_recipe_nutrition_signal()

        # 6. Register CHANNEL RefType
        self._register_ref_types()

    def _register_ref_types(self):
        try:
            from shopman.refs import register_ref_type
            from shopman.refs.types import RefType
            channel = RefType(
                slug="CHANNEL",
                label="Canal",
                allowed_targets=("shop.Channel",),
                unique_scope="all",
                normalizer="upper_strip",
            )
            try:
                register_ref_type(channel)
            except ValueError:
                pass
        except ImportError:
            pass

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

    def _connect_lifecycle_signal(self):
        """Connect Core signal order_changed → lifecycle.dispatch().

        This replaces the old channels.hooks.on_order_lifecycle signal handler.
        The old handler is NOT connected — channels app is not in INSTALLED_APPS.
        """
        from shopman.orderman.signals import order_changed

        from shopman.shop.lifecycle import dispatch

        def on_order_changed(sender, order, event_type, actor, **kwargs):
            from django.db import transaction as _tx

            if event_type == "created":
                phase = "on_commit"
            elif event_type == "status_changed":
                phase = f"on_{order.status}"
            else:
                return
            _tx.on_commit(lambda: dispatch(order, phase))

        order_changed.connect(
            on_order_changed,
            dispatch_uid="shopman.shop.lifecycle.on_order_changed",
            weak=False,
        )
        logger.info("ShopmanConfig: lifecycle signal connected.")

    def _connect_production_lifecycle_signal(self):
        """Connect Core signal production_changed → production_lifecycle.dispatch_production()."""
        from shopman.craftsman.signals import production_changed

        from shopman.shop.production_lifecycle import on_production_changed_receiver

        production_changed.connect(
            on_production_changed_receiver,
            dispatch_uid="shopman.shop.production_lifecycle.on_production_changed",
            weak=False,
        )
        logger.info("ShopmanConfig: production lifecycle signal connected.")

    def _connect_recipe_nutrition_signal(self):
        """Materialize Product ingredients + nutrition whenever a Recipe is saved.

        Idempotent: the service refuses to overwrite manual overrides
        (``nutrition_facts["auto_filled"]=False``). See
        ``docs/decisions/adr-008-pdp-nutrition.md``.
        """
        from django.db.models.signals import post_save
        from shopman.craftsman.models import Recipe
        from shopman.offerman.models import Product

        from shopman.shop.services.nutrition_from_recipe import (
            fill_nutrition_from_recipe,
        )

        def on_recipe_saved(sender, instance: Recipe, created: bool, **kwargs):
            if not instance.is_active:
                return
            product = Product.objects.filter(sku=instance.output_sku).first()
            if product is None:
                return
            try:
                fill_nutrition_from_recipe(product)
            except Exception:
                logger.exception(
                    "nutrition_from_recipe: failed for product=%s recipe=%s",
                    instance.output_sku, instance.ref,
                )

        post_save.connect(
            on_recipe_saved,
            sender=Recipe,
            dispatch_uid="shopman.shop.services.nutrition_from_recipe.on_recipe_saved",
            weak=False,
        )
        logger.info("ShopmanConfig: recipe nutrition signal connected.")
