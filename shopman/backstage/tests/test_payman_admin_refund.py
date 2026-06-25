"""WP-D4 — partial/total refund flow on the PaymentIntent admin."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from shopman.payman.models import PaymentIntent
from shopman.payman.service import PaymentService

from shopman.shop.models import Shop


def _captured_intent(amount_q=10000):
    intent = PaymentService.create_intent(
        f"ORD-ADMINREF{PaymentIntent.objects.count()}", amount_q, "pix"
    )
    PaymentService.authorize(intent.ref)
    PaymentService.capture(intent.ref)
    return PaymentService.get(intent.ref)


def _refund_url(pk):
    return f"/admin/payman/paymentintent/{pk}/refund-amount/"


@pytest.fixture
def admin_client(client, db):
    Shop.objects.create(name="Loja")
    user = User.objects.create_superuser("ref-admin", "r@test.com", "pw")
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_refund_page_renders(admin_client):
    intent = _captured_intent(10000)
    resp = admin_client.get(_refund_url(intent.pk))
    assert resp.status_code == 200
    assert b"Confirmar reembolso" in resp.content


@pytest.mark.django_db
def test_partial_refund(admin_client):
    intent = _captured_intent(10000)
    resp = admin_client.post(_refund_url(intent.pk), {"amount_reais": "30.00"})
    assert resp.status_code in (200, 302)
    assert PaymentService.refunded_total(intent.ref) == 3000


@pytest.mark.django_db
def test_total_refund_when_blank(admin_client):
    intent = _captured_intent(5000)
    resp = admin_client.post(_refund_url(intent.pk), {"amount_reais": ""})
    assert resp.status_code in (200, 302)
    assert PaymentService.refunded_total(intent.ref) == 5000


@pytest.mark.django_db
def test_refund_above_available_is_rejected(admin_client):
    intent = _captured_intent(4000)
    resp = admin_client.post(_refund_url(intent.pk), {"amount_reais": "99.00"})
    assert resp.status_code == 200  # re-renders with error
    assert PaymentService.refunded_total(intent.ref) == 0
