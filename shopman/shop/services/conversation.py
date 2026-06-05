"""Conversational projection for WhatsApp/ManyChat and other chat surfaces.

The projection in this module is a compact view over canonical tracking,
payment, and channel policy resolution. It intentionally does not define order
status, payment state, pricing, stock, or availability rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shopman.shop.projections.types import Action
from shopman.shop.services import order_tracking, payment_status
from shopman.shop.services.channel_policy import resolve_channel_policy
from shopman.shop.services.interaction_context import InteractionContext

_PAYMENT_ACTIONS = {"pay_now", "copy_pix", "authorize_card", "pay_card", "retry_payment"}


@dataclass(frozen=True)
class RemoteConversationProjection:
    """Compact customer-facing contract for conversational surfaces."""

    order_ref: str
    order_status: str
    channel_ref: str
    source_projection: str
    state: str
    title: str
    message: str
    tone: str
    actions: tuple[Action, ...]
    deadline_at: str | None
    next_event: str
    recovery: str
    items_summary: tuple[str, ...]
    total_display: str
    tracking_url: str
    payment_url: str | None
    supports_access_link: bool
    requires_payment_gate: bool


def build_order_conversation(
    order: Any,
    *,
    channel_ref: str | None = None,
    is_debug: bool = False,
) -> RemoteConversationProjection:
    """Build a conversation projection from canonical order projections."""

    interaction = InteractionContext.from_order(
        order,
        surface_ref="manychat",
        channel_ref=channel_ref,
    )
    resolved_channel_ref = interaction.channel_ref or "web"
    policy = resolve_channel_policy(resolved_channel_ref)
    tracking = order_tracking.build_tracking(order, is_debug=is_debug)
    payment = _build_payment_if_relevant(order)
    source_projection, promise = _select_conversation_promise(
        tracking=tracking,
        payment=payment,
    )
    tracking_url = f"/pedido/{order.ref}/"
    payment_url = _payment_url(order, payment)
    tracking_actions = _actions(getattr(tracking, "actions", ()))

    return RemoteConversationProjection(
        order_ref=str(getattr(tracking, "order_ref", getattr(order, "ref", ""))),
        order_status=str(getattr(order, "status", "")),
        channel_ref=resolved_channel_ref,
        source_projection=source_projection,
        state=str(getattr(promise, "state", "")),
        title=str(getattr(promise, "title", "")),
        message=str(getattr(promise, "message", "")),
        tone=str(getattr(promise, "tone", "info") or "info"),
        actions=_conversation_actions(
            promise,
            tracking_actions=tracking_actions,
            channel_can_cancel=bool(getattr(policy, "can_cancel", False)),
            channel_can_rate=bool(getattr(policy, "can_rate", False)),
        ),
        deadline_at=getattr(promise, "deadline_at", None),
        next_event=str(getattr(promise, "next_event", "") or ""),
        recovery=str(getattr(promise, "recovery", "") or ""),
        items_summary=_items_summary(getattr(tracking, "items", ())),
        total_display=str(getattr(tracking, "total_display", "")),
        tracking_url=tracking_url,
        payment_url=payment_url,
        supports_access_link=policy.supports_access_link,
        requires_payment_gate=policy.requires_payment_gate,
    )


def _build_payment_if_relevant(order: Any) -> Any | None:
    payment = (getattr(order, "data", None) or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method not in {"pix", "card"}:
        return None
    return payment_status.build_payment(order)


def _select_conversation_promise(*, tracking: Any, payment: Any | None) -> tuple[str, Any]:
    if payment is not None:
        payment_promise = getattr(payment, "promise", None)
        if _has_payment_action(payment_promise):
            return "payment", payment_promise

    return "tracking", tracking.promise


def _payment_url(order: Any, payment: Any | None) -> str | None:
    if payment is None:
        return None
    promise = getattr(payment, "promise", None)
    for action in _promise_actions(promise):
        if action.href and action.ref in _PAYMENT_ACTIONS:
            return action.href
    return f"/pedido/{order.ref}/pagamento/"


def _promise_actions(promise: Any) -> tuple[Action, ...]:
    return _actions(getattr(promise, "actions", ()))


def _actions(actions: Any) -> tuple[Action, ...]:
    return tuple(action for action in (actions or ()) if isinstance(action, Action))


def _conversation_actions(
    promise: Any,
    *,
    tracking_actions: tuple[Action, ...],
    channel_can_cancel: bool,
    channel_can_rate: bool,
) -> tuple[Action, ...]:
    allowed_tracking_refs = set()
    if channel_can_cancel:
        allowed_tracking_refs.add("cancel_order")
    if channel_can_rate:
        allowed_tracking_refs.add("rate_order")

    actions = [
        action
        for action in _promise_actions(promise)
        if action.enabled
    ]
    actions.extend(
        action
        for action in tracking_actions
        if action.enabled and action.ref in allowed_tracking_refs
    )
    return _dedupe_actions(actions)


def _dedupe_actions(actions: list[Action]) -> tuple[Action, ...]:
    seen: set[str] = set()
    deduped: list[Action] = []
    for action in actions:
        if action.ref in seen:
            continue
        seen.add(action.ref)
        deduped.append(action)
    return tuple(deduped)


def _has_payment_action(promise: Any) -> bool:
    return any(action.enabled and action.ref in _PAYMENT_ACTIONS for action in _promise_actions(promise))


def _items_summary(items: Any) -> tuple[str, ...]:
    item_tuple = tuple(items)
    rows = []
    for item in item_tuple[:5]:
        qty = getattr(item, "qty", "")
        name = getattr(item, "name", "")
        if qty and name:
            rows.append(f"{qty}x {name}")
        elif name:
            rows.append(str(name))
    remaining = max(len(item_tuple) - 5, 0)
    if remaining:
        rows.append(f"+{remaining} itens")
    return tuple(rows)
