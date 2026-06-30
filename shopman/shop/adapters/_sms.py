"""Shared helpers for SMS OTP senders (Twilio, Comtele, …).

Keeps message rendering and number normalization in one place so each provider sender
stays thin. Provider choice is swappable via DOORMAN['DELIVERY_SENDERS']['sms'].
"""

from __future__ import annotations

DEFAULT_CODE_MESSAGE = "{code} é o seu código de verificação. Válido por {ttl} minutos. Não compartilhe."


def ttl_minutes() -> int:
    """Verification code validity in minutes (from Doorman config; 10 as fallback)."""
    try:
        from shopman.doorman.conf import doorman_settings

        return int(doorman_settings.ACCESS_CODE_TTL_MINUTES)
    except Exception:
        return 10


def render_message(cfg: dict, code: str) -> str:
    """Build the OTP message text from config (or the default), filling code + ttl."""
    template = str(cfg.get("code_message") or DEFAULT_CODE_MESSAGE)
    return template.format(code=code, ttl=ttl_minutes())


def to_digits(target: str) -> str:
    """Digits-only phone number (strips '+', spaces, punctuation)."""
    return "".join(ch for ch in str(target) if ch.isdigit())
