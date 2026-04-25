from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from shopman.stockman import stock
from shopman.stockman.models import Batch, Move, Position, PositionKind
from shopman.stockman.services.availability import availability_scope_for_channel

pytestmark = pytest.mark.django_db


def _position(ref: str) -> Position:
    position, _ = Position.objects.get_or_create(
        ref=ref,
        defaults={
            "name": ref,
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    return position


def _scope_resolver(channel_ref: str | None) -> dict:
    if channel_ref == "remote":
        return {"safety_margin": 2, "allowed_positions": ["vitrine"]}
    return {"safety_margin": 0, "allowed_positions": None}


class TestBatchQuerySetActive:
    def test_active_returns_only_batches_with_positive_stock(self):
        position = _position("hardening-batch")
        active = Batch.objects.create(
            ref="HARD-ACTIVE",
            sku="HARD-SKU",
            expiry_date=date.today() + timedelta(days=2),
        )
        empty = Batch.objects.create(
            ref="HARD-EMPTY",
            sku="HARD-SKU",
            expiry_date=date.today() + timedelta(days=2),
        )

        quant = stock.receive(Decimal("5"), "HARD-SKU", position, batch=active.ref)
        stock.receive(Decimal("3"), "HARD-SKU", position, batch=empty.ref)
        stock.issue(Decimal("3"), stock.get_quant("HARD-SKU", position=position, batch=empty.ref))

        result = list(Batch.objects.active())
        assert active in result
        assert empty not in result
        assert quant.batch == active.ref


class TestMoveQuerySetGuards:
    def test_bulk_update_is_blocked_for_any_field(self):
        quant = stock.receive(Decimal("5"), "HARD-MOVE", _position("hardening-move"))

        with pytest.raises(ValueError, match="imutáveis"):
            Move.objects.filter(quant=quant).update(reason="edited")

    def test_bulk_delete_is_blocked(self):
        quant = stock.receive(Decimal("5"), "HARD-MOVE-DEL", _position("hardening-move-del"))

        with pytest.raises(ValueError, match="imutáveis"):
            Move.objects.filter(quant=quant).delete()


class TestAvailabilityScopeForChannel:
    def test_defaults_do_not_require_orchestrator(self):
        assert availability_scope_for_channel("any") == {
            "safety_margin": 0,
            "allowed_positions": None,
        }

    @override_settings(
        STOCKMAN={
            "CHANNEL_SCOPE_RESOLVER": "shopman.stockman.tests.test_hardening._scope_resolver",
        }
    )
    def test_optional_resolver_projects_channel_scope(self):
        assert availability_scope_for_channel("remote") == {
            "safety_margin": 2,
            "allowed_positions": ["vitrine"],
        }
