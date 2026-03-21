"""
Django AppConfig para confirmation.

Registra:
- ConfirmationTimeoutHandler no registry de diretivas
- Hooks (on_order_created, on_order_status_changed) no signal order_changed
"""

from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ConfirmationConfig(AppConfig):
    name = "shopman.confirmation"
    label = "confirmation"
    verbose_name = _("Confirmação de Pedidos")

    def ready(self):
        from shopman.ordering.registry import register_directive_handler
        from shopman.ordering.signals import order_changed

        from .handlers import ConfirmationTimeoutHandler
        from .hooks import on_order_created, on_order_status_changed

        # --- Registra handler de diretiva ---
        try:
            register_directive_handler(ConfirmationTimeoutHandler())
        except ValueError:
            pass  # Já registrado (reload)

        # --- Conecta hooks ao signal order_changed ---
        # on_order_status_changed escuta todas as mudanças de status
        order_changed.connect(
            on_order_status_changed,
            dispatch_uid="confirmation.on_order_status_changed",
        )

        # on_order_created é chamado quando event_type == "created"
        # Wrappamos para extrair o order do kwargs do signal
        def _on_order_created_receiver(sender, order, event_type, actor, **kwargs):
            if event_type == "created":
                on_order_created(order)

        order_changed.connect(
            _on_order_created_receiver,
            dispatch_uid="confirmation.on_order_created",
        )
