"""Shopman orchestration — channel presets and provisioning.

Provides:
- Channel preset definitions (pos, remote, marketplace)
- ``setup_channels`` helper for bootstrapping default channels

Handler and validator registration is handled by each module's AppConfig.ready()
(e.g. InventoryConfig, NotificationsConfig, PaymentConfig, ConfirmationConfig).
"""

from __future__ import annotations

from shopman import presets
from shopman.channels import ensure_channel


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
