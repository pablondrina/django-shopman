"""WP-3 — "Me avise quando disponível" (stock-back alerts).

Cobre: subscribe (anônimo/dedup/sem contato), notify idempotente (dispara só
quando disponível, marca uma vez, não marca em falha de envio) e o endpoint.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from shopman.offerman.models import Product

from shopman.storefront.models import StockAlertSubscription
from shopman.storefront.services import stock_alerts

pytestmark = pytest.mark.django_db

PHONE = "+5543999990001"


def _state(can_add: bool):
    return MagicMock(can_add_to_cart=can_add)


def _publish(sku="SKU-NOTIFY"):
    return Product.objects.create(sku=sku, name="Pão Teste", base_price_q=500, is_published=True, is_sellable=True)


# ── subscribe ───────────────────────────────────────────────────────


def test_subscribe_anonymous_creates_pending():
    sub = stock_alerts.subscribe("SKU-1", channel_ref="web", phone=PHONE)
    assert sub is not None
    assert sub.is_pending
    assert sub.contact_phone == PHONE


def test_subscribe_dedupes_pending_for_same_contact():
    a = stock_alerts.subscribe("SKU-1", phone=PHONE)
    b = stock_alerts.subscribe("SKU-1", phone=PHONE)
    assert a.pk == b.pk
    assert StockAlertSubscription.objects.filter(sku="SKU-1").count() == 1


def test_subscribe_requires_a_contact():
    assert stock_alerts.subscribe("SKU-1") is None


# ── notify ──────────────────────────────────────────────────────────


def test_notify_sends_and_marks_when_available():
    sub = stock_alerts.subscribe("SKU-1", phone=PHONE)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
    ):
        notified = stock_alerts.notify_back_in_stock("SKU-1")

    assert notified == 1
    nf.assert_called_once()
    assert nf.call_args.kwargs["event"] == "stock.arrived"
    assert nf.call_args.kwargs["recipient"] == PHONE
    sub.refresh_from_db()
    assert sub.notified_at is not None


def test_notify_skips_when_still_unavailable():
    sub = stock_alerts.subscribe("SKU-1", phone=PHONE)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(False)),
        patch("shopman.shop.notifications.notify") as nf,
    ):
        notified = stock_alerts.notify_back_in_stock("SKU-1")

    assert notified == 0
    nf.assert_not_called()
    sub.refresh_from_db()
    assert sub.notified_at is None


def test_notify_is_idempotent_once_notified():
    stock_alerts.subscribe("SKU-1", phone=PHONE)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)),
    ):
        stock_alerts.notify_back_in_stock("SKU-1")
        again = stock_alerts.notify_back_in_stock("SKU-1")

    assert again == 0


def test_notify_does_not_mark_on_send_failure():
    sub = stock_alerts.subscribe("SKU-1", phone=PHONE)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=False)),
    ):
        notified = stock_alerts.notify_back_in_stock("SKU-1")

    assert notified == 0
    sub.refresh_from_db()
    assert sub.notified_at is None  # mantém pendente p/ retry na próxima chegada


# ── endpoint ────────────────────────────────────────────────────────


def test_endpoint_anonymous_subscribes(client):
    p = _publish()
    resp = client.post(f"/api/v1/availability/{p.sku}/notify/", {"phone": PHONE})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert StockAlertSubscription.objects.filter(sku=p.sku, notified_at__isnull=True).exists()


def test_endpoint_requires_phone_when_anonymous(client):
    p = _publish()
    resp = client.post(f"/api/v1/availability/{p.sku}/notify/", {})
    assert resp.status_code == 400


def test_endpoint_404_for_unknown_sku(client):
    resp = client.post("/api/v1/availability/NOPE/notify/", {"phone": PHONE})
    assert resp.status_code == 404


# ── trigger (Move receiver) ─────────────────────────────────────────


def test_move_receiver_schedules_notify_for_pending_sku():
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-MOVE", phone=PHONE)
    fake = MagicMock(quant_id=1)
    fake.quant.sku = "SKU-MOVE"
    with (
        patch("shopman.storefront.services.stock_alerts.notify_back_in_stock") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=fake)
    nb.assert_called_once_with("SKU-MOVE")


def test_move_receiver_skips_when_no_pending_subscription():
    from shopman.storefront import handlers

    fake = MagicMock(quant_id=1)
    fake.quant.sku = "SKU-NO-WAITERS"
    with (
        patch("shopman.storefront.services.stock_alerts.notify_back_in_stock") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=fake)
    nb.assert_not_called()


# ── trigger (fornada) ───────────────────────────────────────────────


def test_bake_receiver_notifies_production_ready_subscribers():
    """"Me avise quando sair do forno" dispara na fornada, não na reposição."""
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-BAKE", phone=PHONE, alert_type="production_ready")
    with (
        patch("shopman.storefront.services.stock_alerts.notify_bake_ready") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_production_finished_for_stock_alerts(
            sender=None, product_ref="SKU-BAKE", date=None, action="finished", work_order=None
        )
    nb.assert_called_once_with("SKU-BAKE")


def test_bake_receiver_ignores_other_production_actions():
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-BAKE", phone=PHONE, alert_type="production_ready")
    with (
        patch("shopman.storefront.services.stock_alerts.notify_bake_ready") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_production_finished_for_stock_alerts(
            sender=None, product_ref="SKU-BAKE", date=None, action="started", work_order=None
        )
    nb.assert_not_called()


def test_stock_back_subscriber_is_not_woken_by_a_bake():
    """Os dois gatilhos são independentes: quem espera reposição não recebe fornada."""
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-BAKE", phone=PHONE)  # stock_back (default)
    with (
        patch("shopman.storefront.services.stock_alerts.notify_bake_ready") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_production_finished_for_stock_alerts(
            sender=None, product_ref="SKU-BAKE", date=None, action="finished", work_order=None
        )
    nb.assert_not_called()


def test_both_alert_types_coexist_for_the_same_shopper():
    back = stock_alerts.subscribe("SKU-BOTH", phone=PHONE)
    bake = stock_alerts.subscribe("SKU-BOTH", phone=PHONE, alert_type="production_ready")
    assert back.pk != bake.pk
    assert bake.alert_type == "production_ready"


def test_endpoint_accepts_the_bake_alert_type(client):
    p = _publish(sku="SKU-BAKE-API")
    resp = client.post(
        f"/api/v1/availability/{p.sku}/notify/",
        {"phone": PHONE, "alert_type": "production_ready"},
    )
    assert resp.status_code == 200
    sub = StockAlertSubscription.objects.get(sku=p.sku)
    assert sub.alert_type == "production_ready"


def test_endpoint_rejects_an_unknown_alert_type(client):
    p = _publish(sku="SKU-BAD-TYPE")
    resp = client.post(
        f"/api/v1/availability/{p.sku}/notify/",
        {"phone": PHONE, "alert_type": "telepatia"},
    )
    assert resp.status_code == 400
    assert resp.json()["field"] == "alert_type"
