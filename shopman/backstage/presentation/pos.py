"""POS HTMX fragment view-models.

The POS surface answers many small requests with HTML fragments (errors, the
sale-confirmed banner, the customer chip, tab status, cash messages). Each shape
below is a frozen view-model carrying exactly what its template renders — including
the ``data-*`` attributes the Alpine client reads back after a swap. The view
builds one of these, then renders ``frag.TEMPLATE``; transport concerns (HTTP
status, ``HX-Trigger``) stay in the view.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import ClassVar

from shopman.utils.monetary import format_money

_FRAGMENTS = "pos/partials/fragments"


# ── Error / sale banners ─────────────────────────────────────────────


@dataclass(frozen=True)
class PosErrorFragment:
    """A danger banner. ``code``/``focus``/``field`` feed the client's error focus."""

    TEMPLATE: ClassVar[str] = f"{_FRAGMENTS}/error_banner.html"
    title: str
    detail: str = ""
    recovery: str = ""
    code: str = ""
    focus: str = ""
    field: str = ""


def intent_error(exc) -> PosErrorFragment:
    """Shape a :class:`PosIntentError` into the validation banner."""
    return PosErrorFragment(
        title=exc.message,
        recovery=exc.recovery or "Corrija os dados destacados e tente novamente.",
        code=exc.code,
        focus=exc.focus,
        field=exc.field,
    )


def cash_shift_required() -> PosErrorFragment:
    return PosErrorFragment(
        title="Abra o caixa antes de finalizar uma venda.",
        recovery="Abra um turno de caixa neste terminal e tente novamente.",
        code="cash_shift_required",
        focus="cash",
        field="cash_shift_id",
    )


def empty_cart() -> PosErrorFragment:
    return PosErrorFragment(title="Carrinho vazio — adicione produtos antes de fechar.")


def invalid_payload() -> PosErrorFragment:
    return PosErrorFragment(title="Dados inválidos. Tente novamente.")


def channel_error(detail: str) -> PosErrorFragment:
    return PosErrorFragment(title=detail)


def sale_error(detail: str, *, is_stock: bool) -> PosErrorFragment:
    return PosErrorFragment(
        title="Produto indisponível" if is_stock else "Erro ao finalizar pedido",
        detail=detail,
        recovery="Remova o item e tente novamente." if is_stock else "Tente novamente ou limpe o carrinho.",
    )


@dataclass(frozen=True)
class PosOrderConfirmed:
    """The sale-confirmed banner. The client reads ``data-order-ref`` back."""

    TEMPLATE: ClassVar[str] = f"{_FRAGMENTS}/order_confirmed.html"
    order_ref: str
    total_display: str
    order_url: str
    fiscal_hint: str


def order_confirmed(result, *, order_url: str) -> PosOrderConfirmed:
    return PosOrderConfirmed(
        order_ref=result.order_ref,
        total_display=f"R$ {format_money(result.total_q)}",
        order_url=order_url,
        fiscal_hint=result.fiscal_hint,
    )


# ── Customer chip ────────────────────────────────────────────────────


@dataclass(frozen=True)
class PosCustomerChip:
    """Customer lookup result. ``found`` carries the ``data-*`` the client reads."""

    TEMPLATE: ClassVar[str] = f"{_FRAGMENTS}/customer_chip.html"
    state: str  # "anon" | "found" | "missing"
    name: str = ""
    ref: str = ""
    group: str = ""
    email: str = ""
    default_address: str = ""
    favorite_item: str = "{}"
    last_order_items: str = "[]"
    staff_badge: str = ""
    memory: str = ""


def customer_anon() -> PosCustomerChip:
    return PosCustomerChip(state="anon")


def customer_missing() -> PosCustomerChip:
    return PosCustomerChip(state="missing")


