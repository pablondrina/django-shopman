"""Channel configuration validation for the Shopman orchestrator."""

REQUIRED_KEYS = {
    "channel_type",
    "auto_confirm",
    "payment_mode",
    "stock_hold_ttl",
}

VALID_CHANNEL_TYPES = {"pos", "remote", "marketplace"}

VALID_PAYMENT_MODES = {
    "counter",      # pagamento síncrono no balcão (PDV)
    "pix",          # PIX assíncrono com webhook
    "external",     # já pago externamente (marketplace)
}


class ChannelConfigError(Exception):
    """Raised when a channel config is invalid."""


def validate_channel_config(config: dict) -> dict:
    """Validate a channel configuration dict.

    Raises ChannelConfigError if required keys are missing or values are invalid.
    Returns the config unchanged if valid.
    """
    missing = REQUIRED_KEYS - config.keys()
    if missing:
        raise ChannelConfigError(f"Missing required keys: {sorted(missing)}")

    if config["channel_type"] not in VALID_CHANNEL_TYPES:
        raise ChannelConfigError(
            f"Invalid channel_type {config['channel_type']!r}. "
            f"Must be one of {sorted(VALID_CHANNEL_TYPES)}"
        )

    if config["payment_mode"] not in VALID_PAYMENT_MODES:
        raise ChannelConfigError(
            f"Invalid payment_mode {config['payment_mode']!r}. "
            f"Must be one of {sorted(VALID_PAYMENT_MODES)}"
        )

    if not isinstance(config["auto_confirm"], bool):
        raise ChannelConfigError("auto_confirm must be a boolean")

    ttl = config["stock_hold_ttl"]
    if ttl is not None and (not isinstance(ttl, (int, float)) or ttl < 0):
        raise ChannelConfigError("stock_hold_ttl must be a non-negative number or None")

    return config
