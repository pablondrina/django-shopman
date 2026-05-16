"""Reorder projections shared by storefront surfaces."""

from __future__ import annotations

from dataclasses import dataclass

from django.http import HttpRequest

from shopman.shop.projections.types import SurfaceActionProjection
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.projections.cart import CartProjection, build_cart
from shopman.storefront.projections.home import CopyEntryProjection


@dataclass(frozen=True)
class ReorderConflictItemProjection:
    sku: str
    name: str
    qty: int


@dataclass(frozen=True)
class ReorderConflictCopyProjection:
    title: CopyEntryProjection
    message: CopyEntryProjection
    current_cart_label: CopyEntryProjection
    previous_order_label: CopyEntryProjection
    append_help: CopyEntryProjection
    replace_help: CopyEntryProjection
    replace_ack_label: CopyEntryProjection
    cancel_label: CopyEntryProjection


@dataclass(frozen=True)
class ReorderConflictProjection:
    detail: str
    error_code: str
    order_ref: str
    cart: CartProjection
    items: tuple[ReorderConflictItemProjection, ...]
    copy: ReorderConflictCopyProjection
    actions: tuple[SurfaceActionProjection, ...]


def build_reorder_conflict(request: HttpRequest, order, *, order_ref: str | None = None) -> ReorderConflictProjection:
    from shopman.shop.omotenashi import OmotenashiContext

    omotenashi = OmotenashiContext.from_request(request)
    copy = _copy(omotenashi.moment, omotenashi.audience)
    ref = order_ref or str(order.ref)
    append_label = copy_entry("REORDER_CONFLICT_APPEND_LABEL", omotenashi.moment, omotenashi.audience)
    replace_label = copy_entry("REORDER_CONFLICT_REPLACE_LABEL", omotenashi.moment, omotenashi.audience)

    return ReorderConflictProjection(
        detail=copy.message.message or "Escolha como deseja repetir este pedido.",
        error_code="cart_not_empty",
        order_ref=ref,
        cart=build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF),
        items=_snapshot_items(order),
        copy=copy,
        actions=(
            SurfaceActionProjection(
                ref="reorder_append",
                kind="mutation",
                label=append_label.title or "Adicionar ao carrinho atual",
                priority="primary",
                href=f"/api/v1/orders/{ref}/reorder/",
                method="POST",
                payload_schema={
                    "type": "object",
                    "required": ["mode", "idempotency_key"],
                    "properties": {
                        "mode": {"type": "string", "const": "append"},
                        "idempotency_key": {"type": "string"},
                    },
                },
                idempotency="required",
            ),
            SurfaceActionProjection(
                ref="reorder_replace",
                kind="mutation",
                label=replace_label.title or "Substituir carrinho",
                priority="danger",
                href=f"/api/v1/orders/{ref}/reorder/",
                method="POST",
                payload_schema={
                    "type": "object",
                    "required": ["mode", "idempotency_key"],
                    "properties": {
                        "mode": {"type": "string", "const": "replace"},
                        "idempotency_key": {"type": "string"},
                    },
                },
                idempotency="required",
                confirmation={
                    "title": replace_label.title or "Substituir carrinho",
                    "message": copy.replace_help.message,
                    "confirm_label": replace_label.title or "Substituir carrinho",
                    "severity": "danger",
                },
            ),
        ),
    )


def _copy(moment: str, audience: str) -> ReorderConflictCopyProjection:
    return ReorderConflictCopyProjection(
        title=copy_entry("REORDER_CONFLICT_TITLE", moment, audience),
        message=copy_entry("REORDER_CONFLICT_MESSAGE", moment, audience),
        current_cart_label=copy_entry("REORDER_CONFLICT_CURRENT_CART_LABEL", moment, audience),
        previous_order_label=copy_entry("REORDER_CONFLICT_PREVIOUS_ORDER_LABEL", moment, audience),
        append_help=copy_entry("REORDER_CONFLICT_APPEND_HELP", moment, audience),
        replace_help=copy_entry("REORDER_CONFLICT_REPLACE_HELP", moment, audience),
        replace_ack_label=copy_entry("REORDER_CONFLICT_REPLACE_ACK_LABEL", moment, audience),
        cancel_label=copy_entry("REORDER_CONFLICT_CANCEL_LABEL", moment, audience),
    )


def copy_entry(key: str, moment: str, audience: str) -> CopyEntryProjection:
    from shopman.shop.omotenashi import resolve_copy

    entry = resolve_copy(key, moment=moment, audience=audience)
    return CopyEntryProjection(title=entry.title, message=entry.message)


def _snapshot_items(order) -> tuple[ReorderConflictItemProjection, ...]:
    snapshot_items = (order.snapshot or {}).get("items") or []
    if snapshot_items:
        return tuple(
            ReorderConflictItemProjection(
                sku=str(item.get("sku")),
                name=str(item.get("name") or item.get("sku")),
                qty=int(item.get("qty", 1) or 1),
            )
            for item in snapshot_items
            if item.get("sku")
        )

    return tuple(
        ReorderConflictItemProjection(
            sku=str(item.sku),
            name=str(item.name or item.sku),
            qty=int(item.qty or 1),
        )
        for item in order.items.all()
        if item.sku
    )
