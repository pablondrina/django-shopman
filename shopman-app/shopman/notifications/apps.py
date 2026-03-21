"""
Django AppConfig para notifications.

Registra:
- NotificationSendHandler no registry de diretivas
- ConsoleBackend como backend default (se nenhum outro configurado)
"""

from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class NotificationsConfig(AppConfig):
    name = "shopman.notifications"
    label = "shopman_notifications"
    verbose_name = _("Notificacoes")

    def ready(self):
        from shopman.ordering.registry import register_directive_handler

        from .backends.console import ConsoleBackend
        from .handlers import NotificationSendHandler
        from .service import register_backend

        # Register directive handler for topic="notification.send"
        try:
            register_directive_handler(NotificationSendHandler())
        except ValueError:
            pass  # Already registered (reload)

        # Register default console backend
        register_backend("console", ConsoleBackend())

        # Register Manychat backend if API token is configured
        self._register_manychat_backend(register_backend)

    @staticmethod
    def _register_manychat_backend(register_backend) -> None:
        from django.conf import settings

        api_token = getattr(settings, "MANYCHAT_API_TOKEN", "")
        if not api_token:
            return

        from .backends.manychat import ManychatBackend, ManychatConfig

        config = ManychatConfig(
            api_token=api_token,
            flow_map=getattr(settings, "MANYCHAT_FLOW_MAP", {}),
        )

        resolver = None
        try:
            from shopman.attending.contrib.manychat.resolver import ManychatSubscriberResolver

            resolver = ManychatSubscriberResolver.resolve
        except ImportError:
            pass

        register_backend("manychat", ManychatBackend(config=config, resolver=resolver))
