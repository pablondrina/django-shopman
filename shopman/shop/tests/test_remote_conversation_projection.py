from __future__ import annotations

from types import SimpleNamespace

import pytest

from shopman.shop.projections.types import SurfaceActionProjection
from shopman.shop.services import conversation


def _channel_policy(**overrides):
    values = {
        "can_cancel": True,
        "can_rate": True,
        "supports_access_link": True,
        "requires_payment_gate": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _promise(**overrides):
    values = {
        "state": "received",
        "title": "Recebemos seu pedido.",
        "message": "Vamos conferir a disponibilidade.",
        "tone": "info",
        "actions": (),
        "deadline_at": None,
        "next_event": "Conferir disponibilidade.",
        "recovery": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_conversation_uses_tracking_promise_without_creating_order_status(monkeypatch):
    order = SimpleNamespace(
        ref="ORD-CHAT-1",
        status="new",
        channel_ref="whatsapp",
        data={},
    )
    tracking = SimpleNamespace(
        order_ref=order.ref,
        promise=_promise(state="availability_check"),
        items=[SimpleNamespace(qty=2, name="Croissant")],
        total_display="R$ 20,00",
        actions=(SurfaceActionProjection(
            ref="cancel_order",
            kind="mutation",
            label="Cancelar pedido",
            href="/api/v1/orders/ORD-CHAT-1/cancel/",
            method="POST",
            priority="danger",
        ),),
    )
    monkeypatch.setattr(conversation.order_tracking, "build_tracking", lambda order, is_debug=False: tracking)
    monkeypatch.setattr(conversation.payment_status, "build_payment", pytest.fail)
    monkeypatch.setattr(conversation, "resolve_channel_policy", lambda channel_ref: _channel_policy())

    projection = conversation.build_order_conversation(order)

    assert projection.source_projection == "tracking"
    assert projection.state == "availability_check"
    assert projection.order_status == "new"
    assert projection.actions[0].ref == "cancel_order"
    assert projection.actions[0].kind == "mutation"
    assert projection.items_summary == ("2x Croissant",)
    assert projection.tracking_url == "/pedido/ORD-CHAT-1/"


def test_conversation_prefers_payment_promise_when_customer_payment_action_exists(monkeypatch):
    order = SimpleNamespace(
        ref="ORD-CHAT-2",
        status="confirmed",
        channel_ref="whatsapp",
        data={"payment": {"method": "pix"}},
    )
    tracking = SimpleNamespace(
        order_ref=order.ref,
        promise=_promise(
            state="payment_requested",
            actions=(SurfaceActionProjection(
                ref="pay_now",
                kind="link",
                label="Pagar agora",
                href="/pedido/ORD-CHAT-2/pagamento/",
                priority="primary",
            ),),
        ),
        items=[],
        total_display="R$ 45,00",
        actions=(SurfaceActionProjection(
            ref="cancel_order",
            kind="mutation",
            label="Cancelar pedido",
            href="/api/v1/orders/ORD-CHAT-2/cancel/",
            method="POST",
            priority="danger",
        ),),
    )
    payment = SimpleNamespace(
        promise=_promise(
            state="pix_payment_after_confirmation",
            title="Pagamento Pix",
            actions=(SurfaceActionProjection(
                ref="copy_pix",
                kind="copy",
                label="Pagar com Pix",
                href="/pedido/ORD-CHAT-2/pagamento/",
                priority="primary",
            ),),
            deadline_at="2026-05-15T12:15:00-03:00",
        )
    )
    monkeypatch.setattr(conversation.order_tracking, "build_tracking", lambda order, is_debug=False: tracking)
    monkeypatch.setattr(conversation.payment_status, "build_payment", lambda order: payment)
    monkeypatch.setattr(
        conversation,
        "resolve_channel_policy",
        lambda channel_ref: _channel_policy(requires_payment_gate=True),
    )

    projection = conversation.build_order_conversation(order)

    assert projection.source_projection == "payment"
    assert projection.state == "pix_payment_after_confirmation"
    assert projection.order_status == "confirmed"
    assert projection.actions[0].ref == "copy_pix"
    assert projection.actions[0].href == "/pedido/ORD-CHAT-2/pagamento/"
    assert projection.actions[1].ref == "cancel_order"
    assert projection.payment_url == "/pedido/ORD-CHAT-2/pagamento/"
    assert projection.requires_payment_gate is True


def test_conversation_respects_channel_policy_cancel_gate(monkeypatch):
    order = SimpleNamespace(ref="ORD-CHAT-3", status="preparing", channel_ref="ifood", data={})
    tracking = SimpleNamespace(
        order_ref=order.ref,
        promise=_promise(state="preparing"),
        items=[],
        total_display="R$ 10,00",
        actions=(SurfaceActionProjection(
            ref="cancel_order",
            kind="mutation",
            label="Cancelar pedido",
            href="/api/v1/orders/ORD-CHAT-3/cancel/",
            method="POST",
            priority="danger",
        ),),
    )
    monkeypatch.setattr(conversation.order_tracking, "build_tracking", lambda order, is_debug=False: tracking)
    monkeypatch.setattr(conversation.payment_status, "build_payment", pytest.fail)
    monkeypatch.setattr(
        conversation,
        "resolve_channel_policy",
        lambda channel_ref: _channel_policy(can_cancel=False, supports_access_link=False),
    )

    projection = conversation.build_order_conversation(order)

    assert all(action.ref != "cancel_order" for action in projection.actions)
    assert projection.supports_access_link is False
    assert projection.state == "preparing"
