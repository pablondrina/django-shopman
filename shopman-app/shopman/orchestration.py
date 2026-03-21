"""Shopman orchestration — connects presets and business rules to the ordering kernel.

This module is imported by ShopmanConfig.ready() and is responsible for:
- Registering channel presets as Channel provisioning helpers
- Registering any shopman-level validators/modifiers/handlers with the ordering registry
- Providing the ``setup_channels`` helper for bootstrapping default channels

The orchestrator does NOT register handlers at import time.  Registration
happens lazily when ``setup_channels`` is called (e.g. via management command
or data migration).
"""

from __future__ import annotations

from shopman import presets
from shopman.channels import ensure_channel
from shopman.ordering import registry


# ---------------------------------------------------------------------------
# Extensions — register handlers, validators, etc. once
# ---------------------------------------------------------------------------

_extensions_registered = False


def register_extensions():
    """Register all shopman directive handlers and commit validators.

    Safe to call multiple times — registrations are idempotent.
    """
    global _extensions_registered
    if _extensions_registered:
        return

    from shopman.contrib.stock_handler import StockHoldHandler
    from shopman.contrib.stock_validator import StockCheckValidator
    from shopman.contrib.notification_handler import NotificationHandler

    registry.register_directive_handler(StockHoldHandler())
    registry.register_directive_handler(NotificationHandler())
    registry.register_validator(StockCheckValidator())
    _extensions_registered = True


# Backward-compat alias
register_stock_extensions = register_extensions


# ---------------------------------------------------------------------------
# Preset registry — maps preset name → callable
# ---------------------------------------------------------------------------

PRESETS = {
    "pos": presets.pos,
    "remote": presets.remote,
    "marketplace": presets.marketplace,
}


# ---------------------------------------------------------------------------
# Default channel definitions
# ---------------------------------------------------------------------------

DEFAULT_CHANNELS = [
    {
        "ref": "pos",
        "name": "Balcão / PDV",
        "preset": "pos",
        "config_extras": {
            "icon": "point_of_sale",
            "terminology": {"order": "Comanda", "order_plural": "Comandas"},
        },
        "channel_defaults": {
            "pricing_policy": "internal",
            "edit_policy": "open",
            "display_order": 10,
        },
    },
    {
        "ref": "remote",
        "name": "Remoto / WhatsApp",
        "preset": "remote",
        "config_extras": {
            "icon": "smartphone",
        },
        "channel_defaults": {
            "pricing_policy": "internal",
            "edit_policy": "open",
            "display_order": 20,
        },
    },
    {
        "ref": "marketplace",
        "name": "Marketplace",
        "preset": "marketplace",
        "config_extras": {
            "icon": "storefront",
        },
        "channel_defaults": {
            "pricing_policy": "external",
            "edit_policy": "locked",
            "display_order": 30,
        },
    },
]


def setup_channels(channel_defs=None):
    """Provision default Channels from preset definitions.

    Parameters
    ----------
    channel_defs : list[dict] | None
        Channel definitions to provision.  Falls back to ``DEFAULT_CHANNELS``.

    Returns
    -------
    list[tuple[Channel, bool]]
        List of (channel, created) tuples.
    """
    register_extensions()

    defs = channel_defs if channel_defs is not None else DEFAULT_CHANNELS
    results = []

    for ch_def in defs:
        preset_name = ch_def["preset"]
        preset_fn = PRESETS[preset_name]
        preset_config = preset_fn()

        # Merge any extra config keys (icon, terminology, etc.)
        channel_defaults = dict(ch_def.get("channel_defaults", {}))
        channel_defaults["config"] = dict(ch_def.get("config_extras", {}))

        channel, created = ensure_channel(
            ref=ch_def["ref"],
            name=ch_def.get("name", ""),
            preset_config=preset_config,
            channel_defaults=channel_defaults,
        )
        results.append((channel, created))

    return results
