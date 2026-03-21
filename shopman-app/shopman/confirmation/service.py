from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings


# Hardcoded defaults (último recurso na cascata)
DEFAULT_CONFIRMATION_TIMEOUT_MINUTES = 5
DEFAULT_PIX_PAYMENT_TIMEOUT_MINUTES = 10
DEFAULT_HOLD_EXPIRATION_MINUTES = 20
DEFAULT_SAFETY_MARGIN = 0


def _get_settings_confirmation_flow() -> dict[str, Any]:
    """Retorna settings.CONFIRMATION_FLOW ou dict vazio."""
    return getattr(settings, "CONFIRMATION_FLOW", {})


def get_confirmation_timeout(channel: Any) -> int:
    """
    Retorna timeout de confirmação do operador em minutos.

    Cascata:
    1. Channel.config["confirmation_flow"]["confirmation_timeout_minutes"]
    2. settings.CONFIRMATION_FLOW["confirmation_timeout_minutes"]
    3. DEFAULT_CONFIRMATION_TIMEOUT_MINUTES (5)
    """
    config = (channel.config or {}).get("confirmation_flow", {})
    value = config.get("confirmation_timeout_minutes")
    if value is not None:
        return int(value)

    value = _get_settings_confirmation_flow().get("confirmation_timeout_minutes")
    if value is not None:
        return int(value)

    return DEFAULT_CONFIRMATION_TIMEOUT_MINUTES


def get_pix_timeout(channel: Any) -> int:
    """
    Retorna timeout de pagamento PIX em minutos.

    Cascata:
    1. Channel.config["confirmation_flow"]["pix_payment_timeout_minutes"]
    2. settings.CONFIRMATION_FLOW["pix_payment_timeout_minutes"]
    3. DEFAULT_PIX_PAYMENT_TIMEOUT_MINUTES (10)
    """
    config = (channel.config or {}).get("confirmation_flow", {})
    value = config.get("pix_payment_timeout_minutes")
    if value is not None:
        return int(value)

    value = _get_settings_confirmation_flow().get("pix_payment_timeout_minutes")
    if value is not None:
        return int(value)

    return DEFAULT_PIX_PAYMENT_TIMEOUT_MINUTES


def get_hold_expiration(channel: Any) -> int:
    """
    Retorna TTL do hold de checkout em minutos.

    Cascata:
    1. Channel.config["stock"]["checkout_hold_expiration_minutes"]
    2. settings.CONFIRMATION_FLOW["checkout_hold_expiration_minutes"]
    3. DEFAULT_HOLD_EXPIRATION_MINUTES (20)
    """
    stock_config = (channel.config or {}).get("stock", {})
    value = stock_config.get("checkout_hold_expiration_minutes")
    if value is not None:
        return int(value)

    value = _get_settings_confirmation_flow().get("checkout_hold_expiration_minutes")
    if value is not None:
        return int(value)

    return DEFAULT_HOLD_EXPIRATION_MINUTES


def calculate_hold_ttl(channel: Any) -> timedelta:
    """
    Calcula TTL do hold garantindo que cobre todo o ciclo.

    Hold TTL = max(configurado, confirmação + pagamento + 5 min margem)
    """
    configured = get_hold_expiration(channel)
    confirm = get_confirmation_timeout(channel)
    pix = get_pix_timeout(channel)
    minimum = confirm + pix + 5  # 5 min margem

    return timedelta(minutes=max(configured, minimum))


def get_safety_margin(channel: Any, product_data: dict | None = None) -> int:
    """
    Retorna margem de segurança (unidades de buffer).

    Cascata:
    1. product_data["safety_margin"] (por produto)
    2. Channel.config["stock"]["safety_margin_default"] (por canal)
    3. settings.CONFIRMATION_FLOW["default_safety_margin"] (global)
    4. 0 (sem margem)
    """
    if product_data and "safety_margin" in product_data:
        return int(product_data["safety_margin"])

    stock_config = (channel.config or {}).get("stock", {})
    value = stock_config.get("safety_margin_default")
    if value is not None:
        return int(value)

    value = _get_settings_confirmation_flow().get("default_safety_margin")
    if value is not None:
        return int(value)

    return DEFAULT_SAFETY_MARGIN


def requires_manual_confirmation(channel: Any) -> bool:
    """Retorna se o canal requer confirmação manual do operador."""
    config = (channel.config or {}).get("confirmation_flow", {})
    value = config.get("require_manual_confirmation")
    if value is not None:
        return bool(value)

    value = _get_settings_confirmation_flow().get("require_manual_confirmation")
    if value is not None:
        return bool(value)

    return False
