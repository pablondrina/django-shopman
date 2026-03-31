"""
Django AppConfig for channels/.

Registra handlers, backends e checks novos via setup.register_all().
"""

from __future__ import annotations

import logging

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class ChannelsConfig(AppConfig):
    name = "channels"
    label = "channels_app"
    verbose_name = _("Canais")

    def ready(self):
        from channels.setup import register_all

        try:
            register_all()
            self._connect_signals()
            self._validate_hold_ttl()
            logger.info("ChannelsConfig: setup complete.")
        except Exception:
            logger.warning(
                "ChannelsConfig: setup failed.",
                exc_info=True,
            )

    @staticmethod
    def _validate_hold_ttl():
        """Validate HOLD_TTL >= PAYMENT_TIMEOUT + 5 min margin for all presets."""
        from channels.presets import remote

        config = remote()
        hold_ttl = config.get("stock", {}).get("hold_ttl_minutes") or 0
        pix_timeout = config.get("payment", {}).get("timeout_minutes") or 0
        margin = 5

        if hold_ttl and pix_timeout and hold_ttl < pix_timeout + margin:
            logger.error(
                "HOLD_TTL (%d min) < PAYMENT_TIMEOUT (%d min) + margin (%d min). "
                "Risk of overselling. Increase hold_ttl_minutes.",
                hold_ttl, pix_timeout, margin,
            )

    def _connect_signals(self):
        from shopman.ordering.signals import order_changed

        from channels.hooks import on_order_lifecycle

        order_changed.connect(
            on_order_lifecycle,
            dispatch_uid="channels.on_order_lifecycle",
        )
