from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from shopman.stockman.models import Hold, HoldStatus, Move, Position, PositionKind, Quant, StockAlert
from shopman.stockman.services.movements import StockMovements

User = get_user_model()

BASE_URL = "/api/stockman"


class StockmanAPITestBase(TestCase):
    """Base class with common setup for all Stockman API tests.

    Uses plain SKU strings with NoopSkuValidator — no dependency on offerman.
    """

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.vitrine, _ = Position.objects.get_or_create(
            ref="vitrine",
            defaults={
                "name": "Vitrine Principal",
                "kind": PositionKind.PHYSICAL,
                "is_saleable": True,
            },
        )
        self.deposito, _ = Position.objects.get_or_create(
            ref="deposito",
            defaults={
                "name": "Depósito",
                "kind": PositionKind.PHYSICAL,
                "is_saleable": False,
            },
        )

        # Plain SKU references — NoopSkuValidator accepts any SKU as valid
        self.product = SimpleNamespace(sku="PAO-FORMA", name="Pão de Forma", shelflife=None)
        self.croissant = SimpleNamespace(sku="CROISSANT", name="Croissant", shelflife=0)


# ══════════════════════════════════════════════════════════════════
# AVAILABILITY
# ══════════════════════════════════════════════════════════════════


class AvailabilityTests(StockmanAPITestBase):
    """Tests for GET /api/stockman/availability/"""

    def test_availability_returns_qty_and_reserved(self):
        """Critério: GET availability/?sku=X retorna qty disponível e reservada."""
        StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, reason="Produção")
        resp = self.client.get(f"{BASE_URL}/availability/", {"sku": "PAO-FORMA"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["sku"] == "PAO-FORMA"
        assert Decimal(data["total_available"]) == Decimal("20.000")
        assert Decimal(data["total_reserved"]) == Decimal("0.000")
        assert len(data["positions"]) == 1
        assert data["positions"][0]["position_ref"] == "vitrine"

    def test_availability_with_holds(self):
        quant = StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, reason="Produção")
        Hold.objects.create(
            sku=self.product.sku,
            quant=quant,
            quantity=Decimal("5"),
            target_date=date.today(),
            status=HoldStatus.PENDING,
        )
        resp = self.client.get(f"{BASE_URL}/availability/", {"sku": "PAO-FORMA"})
        data = resp.json()
        assert Decimal(data["total_available"]) == Decimal("15.000")
        assert Decimal(data["total_reserved"]) == Decimal("5.000")

    def test_availability_with_position_filter(self):
        StockMovements.receive(Decimal("10"), self.product.sku, position=self.vitrine, reason="Produção")
        StockMovements.receive(Decimal("5"), self.product.sku, position=self.deposito, reason="Produção")
        resp = self.client.get(f"{BASE_URL}/availability/", {"sku": "PAO-FORMA", "position_ref": "vitrine"})
        data = resp.json()
        assert Decimal(data["total_available"]) == Decimal("10.000")
        assert len(data["positions"]) == 1

    def test_availability_missing_sku(self):
        resp = self.client.get(f"{BASE_URL}/availability/")
        assert resp.status_code == 400

    def test_availability_unknown_sku(self):
        # NoopSkuValidator aceita qualquer SKU como válido — retorna 200 com estoque zero
        resp = self.client.get(f"{BASE_URL}/availability/", {"sku": "INEXISTENTE"})
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(data["total_available"]) == Decimal("0.000")

    def test_availability_no_stock_returns_zero(self):
        resp = self.client.get(f"{BASE_URL}/availability/", {"sku": "PAO-FORMA"})
        data = resp.json()
        assert Decimal(data["total_available"]) == Decimal("0.000")
        assert Decimal(data["total_reserved"]) == Decimal("0.000")

    def test_availability_allowed_positions_excludes_d1_on_ontem(self):
        """Canais remotos: breakdown sem quants em posições fora da lista (ex.: D-1 só em ontem)."""
        from shopman.stockman.services.availability import availability_for_sku

        ontem, _ = Position.objects.get_or_create(
            ref="ontem",
            defaults={
                "name": "Vitrine D-1 (ontem)",
                "kind": PositionKind.PHYSICAL,
                "is_saleable": True,
            },
        )
        StockMovements.receive(
            Decimal("5"),
            self.product.sku,
            position=ontem,
            batch="D-1",
            reason="Sobra D-1",
        )
        full = availability_for_sku(self.product.sku)
        assert full["breakdown"]["d1"] == Decimal("5")

        filtered = availability_for_sku(
            self.product.sku,
            allowed_positions=["vitrine", "deposito"],
        )
        assert filtered["breakdown"]["d1"] == Decimal("0")
        assert filtered["total_available"] == Decimal("0")


class BulkAvailabilityTests(StockmanAPITestBase):
    """Tests for GET /api/stockman/availability/bulk/"""

    def test_bulk_returns_multiple_skus(self):
        """Critério: GET availability/bulk/?skus=X,Y,Z retorna múltiplos."""
        StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, reason="Produção")
        StockMovements.receive(Decimal("10"), self.croissant.sku, position=self.vitrine, reason="Produção")

        resp = self.client.get(f"{BASE_URL}/availability/bulk/", {"skus": "PAO-FORMA,CROISSANT"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        skus = {item["sku"] for item in data}
        assert skus == {"PAO-FORMA", "CROISSANT"}

    def test_bulk_unknown_sku_returns_zero(self):
        resp = self.client.get(f"{BASE_URL}/availability/bulk/", {"skus": "PAO-FORMA,INEXISTENTE"})
        data = resp.json()
        assert len(data) == 2
        unknown = next(d for d in data if d["sku"] == "INEXISTENTE")
        assert Decimal(unknown["total_available"]) == Decimal("0.000")

    def test_bulk_missing_param(self):
        resp = self.client.get(f"{BASE_URL}/availability/bulk/")
        assert resp.status_code == 400


# ══════════════════════════════════════════════════════════════════
# POSITIONS / QUANTS
# ══════════════════════════════════════════════════════════════════


class PositionTests(StockmanAPITestBase):
    """Tests for GET /api/stockman/positions/"""

    def test_list_positions(self):
        resp = self.client.get(f"{BASE_URL}/positions/")
        assert resp.status_code == 200
        data = resp.json()
        results = data["results"] if "results" in data else data
        refs = {p["ref"] for p in results}
        assert "vitrine" in refs
        assert "deposito" in refs

    def test_position_fields(self):
        resp = self.client.get(f"{BASE_URL}/positions/")
        data = resp.json()
        results = data["results"] if "results" in data else data
        vitrine = next(p for p in results if p["ref"] == "vitrine")
        assert vitrine["name"] == "Vitrine Principal"
        assert vitrine["kind"] == "physical"
        assert vitrine["is_saleable"] is True


class PositionQuantsTests(StockmanAPITestBase):
    """Tests for GET /api/stockman/positions/{code}/quants/"""

    def test_quants_at_position(self):
        StockMovements.receive(Decimal("15"), self.product.sku, position=self.vitrine, reason="Produção")
        resp = self.client.get(f"{BASE_URL}/positions/vitrine/quants/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["sku"] == "PAO-FORMA"
        assert Decimal(data[0]["quantity"]) == Decimal("15.000")

    def test_quants_min_qty_filter(self):
        StockMovements.receive(Decimal("5"), self.product.sku, position=self.vitrine, reason="Produção")
        StockMovements.receive(Decimal("20"), self.croissant.sku, position=self.vitrine, reason="Produção")
        resp = self.client.get(f"{BASE_URL}/positions/vitrine/quants/", {"min_qty": "10"})
        data = resp.json()
        assert len(data) == 1
        assert data[0]["sku"] == "CROISSANT"

    def test_quants_unknown_position(self):
        resp = self.client.get(f"{BASE_URL}/positions/inexistente/quants/")
        assert resp.status_code == 404

    def test_quants_empty_position(self):
        resp = self.client.get(f"{BASE_URL}/positions/deposito/quants/")
        data = resp.json()
        assert data == []


# ══════════════════════════════════════════════════════════════════
# ALERTS
# ══════════════════════════════════════════════════════════════════


class BelowMinimumAlertTests(StockmanAPITestBase):
    """Tests for GET /api/stockman/alerts/below-minimum/"""

    def test_triggered_alerts(self):
        StockMovements.receive(Decimal("3"), self.product.sku, position=self.vitrine, reason="Produção")
        StockAlert.objects.create(
            sku=self.product.sku,
            position=self.vitrine,
            min_quantity=Decimal("10"),
        )
        resp = self.client.get(f"{BASE_URL}/alerts/below-minimum/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["sku"] == "PAO-FORMA"
        assert Decimal(data[0]["current_qty"]) == Decimal("3.000")
        assert Decimal(data[0]["minimum_qty"]) == Decimal("10.000")
        assert Decimal(data[0]["deficit"]) == Decimal("7.000")

    def test_no_triggered_alerts(self):
        StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, reason="Produção")
        StockAlert.objects.create(
            sku=self.product.sku,
            position=self.vitrine,
            min_quantity=Decimal("10"),
        )
        resp = self.client.get(f"{BASE_URL}/alerts/below-minimum/")
        data = resp.json()
        assert data == []

    def test_filter_by_position(self):
        StockMovements.receive(Decimal("3"), self.product.sku, position=self.vitrine, reason="Produção")
        StockMovements.receive(Decimal("3"), self.croissant.sku, position=self.deposito, reason="Produção")
        StockAlert.objects.create(sku=self.product.sku, position=self.vitrine, min_quantity=Decimal("10"))
        StockAlert.objects.create(sku=self.croissant.sku, position=self.deposito, min_quantity=Decimal("10"))
        resp = self.client.get(f"{BASE_URL}/alerts/below-minimum/", {"position_ref": "vitrine"})
        data = resp.json()
        assert len(data) == 1
        assert data[0]["position_ref"] == "vitrine"


# ══════════════════════════════════════════════════════════════════
# RECEIVE / ISSUE (WRITE)
# ══════════════════════════════════════════════════════════════════


class ReceiveTests(StockmanAPITestBase):
    """Tests for POST /api/stockman/receive/"""

    def test_receive_creates_move_and_updates_quant(self):
        """Critério: POST receive/ cria Move e atualiza Quant atomicamente."""
        resp = self.client.post(f"{BASE_URL}/receive/", {
            "sku": "PAO-FORMA",
            "qty": "20.000",
            "position_ref": "vitrine",
            "reference": "PO-2026-001",
        }, format="json")
        assert resp.status_code == 201
        data = resp.json()
        assert data["sku"] == "PAO-FORMA"
        assert Decimal(data["qty"]) == Decimal("20.000")
        assert data["position_ref"] == "vitrine"
        assert Decimal(data["new_balance"]) == Decimal("20.000")
        assert data["move_id"] is not None

        # Verify immutable ledger
        assert Move.objects.count() == 1
        move = Move.objects.first()
        assert move.delta == Decimal("20")

    def test_receive_multiple_creates_cumulative_balance(self):
        self.client.post(f"{BASE_URL}/receive/", {
            "sku": "PAO-FORMA", "qty": "10.000", "position_ref": "vitrine", "reference": "PO-001",
        }, format="json")
        resp = self.client.post(f"{BASE_URL}/receive/", {
            "sku": "PAO-FORMA", "qty": "5.000", "position_ref": "vitrine", "reference": "PO-002",
        }, format="json")
        data = resp.json()
        assert Decimal(data["new_balance"]) == Decimal("15.000")
        assert Move.objects.count() == 2

    def test_receive_unknown_sku(self):
        # NoopSkuValidator aceita qualquer SKU como válido — receive retorna 201
        resp = self.client.post(f"{BASE_URL}/receive/", {
            "sku": "INEXISTENTE", "qty": "10.000", "position_ref": "vitrine", "reference": "PO-001",
        }, format="json")
        assert resp.status_code == 201

    def test_receive_unknown_position(self):
        resp = self.client.post(f"{BASE_URL}/receive/", {
            "sku": "PAO-FORMA", "qty": "10.000", "position_ref": "inexistente", "reference": "PO-001",
        }, format="json")
        assert resp.status_code == 404

    def test_receive_with_notes(self):
        resp = self.client.post(f"{BASE_URL}/receive/", {
            "sku": "PAO-FORMA", "qty": "10.000", "position_ref": "vitrine",
            "reference": "PO-001", "notes": "Entrega matinal",
        }, format="json")
        assert resp.status_code == 201
        move = Move.objects.first()
        assert move.reason == "Entrega matinal"

    def test_receive_generates_move_in_immutable_ledger(self):
        """Critério: Todas as operações de escrita geram Move no ledger imutável."""
        self.client.post(f"{BASE_URL}/receive/", {
            "sku": "PAO-FORMA", "qty": "10.000", "position_ref": "vitrine", "reference": "PO-001",
        }, format="json")
        move = Move.objects.first()
        assert move.delta > 0
        assert move.user == self.user

        # Move is immutable — cannot be updated
        with pytest.raises(ValueError):
            move.save()


class IssueTests(StockmanAPITestBase):
    """Tests for POST /api/stockman/issue/"""

    def test_issue_creates_negative_move(self):
        StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, reason="Produção")
        resp = self.client.post(f"{BASE_URL}/issue/", {
            "sku": "PAO-FORMA", "qty": "5.000", "position_ref": "vitrine", "reference": "WO-2026-042",
        }, format="json")
        assert resp.status_code == 201
        data = resp.json()
        assert Decimal(data["new_balance"]) == Decimal("15.000")

    def test_issue_fails_if_insufficient_qty(self):
        """Critério: POST issue/ falha se qty insuficiente (400)."""
        StockMovements.receive(Decimal("5"), self.product.sku, position=self.vitrine, reason="Produção")
        resp = self.client.post(f"{BASE_URL}/issue/", {
            "sku": "PAO-FORMA", "qty": "10.000", "position_ref": "vitrine", "reference": "WO-001",
        }, format="json")
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == "INSUFFICIENT_QUANTITY"

    def test_issue_no_stock_at_position(self):
        resp = self.client.post(f"{BASE_URL}/issue/", {
            "sku": "PAO-FORMA", "qty": "5.000", "position_ref": "vitrine", "reference": "WO-001",
        }, format="json")
        assert resp.status_code == 400

    def test_issue_generates_move_in_immutable_ledger(self):
        """Critério: Todas as operações de escrita geram Move no ledger imutável."""
        StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, reason="Produção")
        self.client.post(f"{BASE_URL}/issue/", {
            "sku": "PAO-FORMA", "qty": "5.000", "position_ref": "vitrine", "reference": "WO-001",
        }, format="json")
        # 2 moves: 1 receive + 1 issue
        assert Move.objects.count() == 2
        issue_move = Move.objects.order_by("-timestamp").first()
        assert issue_move.delta < 0


# ══════════════════════════════════════════════════════════════════
# HISTORY (MOVES / HOLDS)
# ══════════════════════════════════════════════════════════════════


class MoveHistoryTests(StockmanAPITestBase):
    """Tests for GET /api/stockman/moves/"""

    def test_moves_returns_paginated_history(self):
        """Critério: GET /api/stockman/moves/ retorna histórico paginado e filtrável."""
        StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, user=self.user, reason="Produção manhã")
        StockMovements.receive(Decimal("10"), self.croissant.sku, position=self.vitrine, user=self.user, reason="Produção manhã")

        resp = self.client.get(f"{BASE_URL}/moves/")
        assert resp.status_code == 200
        data = resp.json()
        # Paginated response has count, results
        assert "count" in data
        assert "results" in data
        assert data["count"] == 2

    def test_moves_filter_by_sku(self):
        StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, reason="Produção")
        StockMovements.receive(Decimal("10"), self.croissant.sku, position=self.vitrine, reason="Produção")

        resp = self.client.get(f"{BASE_URL}/moves/", {"sku": "PAO-FORMA"})
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["sku"] == "PAO-FORMA"

    def test_moves_filter_by_position(self):
        StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, reason="Produção")
        StockMovements.receive(Decimal("10"), self.product.sku, position=self.deposito, reason="Produção")

        resp = self.client.get(f"{BASE_URL}/moves/", {"position_ref": "vitrine"})
        data = resp.json()
        assert data["count"] == 1

    def test_moves_filter_by_type_receive(self):
        quant = StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, reason="Produção")
        StockMovements.issue(Decimal("5"), quant, reason="Venda")

        resp = self.client.get(f"{BASE_URL}/moves/", {"type": "receive"})
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["move_type"] == "receive"

    def test_moves_filter_by_type_issue(self):
        quant = StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, reason="Produção")
        StockMovements.issue(Decimal("5"), quant, reason="Venda")

        resp = self.client.get(f"{BASE_URL}/moves/", {"type": "issue"})
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["move_type"] == "issue"

    def test_moves_fields(self):
        StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, user=self.user, reason="Produção manhã")
        resp = self.client.get(f"{BASE_URL}/moves/")
        move = resp.json()["results"][0]
        assert "id" in move
        assert move["sku"] == "PAO-FORMA"
        assert move["position_ref"] == "vitrine"
        assert move["move_type"] == "receive"
        assert move["reason"] == "Produção manhã"
        assert move["user"] == "testuser"
        assert "timestamp" in move


