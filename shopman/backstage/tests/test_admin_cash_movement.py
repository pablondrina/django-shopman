"""WP-D4 — audited cash movement add form (Reais → centavos, created_by stamp)."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from shopman.backstage.admin.cash_register import CashMovementForm
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
def test_form_converts_reais_to_centavos(shift):
    form = CashMovementForm(
        data={
            "shift": shift.pk,
            "movement_type": CashMovement.MovementType.SANGRIA,
            "amount_reais": "25.50",
            "reason": "Sangria pós-fechamento",
        }
    )
    assert form.is_valid(), form.errors
    movement = form.save()
    assert movement.amount_q == 2550


@pytest.mark.django_db
def test_add_via_admin_stamps_created_by(client, shift):
    admin_user = User.objects.create_superuser("cash-admin", "c@test.com", "pw")
    client.force_login(admin_user)
    resp = client.post(
        reverse("admin:backstage_cashmovement_add"),
        {
            "shift": shift.pk,
            "movement_type": CashMovement.MovementType.SUPRIMENTO,
            "amount_reais": "10.00",
            "reason": "Troco",
        },
    )
    assert resp.status_code in (200, 302)
    movement = CashMovement.objects.get(shift=shift)
    assert movement.amount_q == 1000
    assert movement.created_by == "cash-admin"


@pytest.mark.django_db
def test_existing_movements_are_immutable(shift):
    from django.contrib import admin

    from shopman.backstage.models import CashMovement as CM

    registered = admin.site._registry[CM]
    assert registered.has_change_permission(_req()) is False
    assert registered.has_delete_permission(_req()) is False


def _req():
    from django.test import RequestFactory

    request = RequestFactory().get("/")
    request.user = User(is_superuser=True, is_staff=True)
    return request
