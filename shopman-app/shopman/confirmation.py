"""
Confirmation flow configuration helpers.

Resolve configuração via ChannelConfig.effective() quando possível,
com fallback para cascata legada (channel.config dict → settings.CONFIRMATION_FLOW).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings


def _get_effective_config(channel: Any):
    """Try ChannelConfig.effective(), return None on failure."""
    try:
        from shopman.config import ChannelConfig
        return ChannelConfig.effective(channel)
    except Exception:
        return None


# ── Hardcoded defaults (último recurso) ──

DEFAULT_CONFIRMATION_TIMEOUT_MINUTES = 5
DEFAULT_PIX_PAYMENT_TIMEOUT_MINUTES = 10
DEFAULT_HOLD_EXPIRATION_MINUTES = 20
DEFAULT_SAFETY_MARGIN = 0


# ── Legacy cascade (fallback) ──

def _cascade(
    channel: Any,
    config_path: tuple[str, ...],
    settings_key: str | None = None,
    default: Any = None,
) -> Any:
    """Cascata legada: channel.config → settings.CONFIRMATION_FLOW → default."""
    value = _deep_get(channel.config or {}, config_path)
    if value is not None:
        return value

    sf = getattr(settings, "CONFIRMATION_FLOW", {})
    key = settings_key or config_path[-1]
    if key in sf:
        return sf[key]

    return default


def _deep_get(d: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(key)
        if d is None:
            return None
    return d


# ── Public API ──

def get_confirmation_timeout(channel: Any) -> int:
    """Retorna timeout de confirmação do operador em minutos."""
    cfg = _get_effective_config(channel)
    if cfg:
        return cfg.confirmation.timeout_minutes
    return int(
        _cascade(channel, ("confirmation_flow", "confirmation_timeout_minutes"),
                 default=DEFAULT_CONFIRMATION_TIMEOUT_MINUTES)
    )


def get_pix_timeout(channel: Any) -> int:
    """Retorna timeout de pagamento PIX em minutos."""
    cfg = _get_effective_config(channel)
    if cfg:
        return cfg.payment.timeout_minutes
    return int(
        _cascade(channel, ("confirmation_flow", "pix_payment_timeout_minutes"),
                 default=DEFAULT_PIX_PAYMENT_TIMEOUT_MINUTES)
    )


def get_hold_expiration(channel: Any) -> int:
    """Retorna TTL do hold de checkout em minutos."""
    cfg = _get_effective_config(channel)
    if cfg and cfg.stock.hold_ttl_minutes is not None:
        return cfg.stock.hold_ttl_minutes
    return int(
        _cascade(channel, ("stock", "checkout_hold_expiration_minutes"),
                 default=DEFAULT_HOLD_EXPIRATION_MINUTES)
    )


def calculate_hold_ttl(channel: Any) -> timedelta:
    """
    Calcula TTL do hold garantindo que cobre todo o ciclo.

    Hold TTL = max(configurado, confirmação + pagamento + 5 min margem)
    """
    configured = get_hold_expiration(channel)
    confirm = get_confirmation_timeout(channel)
    pix = get_pix_timeout(channel)
    minimum = confirm + pix + 5

    return timedelta(minutes=max(configured, minimum))


def get_safety_margin(channel: Any, product_data: dict | None = None) -> int:
    """
    Retorna margem de segurança (unidades de buffer).

    Cascata: product → ChannelConfig.stock.safety_margin → legacy → 0.
    """
    if product_data and "safety_margin" in product_data:
        return int(product_data["safety_margin"])

    cfg = _get_effective_config(channel)
    if cfg and cfg.stock.safety_margin:
        return cfg.stock.safety_margin

    return int(
        _cascade(channel, ("stock", "safety_margin_default"),
                 settings_key="default_safety_margin", default=DEFAULT_SAFETY_MARGIN)
    )


def requires_manual_confirmation(channel: Any) -> bool:
    """Retorna se o canal requer confirmação manual do operador."""
    cfg = _get_effective_config(channel)
    if cfg:
        return cfg.confirmation.mode == "optimistic" or cfg.confirmation.mode == "manual"
    return bool(
        _cascade(channel, ("confirmation_flow", "require_manual_confirmation"),
                 default=False)
    )
