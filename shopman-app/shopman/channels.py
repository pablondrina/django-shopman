"""Channel provisioning — creates or updates ordering Channels from presets.

The orchestrator layer bridges shopman presets (business config) to the
ordering kernel's Channel model.  Preset configs carry shopman-specific
keys (channel_type, payment_mode, etc.) that are stored inside the
Channel.config JSONField under the "preset" umbrella key so the kernel
never needs to interpret them.
"""

from __future__ import annotations

from shopman.ordering.models import Channel


def ensure_channel(
    *,
    ref: str,
    name: str = "",
    preset_config: dict,
    channel_defaults: dict | None = None,
) -> tuple[Channel, bool]:
    """Create or update a Channel with the given preset configuration.

    Parameters
    ----------
    ref : str
        Unique channel identifier (e.g. "pos", "remote-wpp").
    name : str
        Display name for the channel.
    preset_config : dict
        Validated config dict returned by a preset function
        (``shopman.presets.pos()``, etc.).
    channel_defaults : dict | None
        Extra keyword defaults forwarded to Channel fields
        (pricing_policy, edit_policy, display_order, …).

    Returns
    -------
    tuple[Channel, bool]
        (channel, created) — same semantics as ``update_or_create``.
    """
    defaults = dict(channel_defaults or {})
    defaults["name"] = name

    # Build the Channel.config merging preset info with any extra
    # config keys the caller may want (icon, terminology, etc.)
    config = dict(defaults.pop("config", {}))
    config["preset"] = preset_config.get("channel_type", "custom")
    config["payment"] = {
        "mode": preset_config.get("payment_mode"),
    }
    config["confirmation_flow"] = {
        "auto_confirm": preset_config.get("auto_confirm", True),
        "timeout": preset_config.get("confirmation_timeout"),
    }
    config["stock"] = {
        "hold_ttl": preset_config.get("stock_hold_ttl"),
    }
    if "post_commit_directives" in preset_config:
        config["post_commit_directives"] = preset_config["post_commit_directives"]
    if "notification_template" in preset_config:
        config["notification_template"] = preset_config["notification_template"]
    defaults["config"] = config

    channel, created = Channel.objects.update_or_create(
        ref=ref,
        defaults=defaults,
    )
    return channel, created
