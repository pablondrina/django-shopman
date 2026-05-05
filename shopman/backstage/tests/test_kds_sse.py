from __future__ import annotations

import pytest
from shopman.orderman.models import Order

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.shop.handlers import _sse_emitters


@pytest.fixture
def kds_ticket(db):
    order = Order.objects.create(ref="KDS-SSE-ORD", channel_ref="web", status="confirmed", total_q=1000)
    station = KDSInstance.objects.create(ref="prep", name="Preparo", type="prep")
    return KDSTicket.objects.create(
        order=order,
        kds_instance=station,
        items=[{"sku": "P1", "name": "Produto", "qty": 1, "checked": False}],
    )


@pytest.mark.django_db
def test_emit_kds_change_payload(monkeypatch, kds_ticket):
    calls = []
    monkeypatch.setattr(_sse_emitters, "_emit_backstage", lambda *args, **kwargs: calls.append((args, kwargs)))

    _sse_emitters.emit_kds_change(kds_ticket, event_type="backstage-kds-created")

    args, kwargs = calls[0]
    assert args[0] == "kds"
    assert args[1] == "backstage-kds-created"
    assert args[2]["ticket_ref"] == f"KDS-{kds_ticket.pk}"
    assert args[2]["kds_instance_ref"] == "prep"
    assert args[2]["order_ref"] == "KDS-SSE-ORD"
    assert kwargs["scope"] == "prep"


@pytest.mark.django_db
def test_kds_ticket_created_emits_created_and_update(monkeypatch):
    calls = []
    monkeypatch.setattr(_sse_emitters, "_emit_backstage", lambda kind, event_type, payload, **kwargs: calls.append(event_type))
    order = Order.objects.create(ref="KDS-SSE-NEW", channel_ref="web", status="confirmed", total_q=1000)
    station = KDSInstance.objects.create(ref="prep-new", name="Preparo", type="prep")

    KDSTicket.objects.create(order=order, kds_instance=station, items=[])

    assert "backstage-kds-created" in calls
    assert "backstage-kds-update" in calls


@pytest.mark.django_db
def test_kds_ticket_status_change_emits_status_and_update(monkeypatch, kds_ticket):
    calls = []
    monkeypatch.setattr(_sse_emitters, "_emit_backstage", lambda kind, event_type, payload, **kwargs: calls.append(event_type))

    kds_ticket.status = "in_progress"
    kds_ticket.save(update_fields=["status"])

    assert "backstage-kds-status-changed" in calls
    assert "backstage-kds-update" in calls


@pytest.mark.django_db
def test_kds_ticket_items_change_emits_update(monkeypatch, kds_ticket):
    calls = []
    monkeypatch.setattr(_sse_emitters, "_emit_backstage", lambda kind, event_type, payload, **kwargs: calls.append(event_type))

    kds_ticket.items = [{"sku": "P1", "name": "Produto", "qty": 1, "checked": True}]
    kds_ticket.save(update_fields=["items"])

    assert calls == ["backstage-kds-update"]


@pytest.mark.django_db
def test_kds_multi_instance_scopes_events_per_station(monkeypatch):
    """Two stations emitting concurrently must scope to their own ref — no cross-talk."""
    captured: list[tuple[str, str]] = []

    def fake_emit(kind, event_type, payload, *, scope=None):
        captured.append((scope or "main", payload["kds_instance_ref"]))

    monkeypatch.setattr(_sse_emitters, "_emit_backstage", fake_emit)

    prep = KDSInstance.objects.create(ref="prep-multi", name="Preparo", type="prep")
    expedicao = KDSInstance.objects.create(ref="expedicao-multi", name="Expedição", type="expedition")
    order_a = Order.objects.create(ref="MULTI-A", channel_ref="web", status="confirmed", total_q=100)
    order_b = Order.objects.create(ref="MULTI-B", channel_ref="web", status="confirmed", total_q=100)

    KDSTicket.objects.create(order=order_a, kds_instance=prep, items=[])
    KDSTicket.objects.create(order=order_b, kds_instance=expedicao, items=[])

    prep_scopes = {scope for scope, _ in captured if scope == "prep-multi"}
    exp_scopes = {scope for scope, _ in captured if scope == "expedicao-multi"}
    assert prep_scopes == {"prep-multi"}
    assert exp_scopes == {"expedicao-multi"}

    # Each station's payload only references its own ref
    prep_refs = {ref for scope, ref in captured if scope == "prep-multi"}
    exp_refs = {ref for scope, ref in captured if scope == "expedicao-multi"}
    assert prep_refs == {"prep-multi"}
    assert exp_refs == {"expedicao-multi"}
