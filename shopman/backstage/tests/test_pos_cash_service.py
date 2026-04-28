"""POS cash-register service tests."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from shopman.backstage.models import CashMovement, CashRegisterSession
from shopman.backstage.services import pos
from shopman.backstage.services.exceptions import POSError


@pytest.fixture
def operator(db):
    return User.objects.create_user(username="cash-service", password="x", is_staff=True)


def test_parse_money_to_q_accepts_common_operator_inputs():
    assert pos.parse_money_to_q("12,34") == 1234
    assert pos.parse_money_to_q("12.34") == 1234
    assert pos.parse_money_to_q("bad") == 0


@pytest.mark.django_db
def test_open_cash_session_creates_or_returns_current_session(operator):
    session = pos.open_cash_session(operator=operator, opening_amount_raw="50,00")
    same = pos.open_cash_session(operator=operator, opening_amount_raw="99,00")

    assert session.pk == same.pk
    assert session.opening_amount_q == 5000
    assert CashRegisterSession.objects.count() == 1


@pytest.mark.django_db
def test_register_cash_movement_requires_open_session(operator):
    with pytest.raises(POSError):
        pos.register_cash_movement(operator=operator, amount_raw="10")


@pytest.mark.django_db
def test_register_cash_movement_validates_amount_and_normalizes_type(operator):
    session = CashRegisterSession.objects.create(operator=operator, opening_amount_q=0)

    with pytest.raises(POSError):
        pos.register_cash_movement(operator=operator, amount_raw="0")

    movement = pos.register_cash_movement(
        operator=operator,
        movement_type="unknown",
        amount_raw="25,50",
        reason="troco",
    )

    assert movement.session_id == session.pk
    assert movement.movement_type == "sangria"
    assert movement.amount_q == 2550
    assert movement.created_by == operator.username
    assert CashMovement.objects.count() == 1


@pytest.mark.django_db
def test_close_cash_session_requires_open_session(operator):
    with pytest.raises(POSError):
        pos.close_cash_session(operator=operator, closing_amount_raw="0")


@pytest.mark.django_db
def test_close_cash_session_closes_and_records_notes(operator):
    CashRegisterSession.objects.create(operator=operator, opening_amount_q=1000)

    session = pos.close_cash_session(
        operator=operator,
        closing_amount_raw="10,00",
        notes="fim do turno",
    )

    assert session.status == CashRegisterSession.Status.CLOSED
    assert session.closing_amount_q == 1000
    assert session.notes == "fim do turno"
