"""
Shopman Notifications — Sistema simples e plugavel de notificacoes.

Uso basico:
    from shopman.notifications import notify

    # Envia notificacao usando backend configurado
    notify(
        event="order.confirmed",
        recipient="customer@email.com",
        context={"order_ref": "ORD-123", "total": "R$ 50,00"},
    )

Backends disponiveis:
    - console: Log no console (desenvolvimento)
    - webhook: HTTP POST para qualquer URL (integra com Zapier, n8n, Make, etc)
    - email: Email via Django
    - whatsapp: WhatsApp via API (Twilio, Meta, etc)
    - sms: SMS via API (Twilio, etc)

Configuracao via settings.py:
    SHOPMAN_NOTIFICATIONS = {
        "default_backend": "webhook",
        "backends": {
            "webhook": {
                "class": "shopman.notifications.backends.WebhookBackend",
                "url": "https://hooks.zapier.com/xxx",
            },
            "whatsapp": {
                "class": "shopman.notifications.backends.WhatsAppBackend",
                "api_url": "https://graph.facebook.com/v17.0/xxx/messages",
                "token": "xxx",
            },
        },
    }

Ou via Channel.config (por canal):
    channel.config = {
        "notifications": {
            "backend": "whatsapp",
            "on_events": ["order.confirmed", "order.ready"],
        }
    }
"""

from .service import notify, get_backend, register_backend
from .protocols import NotificationBackend, NotificationResult

__all__ = [
    "notify",
    "get_backend",
    "register_backend",
    "NotificationBackend",
    "NotificationResult",
]