def customer_found(customer, *, summary: dict, default_address) -> PosCustomerChip:
    name = f"{customer.first_name} {customer.last_name}".strip()
    group_ref = customer.group.ref if customer.group_id else ""

    bits: list[str] = []
    if summary.get("total_orders"):
        bits.append(f'{summary["total_orders"]} pedidos')
    if summary.get("average_order_q"):
        bits.append(f'ticket médio R$ {format_money(summary["average_order_q"])}')
    if summary.get("favorite_product"):
        bits.append(f'prefere {summary["favorite_product"]}')
    memory = " · ".join(bits) if bits else "sem histórico ainda"

    return PosCustomerChip(
        state="found",
        name=name,
        ref=customer.ref,
        group=group_ref,
        email=customer.email or "",
        default_address=default_address.formatted_address if default_address else "",
        favorite_item=json.dumps(summary.get("favorite_item") or {}, ensure_ascii=False),
        last_order_items=json.dumps(summary.get("last_order_items") or [], ensure_ascii=False),
        staff_badge=" (staff)" if group_ref == "staff" else "",
        memory=memory,
    )


# ── Inline status spans (POS tabs) ───────────────────────────────────


@dataclass(frozen=True)
class PosInlineStatus:
    """A small ``text-xs`` span used by the tab save/create/clear flows."""

    TEMPLATE: ClassVar[str] = f"{_FRAGMENTS}/inline_status.html"
    text: str
    tone: str  # "success" | "danger" | "warning" | "muted"
    bold: bool = False
    tab_ref: str = ""
    code: str = ""
    focus: str = ""


def tab_saved(*, tab_display: str, tab_ref: str) -> PosInlineStatus:
    return PosInlineStatus(text=f"POS tab {tab_display} em uso", tone="success", bold=True, tab_ref=tab_ref)


def tab_created(*, tab_display: str, tab_ref: str) -> PosInlineStatus:
    return PosInlineStatus(text=f"POS tab {tab_display} cadastrada", tone="success", bold=True, tab_ref=tab_ref)


def tab_cleared() -> PosInlineStatus:
    return PosInlineStatus(text="POS tab liberado", tone="muted")


def empty_cart_inline() -> PosInlineStatus:
    return PosInlineStatus(text="Carrinho vazio", tone="warning")


def invalid_payload_inline() -> PosInlineStatus:
    return PosInlineStatus(text="Dados inválidos", tone="danger")


def tab_intent_error(exc) -> PosInlineStatus:
    return PosInlineStatus(text=exc.message, tone="danger", code=exc.code, focus=exc.focus)


def tab_generic_error(detail: str) -> PosInlineStatus:
    return PosInlineStatus(text=f"Erro: {detail}", tone="danger")


# ── Cancel-last result ───────────────────────────────────────────────


@dataclass(frozen=True)
class PosCancelResult:
    """The ``#pos-cancel-result`` block for the cancel/correction flow."""

    TEMPLATE: ClassVar[str] = f"{_FRAGMENTS}/cancel_result.html"
    text: str
    tone: str  # "success" | "error"


def cancel_missing_ref() -> PosCancelResult:
    return PosCancelResult(text="Referência do pedido não informada", tone="error")


def cancel_error(detail: str) -> PosCancelResult:
    return PosCancelResult(text=detail, tone="error")


def cancel_done(order_ref: str) -> PosCancelResult:
    return PosCancelResult(text=f"Venda {order_ref} cancelada com sucesso", tone="success")


# ── Cash register messages ───────────────────────────────────────────


@dataclass(frozen=True)
class PosCashMessage:
    """A cash-register status line (sangria/suprimento/ajuste, close)."""

    TEMPLATE: ClassVar[str] = f"{_FRAGMENTS}/cash_message.html"
    text: str
    tone: str  # "success-foreground" | "destructive"
    small: bool = False


_CASH_MOVEMENT_LABELS = {"sangria": "Sangria", "suprimento": "Suprimento", "ajuste": "Ajuste"}


def cash_movement_done(movement) -> PosCashMessage:
    label = _CASH_MOVEMENT_LABELS.get(movement.movement_type, movement.movement_type)
    return PosCashMessage(
        text=f"{label} de R$ {format_money(movement.amount_q)} registrada.",
        tone="success-foreground",
        small=True,
    )


def cash_movement_error(detail: str) -> PosCashMessage:
    return PosCashMessage(text=detail, tone="destructive", small=True)


def cash_close_error(detail: str) -> PosCashMessage:
    return PosCashMessage(text=detail, tone="destructive")
