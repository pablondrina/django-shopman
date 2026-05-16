"""
Notification service.

Adapter: get_adapter("notification", channel=...) → notification_manychat / email / console

- send(): ASYNC — cria Directive para processamento posterior pelo handler.
- deliver_order_notification(): SYNC — executa a cadeia de backends diretamente.
  Chamado pelo NotificationSendHandler após resolver o pedido.
"""

from __future__ import annotations

import logging

from django.conf import settings
from shopman.orderman.models import Directive

from shopman.shop.notifications import notify

logger = logging.getLogger(__name__)

TOPIC = "notification.send"

_ACTIVE_NOTIFICATION_TEMPLATES = frozenset(
    {
        "payment_requested",
        "payment_expired",
        "payment_failed",
        "order_ready",
        "order_ready_pickup",
        "order_ready_delivery",
        "order_dispatched",
        "order_delivered",
        "order_cancelled",
        "order_rejected",
    }
)

_BACKEND_CHANNELS = {
    "manychat": "whatsapp",
    "sms": "sms",
    "email": "email",
    "push": "push",
    "webhook": "webhook",
    "console": "console",
}

_ORIGIN_CHANNELS = {"whatsapp", "instagram", "web"}


def send(order, template: str, **extra) -> None:
    """
    Schedule a notification for the order.

    Creates a Directive with topic="notification.send". The handler that
    processes the Directive resolves the adapter, builds context, and
    executes the configured fallback chain (for example, manychat → sms → email).

    ASYNC — does not block the request.
    """
    template = _canonical_template(template)
    dedupe_key = _dedupe_key(order, template)
    existing = (
        Directive.objects.filter(
            topic=TOPIC,
            dedupe_key=dedupe_key,
            status__in=("queued", "running", "done"),
        )
        .order_by("-created_at")
        .first()
    )
    if existing:
        logger.info(
            "notification.send: skipped duplicate %s for order %s",
            template,
            order.ref,
        )
        return

    payload = {
        "order_ref": order.ref,
        "channel_ref": order.channel_ref or "",
        "template": template,
        "requires_active_notification": _requires_active_notification(template),
    }
    payload.update(extra)

    # Include origin_channel for routing
    origin = (order.data or {}).get("origin_channel")
    if origin in _ORIGIN_CHANNELS:
        payload["origin_channel"] = origin

    customer_ref = _customer_ref(order)
    if customer_ref:
        payload["customer_ref"] = customer_ref

    Directive.objects.create(topic=TOPIC, payload=payload, dedupe_key=dedupe_key)

    logger.info("notification.send: queued %s for order %s", template, order.ref)


def deliver_order_notification(order, template: str, payload: dict) -> tuple[bool, str | None]:
    """
    Entrega uma notificação de pedido para o cliente via cadeia de backends.

    Tenta cada backend na cadeia configurada pelo canal até um ter sucesso.
    Retorna (True, None) no sucesso ou (False, last_error) se todos falharem.

    SYNC — chamado pelo NotificationSendHandler durante o processamento de directives.
    """
    template = _canonical_template(template)
    backend_chain = _resolve_backend_chain(order)
    requires_active = _requires_active_notification(template, payload=payload)
    backend_chain = _filter_backend_chain(
        order,
        backend_chain,
        payload=payload,
        requires_active=requires_active,
    )

    if not backend_chain or backend_chain == ["none"]:
        if requires_active:
            return False, "no active notification channel available"
        return True, None

    context = _build_context(order, payload, template)
    template = _qualify_template(template, context)
    context["template"] = template

    last_error: str | None = None
    any_attempted = False
    for backend_name in backend_chain:
        if backend_name == "none":
            continue

        recipient = _resolve_recipient(order, backend_name)
        if not recipient:
            logger.debug("notification.deliver: no recipient for backend=%s order=%s, skipping", backend_name, order.ref)
            continue

        from shopman.shop.notifications import get_backend as _get_backend
        backend_module = _get_backend(backend_name)
        if backend_module and hasattr(backend_module, "is_available"):
            if not backend_module.is_available():
                logger.debug(
                    "notification.deliver: backend=%s not configured, skipping order=%s",
                    backend_name, order.ref,
                )
                continue

        any_attempted = True

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

    if not any_attempted:
        # No recipient for any backend — notifications not configured, not a failure.
        if requires_active:
            logger.warning(
                "notification.deliver: active notification has no recipient order=%s template=%s",
                order.ref,
                template,
            )
            return False, "no active notification recipient available"
        logger.info("notification.deliver: no recipient for any backend, skipping order=%s template=%s", order.ref, template)
        return True, None

    return False, last_error


# ── private helpers ──


def _resolve_backend_chain(order) -> list[str]:
    """Resolve a cadeia de backends via ChannelConfig cascade."""
    from shopman.shop.config import ChannelConfig

    notifications = ChannelConfig.for_channel(order.channel_ref).notifications
    backend = notifications.backend or "manychat"
    chain = notifications.fallback_chain or []
    return [backend] + [b for b in chain if b != backend]


