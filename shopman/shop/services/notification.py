"""
Notification service.

Adapter: get_adapter("notification", channel=...) → notification_manychat / email / console

- send(): ASYNC — cria Directive para processamento posterior pelo handler.
- deliver_order_notification(): SYNC — executa a cadeia de backends diretamente.
  Chamado pelo NotificationSendHandler após resolver o pedido.
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Directive

from shopman.shop.notifications import notify

logger = logging.getLogger(__name__)

TOPIC = "notification.send"


def send(order, template: str) -> None:
    """
    Schedule a notification for the order.

    Creates a Directive with topic="notification.send". The handler that
    processes the Directive resolves the adapter, builds context, and
    executes the fallback chain (manychat → email → console).

    ASYNC — does not block the request.
    """
    payload = {
        "order_ref": order.ref,
        "channel_ref": order.channel_ref or "",
        "template": template,
    }

    # Include origin_channel for routing
    origin = (order.data or {}).get("origin_channel")
    if origin:
        payload["origin_channel"] = origin

    Directive.objects.create(topic=TOPIC, payload=payload)

    logger.info("notification.send: queued %s for order %s", template, order.ref)


def deliver_order_notification(order, template: str, payload: dict) -> tuple[bool, str | None]:
    """
    Entrega uma notificação de pedido para o cliente via cadeia de backends.

    Tenta cada backend na cadeia configurada pelo canal até um ter sucesso.
    Retorna (True, None) no sucesso ou (False, last_error) se todos falharem.

    SYNC — chamado pelo NotificationSendHandler durante o processamento de directives.
    """
    backend_chain = _resolve_backend_chain(order)

    if not backend_chain or backend_chain == ["none"]:
        return True, None

    context = _build_context(order, payload, template)
    template = _qualify_template(template, context)
    context["template"] = template

    last_error: str | None = None
    for backend_name in backend_chain:
        if backend_name == "none":
            continue

        recipient = _resolve_recipient(order, backend_name)
        if not recipient:
            last_error = f"No recipient for backend {backend_name}"
            continue

        if backend_name == "manychat" and order.handle_type == "manychat":
            context["subscriber_id"] = order.handle_ref

        result = notify(event=template, recipient=recipient, context=context, backend=backend_name)

        if result.success:
            return True, None

        last_error = result.error or "unknown"
        logger.info(
            "notification backend %s failed for order %s, trying next in chain",
            backend_name, order.ref,
        )

    return False, last_error


# ── private helpers ──


def _resolve_backend_chain(order) -> list[str]:
    """Resolve a cadeia de backends via ChannelConfig cascade."""
    from shopman.shop.config import ChannelConfig

    notifications = ChannelConfig.for_channel(order.channel_ref).notifications
    backend = notifications.backend or "manychat"
    chain = notifications.fallback_chain or []
    return [backend] + [b for b in chain if b != backend]


def _build_context(order, payload: dict, template: str) -> dict:
    """Constrói contexto de notificação a partir dos dados do pedido."""
    fulfillment_type = order.data.get("fulfillment_type", "pickup")

    context = {
        "order_ref": payload.get("order_ref"),
        "template": template,
        "order_status": order.status,
        "total_q": order.total_q,
        "items": order.snapshot.get("items", []),
        "reason": payload.get("reason"),
        "fulfillment_type": fulfillment_type,
        "outside_business_hours": bool(order.data.get("outside_business_hours", False)),
    }

    customer_data = order.data.get("customer", {})
    if isinstance(customer_data, dict):
        context["customer_name"] = customer_data.get("name", "")
    context["customer_phone"] = (
        customer_data.get("phone", "") if isinstance(customer_data, dict) else ""
    )

    customer_uuid = customer_data.get("uuid") if isinstance(customer_data, dict) else None
    if customer_uuid:
        try:
            from uuid import UUID

            from shopman.doorman.protocols.customer import AuthCustomerInfo
            from shopman.shop.services.access_urls import build_reorder_access_url, build_tracking_access_url

            auth_customer = AuthCustomerInfo(
                uuid=UUID(str(customer_uuid)),
                name=customer_data.get("name", ""),
                phone=customer_data.get("phone"),
                email=customer_data.get("email"),
                is_active=True,
            )
            order_ref = payload.get("order_ref") or order.ref
            context["tracking_url"] = build_tracking_access_url(None, auth_customer, order_ref)
            context["reorder_url"] = build_reorder_access_url(None, auth_customer, order_ref)
        except Exception:
            logger.debug("access_urls: could not build tracking/reorder URLs", exc_info=True)

    if order.total_q:
        context["total"] = f"R$ {order.total_q / 100:,.2f}"

    payment = order.data.get("payment")
    if payment:
        context["payment"] = payment

    return context


def _qualify_template(template: str, context: dict) -> str:
    """
    Qualifica o nome do template com base em atributos do pedido.

    order_ready → order_ready_pickup ou order_ready_delivery
    order_received → order_received_outside_hours (quando a flag está ativa),
        degrada silenciosamente pro `order_received` se a variante não existir.
    """
    if template in ("order_ready", "order.ready"):
        ft = context.get("fulfillment_type", "pickup")
        suffix = "delivery" if ft == "delivery" else "pickup"
        return f"{template}_{suffix}"
    if template == "order_received" and context.get("outside_business_hours"):
        from shopman.shop.models import NotificationTemplate
        variant = "order_received_outside_hours"
        if NotificationTemplate.objects.filter(event=variant, is_active=True).exists():
            return variant
    return template


def _resolve_recipient(order, backend_name: str = "") -> str | None:
    """
    Resolve o destinatário com base no tipo de backend.

    manychat → handle_ref (subscriber_id) ou phone
    email    → email ou phone
    sms      → phone
    console  → phone ou qualquer identificador
    """
    customer_data = order.data.get("customer", {})
    if not isinstance(customer_data, dict):
        customer_data = {}

    if backend_name == "manychat":
        if order.handle_type == "manychat" and order.handle_ref:
            return order.handle_ref
        return customer_data.get("phone") or order.data.get("customer_phone")

    if backend_name == "email":
        email = customer_data.get("email")
        if email:
            return email
        return customer_data.get("phone") or order.data.get("customer_phone")

    return (
        customer_data.get("phone")
        or order.data.get("customer_phone")
        or (order.handle_ref if order.handle_type in ("customer", "phone") else None)
    )
