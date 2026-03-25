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
            logger.info("ChannelsConfig: setup complete.")
        except Exception:
            logger.warning(
                "ChannelsConfig: setup failed.",
                exc_info=True,
            )

    def _connect_signals(self):
        from shopman.ordering.signals import order_changed

        from channels.hooks import on_order_lifecycle

        order_changed.connect(
            on_order_lifecycle,
            dispatch_uid="channels.on_order_lifecycle",
        )