class HoldHistoryTests(StockmanAPITestBase):
    """Tests for GET /api/stockman/holds/"""

    def test_holds_list(self):
        quant = StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, reason="Produção")
        Hold.objects.create(
            sku=self.product.sku,
            quant=quant,
            quantity=Decimal("5"),
            target_date=date.today(),
            status=HoldStatus.PENDING,
        )
        resp = self.client.get(f"{BASE_URL}/holds/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        hold = data["results"][0]
        assert hold["sku"] == "PAO-FORMA"
        assert Decimal(hold["quantity"]) == Decimal("5.000")
        assert hold["status"] == "pending"

    def test_holds_filter_by_sku(self):
        quant_pao = StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, reason="Produção")
        quant_cr = StockMovements.receive(Decimal("10"), self.croissant.sku, position=self.vitrine, reason="Produção")
        Hold.objects.create(sku=self.product.sku, quant=quant_pao, quantity=Decimal("5"), target_date=date.today(), status=HoldStatus.PENDING)
        Hold.objects.create(sku=self.croissant.sku, quant=quant_cr, quantity=Decimal("3"), target_date=date.today(), status=HoldStatus.PENDING)

        resp = self.client.get(f"{BASE_URL}/holds/", {"sku": "PAO-FORMA"})
        data = resp.json()
        assert data["count"] == 1

    def test_holds_filter_active_only(self):
        quant = StockMovements.receive(Decimal("20"), self.product.sku, position=self.vitrine, reason="Produção")
        Hold.objects.create(sku=self.product.sku, quant=quant, quantity=Decimal("5"), target_date=date.today(), status=HoldStatus.PENDING)
        Hold.objects.create(sku=self.product.sku, quant=quant, quantity=Decimal("3"), target_date=date.today(), status=HoldStatus.RELEASED)

        resp = self.client.get(f"{BASE_URL}/holds/", {"is_active": "true"})
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["status"] == "pending"


