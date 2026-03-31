"""
Channel presets — templates de canal para cenários comuns.

Cada preset retorna um dict (ChannelConfig serializado) pronto para
armazenar em Channel.config.

Presets disponíveis:

  pos()         — Balcão. Operador presente, pagamento no caixa.
  remote()      — E-commerce/WhatsApp. PIX assíncrono, confirmação otimista.
  marketplace() — iFood/Rappi. Já pago e confirmado pelo marketplace.

Cascata de configuração:
  Channel.config  ←  Shop.defaults  ←  ChannelConfig.defaults()
"""

from __future__ import annotations

from channels.config import ChannelConfig
from channels.topics import (
    CHECKOUT_INFER_DEFAULTS,
    CUSTOMER_ENSURE,
    FULFILLMENT_CREATE,
    LOYALTY_EARN,
    NOTIFICATION_SEND,
    PIX_GENERATE,
    STOCK_COMMIT,
    STOCK_HOLD,
    STOCK_RELEASE,
)


def pos() -> dict:
    """
    Balcão — operador presente, pagamento no caixa.

    Pipeline:
      on_commit:     customer.ensure
      on_confirmed:  stock.commit → notification (order_confirmed)
      on_processing: notification (order_processing)
      on_cancelled:  notification (order_cancelled)

    Confirmação: immediate (auto-confirma no commit)
    Pagamento:   counter (síncrono, sem webhook)
    Stock:       hold TTL de 5 min (operação rápida)
    """
    return ChannelConfig(
        confirmation=ChannelConfig.Confirmation(mode="immediate"),
        payment=ChannelConfig.Payment(method="counter"),
        stock=ChannelConfig.Stock(hold_ttl_minutes=5),
        pipeline=ChannelConfig.Pipeline(
            on_commit=[CUSTOMER_ENSURE],
            on_confirmed=[STOCK_COMMIT, f"{NOTIFICATION_SEND}:order_confirmed"],
            on_processing=[f"{NOTIFICATION_SEND}:order_processing"],
            on_completed=[LOYALTY_EARN],
            on_cancelled=[f"{NOTIFICATION_SEND}:order_cancelled"],
        ),
        notifications=ChannelConfig.Notifications(backend="console", fallback_chain=[]),
        rules=ChannelConfig.Rules(
            validators=["business_hours"],
            modifiers=["shop.employee_discount"],
        ),
    ).to_dict()


def remote() -> dict:
    """
    Remoto — e-commerce, WhatsApp. PIX, confirmação otimista.

    Pipeline:
      on_commit:             customer.ensure → stock.hold
      on_confirmed:          pix.generate → notification (order_confirmed)
      on_payment_confirmed:  stock.commit → notification (payment_confirmed)
      on_processing:         notification (order_processing)
      on_ready:              fulfillment.create → notification (order_ready)
      on_dispatched:         notification (order_dispatched)
      on_delivered:          notification (order_delivered)
      on_cancelled:          stock.release → notification (order_cancelled)

    Confirmação: optimistic (5 min timeout, auto-confirma se operador não cancela)
    Pagamento:   pix (15 min timeout, webhook Efi/Stripe)
    Stock:       hold 30 min + planned holds 48h + safety margin 10 unidades
    Fulfillment: auto_sync_fulfillment ativado (fulfillment → order status)
    """
    return ChannelConfig(
        confirmation=ChannelConfig.Confirmation(mode="optimistic", timeout_minutes=5),
        payment=ChannelConfig.Payment(method=["pix", "card"], timeout_minutes=15),
        stock=ChannelConfig.Stock(
            hold_ttl_minutes=30,
            safety_margin=10,
            planned_hold_ttl_hours=48,
            allowed_positions=["estoque", "vitrine", "producao"],
        ),
        pipeline=ChannelConfig.Pipeline(
            on_commit=[CUSTOMER_ENSURE, STOCK_HOLD, CHECKOUT_INFER_DEFAULTS],
            on_confirmed=[PIX_GENERATE, f"{NOTIFICATION_SEND}:order_confirmed"],
            on_payment_confirmed=[STOCK_COMMIT, f"{NOTIFICATION_SEND}:payment_confirmed"],
            on_processing=[f"{NOTIFICATION_SEND}:order_processing"],
            on_ready=[FULFILLMENT_CREATE, f"{NOTIFICATION_SEND}:order_ready"],
            on_dispatched=[f"{NOTIFICATION_SEND}:order_dispatched"],
            on_delivered=[f"{NOTIFICATION_SEND}:order_delivered"],
            on_completed=[LOYALTY_EARN],
            on_cancelled=[STOCK_RELEASE, f"{NOTIFICATION_SEND}:order_cancelled"],
        ),
        notifications=ChannelConfig.Notifications(
            backend="manychat",
            fallback_chain=["sms", "email"],
        ),
        rules=ChannelConfig.Rules(
            validators=["business_hours", "min_order"],
            modifiers=["shop.discount", "shop.happy_hour"],
            checks=["stock"],
        ),
        flow=ChannelConfig.Flow(auto_sync_fulfillment=True),
    ).to_dict()


def marketplace() -> dict:
    """
    Marketplace — iFood, Rappi. Já pago, já confirmado.

    Pipeline:
      on_commit:     customer.ensure
      on_confirmed:  stock.commit

    Confirmação: immediate (marketplace já confirmou)
    Pagamento:   external (marketplace já cobrou)
    Stock:       sem hold TTL (marketplace garante pagamento)
    Notificações: desabilitadas (marketplace notifica o cliente)
    """
    return ChannelConfig(
        confirmation=ChannelConfig.Confirmation(mode="immediate"),
        payment=ChannelConfig.Payment(method="external"),
        pipeline=ChannelConfig.Pipeline(
            on_commit=[CUSTOMER_ENSURE],
            on_confirmed=[STOCK_COMMIT],
        ),
        notifications=ChannelConfig.Notifications(backend="none", fallback_chain=[]),
        rules=ChannelConfig.Rules(validators=[], modifiers=[]),
    ).to_dict()
