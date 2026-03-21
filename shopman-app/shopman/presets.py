"""Channel presets for common sales scenarios.

Each preset returns a validated channel config dict describing how the
ordering pipeline behaves for that channel type (confirmation, payment,
stock holds, etc.).

See the refactoring plan sections 5.1-5.5 for the E2E flows each preset
enables.
"""

from shopman.config import validate_channel_config


def pos(*, stock_hold_ttl=300, **overrides):
    """Point-of-sale / balcão.

    - auto_confirm: True (operador presente, sem espera)
    - payment_mode: counter (síncrono no balcão)
    - stock_hold_ttl: 300s default (curto, cliente presente)
    """
    config = {
        "channel_type": "pos",
        "auto_confirm": True,
        "payment_mode": "counter",
        "stock_hold_ttl": stock_hold_ttl,
        "post_commit_directives": ["stock.hold", "notification.send"],
        "notification_template": "order_confirmed_pos",
        **overrides,
    }
    return validate_channel_config(config)


def remote(*, stock_hold_ttl=None, confirmation_timeout=600, **overrides):
    """Remote / WhatsApp / e-commerce.

    - auto_confirm: True (confirmação otimista — auto se operador não cancela)
    - payment_mode: pix (assíncrono com webhook)
    - stock_hold_ttl: None (sem expiração — hold dura até commit ou cancel)
    - confirmation_timeout: 600s (10 min para operador cancelar)
    """
    config = {
        "channel_type": "remote",
        "auto_confirm": True,
        "payment_mode": "pix",
        "stock_hold_ttl": stock_hold_ttl,
        "confirmation_timeout": confirmation_timeout,
        "post_commit_directives": ["stock.hold", "notification.send"],
        "notification_template": "order_confirmed_remote",
        **overrides,
    }
    return validate_channel_config(config)


def marketplace(*, stock_hold_ttl=None, **overrides):
    """Marketplace (iFood, Rappi, etc.).

    - auto_confirm: True (pedido já vem confirmado e pago)
    - payment_mode: external (já pago pelo marketplace)
    - stock_hold_ttl: None (commit imediato, hold não expira)
    """
    config = {
        "channel_type": "marketplace",
        "auto_confirm": True,
        "payment_mode": "external",
        "stock_hold_ttl": stock_hold_ttl,
        "post_commit_directives": ["notification.send"],
        "notification_template": "order_confirmed_marketplace",
        **overrides,
    }
    return validate_channel_config(config)