# ══════════════════════════════════════════════════════════════════
# AUTHENTICATION
# ══════════════════════════════════════════════════════════════════


class AuthenticationTests(StockmanAPITestBase):
    """Critério: Autenticação obrigatória em todos os endpoints."""

    def setUp(self) -> None:
        super().setUp()
        self.anon_client = APIClient()

    def test_availability_requires_auth(self):
        resp = self.anon_client.get(f"{BASE_URL}/availability/", {"sku": "PAO-FORMA"})
        assert resp.status_code == 403

    def test_bulk_availability_requires_auth(self):
        resp = self.anon_client.get(f"{BASE_URL}/availability/bulk/", {"skus": "PAO-FORMA"})
        assert resp.status_code == 403

    def test_positions_requires_auth(self):
        resp = self.anon_client.get(f"{BASE_URL}/positions/")
        assert resp.status_code == 403

    def test_quants_requires_auth(self):
        resp = self.anon_client.get(f"{BASE_URL}/positions/vitrine/quants/")
        assert resp.status_code == 403

    def test_alerts_requires_auth(self):
        resp = self.anon_client.get(f"{BASE_URL}/alerts/below-minimum/")
        assert resp.status_code == 403

    def test_receive_requires_auth(self):
        resp = self.anon_client.post(f"{BASE_URL}/receive/", {}, format="json")
        assert resp.status_code == 403

    def test_issue_requires_auth(self):
        resp = self.anon_client.post(f"{BASE_URL}/issue/", {}, format="json")
        assert resp.status_code == 403

    def test_moves_requires_auth(self):
        resp = self.anon_client.get(f"{BASE_URL}/moves/")
        assert resp.status_code == 403

    def test_holds_requires_auth(self):
        resp = self.anon_client.get(f"{BASE_URL}/holds/")
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════
# READ-ONLY ENFORCEMENT
# ══════════════════════════════════════════════════════════════════


class ReadOnlyEnforcementTests(StockmanAPITestBase):
    """Ensure read-only endpoints reject write methods."""

    def test_availability_rejects_post(self):
        resp = self.client.post(f"{BASE_URL}/availability/", {"sku": "PAO-FORMA"}, format="json")
        assert resp.status_code == 405

    def test_positions_rejects_post(self):
        resp = self.client.post(f"{BASE_URL}/positions/", {"ref": "new"}, format="json")
        assert resp.status_code == 405

    def test_moves_rejects_post(self):
        resp = self.client.post(f"{BASE_URL}/moves/", {}, format="json")
        assert resp.status_code == 405

    def test_holds_rejects_post(self):
        resp = self.client.post(f"{BASE_URL}/holds/", {}, format="json")
        assert resp.status_code == 405

    def test_receive_rejects_get(self):
        resp = self.client.get(f"{BASE_URL}/receive/")
        assert resp.status_code == 405

    def test_issue_rejects_get(self):
        resp = self.client.get(f"{BASE_URL}/issue/")
        assert resp.status_code == 405
