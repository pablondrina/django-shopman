"""WP-ADM-6 — CashMovement no Admin é trilha readonly (movimentos nascem no PDV)."""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from shopman.backstage.models import CashMovement, CashShift, POSTerminal


@pytest.fixture
def shift(db):
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja")  # satisfaz o OnboardingMiddleware
    terminal = POSTerminal.objects.create(ref="t1", label="Caixa 1", channel_ref="pdv")
    operator = User.objects.create_user("op-user", "op@test.com", "pw")
    return CashShift.objects.create(
        terminal=terminal,
        operator=operator,
        opened_at=timezone.now(),
        opening_amount_q=10000,
        status=CashShift.Status.CLOSED,
    )


@pytest.mark.django_db
def test_admin_is_readonly_trail():
    registered = admin.site._registry[CashMovement]
    assert registered.has_add_permission(_req()) is False
    assert registered.has_change_permission(_req()) is False
    assert registered.has_delete_permission(_req()) is False


@pytest.mark.django_db
def test_add_via_admin_is_forbidden(client, shift):
    admin_user = User.objects.create_superuser("cash-admin", "c@test.com", "pw")
    client.force_login(admin_user)
    resp = client.post(
        reverse("admin:backstage_cashmovement_add"),
        {
            "shift": shift.pk,
            "movement_type": CashMovement.MovementType.SUPRIMENTO,
            "amount_q": 1000,
            "reason": "Troco",
        },
    )
    assert resp.status_code == 403
    assert not CashMovement.objects.filter(shift=shift).exists()


@pytest.mark.django_db
def test_changelist_remains_visible(client, shift):
    CashMovement.objects.create(
        shift=shift,
        movement_type=CashMovement.MovementType.AJUSTE,
        amount_q=-250,
        reason="Falta na conferência",
        created_by="op-user",
    )
    admin_user = User.objects.create_superuser("cash-admin", "c@test.com", "pw")
    client.force_login(admin_user)
    resp = client.get(reverse("admin:backstage_cashmovement_changelist"))
    assert resp.status_code == 200
    assert "Falta na conferência" in resp.content.decode()


def _req():
    request = RequestFactory().get("/")
    request.user = User(is_superuser=True, is_staff=True)
    return request
