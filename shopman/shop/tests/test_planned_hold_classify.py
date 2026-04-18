"""Planned-hold state classifier tests (AVAILABILITY-PLAN §8).

Covers ``shopman.shop.services.availability.classify_planned_hold_for_session_sku``
against real Hold rows. Planned holds are the ones stamped with
``metadata.planned=True`` at creation (see ``adapters/stock.create_hold``).

Scenarios:
1. Pre-materialization hold (``expires_at=None``) → ``is_awaiting_confirmation``.
2. Post-materialization hold (``expires_at`` in the future, quant physical) →
   ``is_ready_for_confirmation`` with the concrete deadline.
3. Partial materialization (mix awaiting + ready) stays awaiting — the line
   only flips to ready when every hold has materialized.
4. Vanilla cart hold (no ``planned`` marker) → both flags False.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.stockman.models import Hold, HoldStatus, Position, PositionKind, Quant

from shopman.shop.services.availability import classify_planned_hold_for_session_sku

pytestmark = pytest.mark.django_db


SESSION_KEY = "test-planned-hold-session"
SKU = "PAO-PRETO"


def _position():
    pos, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={
            "name": "Loja Principal",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    return pos


def _physical_quant():
    pos = _position()
    quant, _ = Quant.objects.get_or_create(
        sku=SKU,
        position=pos,
        target_date=None,
        batch="",
        defaults={"metadata": {}},
    )
    return quant


def _planned_quant(target: date | None = None):
    pos = _position()
    quant, _ = Quant.objects.get_or_create(
        sku=SKU,
        position=pos,
        target_date=target or (date.today() + timedelta(days=1)),
        batch="",
        defaults={"metadata": {}},
    )
    return quant


def _make_hold(*, quant, expires_at, planned: bool, qty=Decimal("1")):
    target = quant.target_date if quant is not None else date.today()
    return Hold.objects.create(
        sku=SKU,
        quant=quant,
        quantity=qty,
        target_date=target or date.today(),
        status=HoldStatus.PENDING,
        expires_at=expires_at,
        metadata={
            "reference": SESSION_KEY,
            **({"planned": True} if planned else {}),
        },
    )


class TestClassifyPlannedHoldForSessionSku:
    def test_pre_materialization_is_awaiting(self):
        _make_hold(quant=_planned_quant(), expires_at=None, planned=True)

        result = classify_planned_hold_for_session_sku(SESSION_KEY, SKU)

        assert result["is_awaiting_confirmation"] is True
        assert result["is_ready_for_confirmation"] is False
        assert result["deadline"] is None

    def test_demand_only_hold_is_awaiting(self):
        # quant=None (pure demand) — also a planned hold.
        _make_hold(quant=None, expires_at=None, planned=True)

        result = classify_planned_hold_for_session_sku(SESSION_KEY, SKU)

        assert result["is_awaiting_confirmation"] is True
        assert result["is_ready_for_confirmation"] is False

    def test_post_materialization_is_ready(self):
        deadline = timezone.now() + timedelta(minutes=55)
        _make_hold(quant=_physical_quant(), expires_at=deadline, planned=True)

        result = classify_planned_hold_for_session_sku(SESSION_KEY, SKU)

        assert result["is_awaiting_confirmation"] is False
        assert result["is_ready_for_confirmation"] is True
        assert result["deadline"] == deadline

    def test_partial_materialization_stays_awaiting(self):
        """Binary aggregation: any pre-materialization hold keeps the line
        in "Aguardando confirmação" until every hold has materialized.
        """
        _make_hold(quant=_planned_quant(), expires_at=None, planned=True)
        _make_hold(
            quant=_physical_quant(),
            expires_at=timezone.now() + timedelta(minutes=50),
            planned=True,
        )

        result = classify_planned_hold_for_session_sku(SESSION_KEY, SKU)

        assert result["is_awaiting_confirmation"] is True
        assert result["is_ready_for_confirmation"] is False
        assert result["deadline"] is None

    def test_deadline_is_earliest_when_multiple_ready(self):
        earlier = timezone.now() + timedelta(minutes=20)
        later = timezone.now() + timedelta(minutes=55)
        _make_hold(quant=_physical_quant(), expires_at=later, planned=True)
        _make_hold(quant=_physical_quant(), expires_at=earlier, planned=True)

        result = classify_planned_hold_for_session_sku(SESSION_KEY, SKU)

        assert result["is_ready_for_confirmation"] is True
        assert result["deadline"] == earlier

    def test_non_planned_hold_is_neutral(self):
        # Vanilla 30-min hold — no metadata.planned marker.
        _make_hold(
            quant=_physical_quant(),
            expires_at=timezone.now() + timedelta(minutes=30),
            planned=False,
        )

        result = classify_planned_hold_for_session_sku(SESSION_KEY, SKU)

        assert result["is_awaiting_confirmation"] is False
        assert result["is_ready_for_confirmation"] is False
        assert result["deadline"] is None

    def test_empty_inputs_short_circuit(self):
        empty = {
            "is_awaiting_confirmation": False,
            "is_ready_for_confirmation": False,
            "deadline": None,
        }
        assert classify_planned_hold_for_session_sku("", SKU) == empty
        assert classify_planned_hold_for_session_sku(SESSION_KEY, "") == empty

    def test_expired_hold_is_ignored(self):
        _make_hold(
            quant=_physical_quant(),
            expires_at=timezone.now() - timedelta(minutes=5),
            planned=True,
        )

        result = classify_planned_hold_for_session_sku(SESSION_KEY, SKU)

        assert result["is_awaiting_confirmation"] is False
        assert result["is_ready_for_confirmation"] is False