def _filter_backend_chain(
    order,
    backend_chain: list[str],
    *,
    payload: dict,
    requires_active: bool,
) -> list[str]:
    """
    Keep notification routing aligned with customer channel preferences.

    If a customer is known, enabled consents define the active channels. A
    WhatsApp-origin order may still use WhatsApp as the transactional channel
    for the current order even when persisted consent is absent. Critical
    updates without any active route are allowed to fail loudly so the handler
    can retry/escalate instead of creating a silent promise break.
    """
    customer_ref = payload.get("customer_ref") or _customer_ref(order)
    if not customer_ref:
        return backend_chain

    available_channels = tuple(
        sorted(
            {
                channel
                for backend in backend_chain
                for channel in [_BACKEND_CHANNELS.get(backend)]
                if channel and channel not in {"console", "webhook"}
            }
        )
    )
    enabled_channels = _enabled_notification_channels(customer_ref, available_channels)
    allowed_channels = set(enabled_channels)

    origin = payload.get("origin_channel") or (order.data or {}).get("origin_channel") or ""
    if origin == "whatsapp":
        allowed_channels.add("whatsapp")

    if not allowed_channels and _dev_console_allowed(backend_chain):
        return [backend for backend in backend_chain if backend == "console"]

    if not allowed_channels:
        return []

    filtered: list[str] = []
    for backend in backend_chain:
        channel = _BACKEND_CHANNELS.get(backend)
        if channel in allowed_channels:
            filtered.append(backend)
    return filtered


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

            from shopman.shop.services.access_urls import (
                build_payment_access_url,
                build_reorder_access_url,
                build_tracking_access_url,
            )

            auth_customer = AuthCustomerInfo(
                uuid=UUID(str(customer_uuid)),
                name=customer_data.get("name", ""),
                phone=customer_data.get("phone"),
                email=customer_data.get("email"),
                is_active=True,
            )
            order_ref = payload.get("order_ref") or order.ref
            context["tracking_url"] = build_tracking_access_url(None, auth_customer, order_ref)
            context["payment_url"] = build_payment_access_url(None, auth_customer, order_ref)
            context["reorder_url"] = build_reorder_access_url(None, auth_customer, order_ref)
        except Exception:
            logger.debug("access_urls: could not build tracking/reorder URLs", exc_info=True)

    if order.total_q:
        context["total"] = f"R$ {order.total_q / 100:,.2f}"

    payment = order.data.get("payment")
    if payment:
        context["payment"] = payment
        context["payment_url"] = context.get("payment_url") or f"/pedido/{order.ref}/pagamento/"
        copy_paste = payment.get("copy_paste")
        context["copy_paste"] = copy_paste or ""
        context["pix_suffix"] = f" Codigo PIX: {copy_paste}" if copy_paste else ""
    else:
        context["payment_url"] = context.get("payment_url") or f"/pedido/{order.ref}/pagamento/"
        context["pix_suffix"] = ""

    return context


def _qualify_template(template: str, context: dict) -> str:
    """
    Qualifica o nome do template com base em atributos do pedido.

    order_ready → order_ready_pickup ou order_ready_delivery
    order_received → order_received_outside_hours (quando a flag está ativa),
        degrada silenciosamente pro `order_received` se a variante não existir.
    """
    template = _canonical_template(template)
    if template == "order_ready":
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
    email    → email
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
        return email or None

    return (
        customer_data.get("phone")
        or order.data.get("customer_phone")
        or (order.handle_ref if order.handle_type in ("customer", "phone") else None)
    )


def _canonical_template(template: str) -> str:
    return str(template or "").strip()


def _requires_active_notification(template: str, *, payload: dict | None = None) -> bool:
    if payload and payload.get("requires_active_notification") is True:
        return True
    return _canonical_template(template) in _ACTIVE_NOTIFICATION_TEMPLATES


def _dedupe_key(order, template: str) -> str:
    return f"{TOPIC}:{order.ref}:{_canonical_template(template)}"


def _customer_ref(order) -> str:
    data = order.data or {}
    customer_ref = data.get("customer_ref")
    if customer_ref:
        return str(customer_ref)

    customer_data = data.get("customer", {})
    if not isinstance(customer_data, dict):
        customer_data = {}
    if customer_data.get("ref"):
        return str(customer_data["ref"])

    customer_uuid = customer_data.get("uuid")
    if customer_uuid:
        try:
            from shopman.shop.services import customer_context

            resolved = customer_context.customer_ref_by_uuid(customer_uuid)
            if resolved:
                return str(resolved)
        except Exception:
            logger.debug("notification.customer_ref_uuid_lookup_failed order=%s", order.ref, exc_info=True)

    phone = customer_data.get("phone") or data.get("customer_phone")
    if phone:
        try:
            from shopman.guestman.services import customer as customer_service

            customer = customer_service.get_by_phone(phone)
            if customer:
                return str(customer.ref)
        except Exception:
            logger.debug("notification.customer_ref_phone_lookup_failed order=%s", order.ref, exc_info=True)

    return ""


def _enabled_notification_channels(customer_ref: str, channels: tuple[str, ...]) -> frozenset[str]:
    if not channels:
        return frozenset()
    try:
        from shopman.shop.services import customer_context

        return customer_context.enabled_notification_channels(customer_ref, channels)
    except Exception:
        logger.debug(
            "notification.enabled_channels_failed customer=%s",
            customer_ref,
            exc_info=True,
        )
        return frozenset()


def _dev_console_allowed(backend_chain: list[str]) -> bool:
    return bool(getattr(settings, "DEBUG", False) and "console" in backend_chain)
