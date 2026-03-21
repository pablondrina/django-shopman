"""
Notification Backends — Implementacoes prontas para uso.

Backends universais (funcionam out-of-the-box):
- ConsoleBackend: Log no console (dev)
- WebhookBackend: HTTP POST para qualquer URL

Backends com provider (configure com suas credenciais):
- EmailBackend: Email via Django
- WhatsAppBackend: WhatsApp via Meta Cloud API
- TwilioSMSBackend: SMS via Twilio
- ManychatBackend: WhatsApp/Instagram/Facebook/TikTok via Manychat API
"""

from .console import ConsoleBackend
from .webhook import WebhookBackend
from .email import EmailBackend
from .whatsapp import WhatsAppBackend
from .sms import TwilioSMSBackend
from .manychat import ManychatBackend, ManychatConfig

__all__ = [
    # Universais
    "ConsoleBackend",
    "WebhookBackend",
    # Com provider
    "EmailBackend",
    "WhatsAppBackend",
    "TwilioSMSBackend",
    "ManychatBackend",
    "ManychatConfig",
]
