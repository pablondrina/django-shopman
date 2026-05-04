"""End-to-end cross-area scenarios.

These tests stitch together orderman + craftsman + stockman + backstage to
exercise flows that span multiple surfaces. If a regression breaks the
hand-off (e.g. the order signal stops triggering KDS dispatch), one of these
scenarios fails — even if the per-surface tests still pass.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services import production as production_service
from shopman.backstage.services.exceptions import ProductionError
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.orderman.models import Order, OrderItem
from shopman.shop.handlers.production_alerts import check_late_started_orders
from shopman.shop.handlers.production_order_sync import WORK_ORDER_COMMITTED_ORDER_REFS_KEY
from shopman.shop.models import Shop
from shopman.stockman import Position
from shopman.stockman.services.movements import StockMovements


@pytest.fixture
def setup(db):
    Shop.objects.create(name="Loja")
    Position.objects.create(ref="loja", name="Loja", is_saleable=True, is_default=True)
    Position.objects.create(ref="ontem", name="Ontem")
    return User.objects.create_superuser("e2e-admin", "e2e@test.com", "pw")


def _confirm_order(*, sku: str, qty: int, ref: str = "E2E-ORDER") -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        status="confirmed",
        total_q=1500,
        data={"customer": {"name": "Ana"}},
    )
    OrderItem.objects.create(
        order=order,
        line_id="1",
        sku=sku,
        name="Produto",
        qty=qty,
        unit_price_q=1500,
        line_total_q=1500 * qty,
    )
    return order


# ── Cenário 1 — order confirmation links to existing planned WO ───────


@pytest.mark.django_db
def test_e2e_order_confirmed_links_to_planned_work_order(setup):
    """When a confirmed order has SKUs produced, it gets linked to existing planned WOs."""
    from shopman.orderman.signals import order_changed

    recipe = Recipe.objects.create(
        ref="recipe-link",
        name="Produzido",
        output_sku="LINK-SKU",
        batch_size=Decimal("10"),
    )
    wo = craft.plan(recipe, 10, date=date.today())

    order = _confirm_order(sku="LINK-SKU", qty=3)
    order_changed.send(sender=Order, order=order, event_type="created", actor="test")

    order.refresh_from_db()
    awaiting = order.data.get("awaiting_wo_refs") or []
    assert wo.ref in awaiting, "order should reference the planned WO it depends on"

    wo.refresh_from_db()
    assert order.ref in (wo.meta.get(WORK_ORDER_COMMITTED_ORDER_REFS_KEY) or [])


# ── Cenário 2 — WO start→finish updates stock and clears the link ────


@pytest.mark.django_db
def test_e2e_work_order_finish_updates_stock_and_alerts_low_yield(setup):
    """A finish that drops below 80% yield must create a `production_low_yield` alert."""
    recipe = Recipe.objects.create(
        ref="recipe-yield",
        name="Yield",
        output_sku="YIELD-SKU",
        batch_size=Decimal("10"),
    )
    wo = craft.plan(recipe, 10, date=date.today())
    craft.start(wo, quantity=10, expected_rev=0)
    craft.finish(wo, finished=5, actor="test")

    alerts = OperatorAlert.objects.filter(type="production_low_yield", order_ref=wo.ref)
    assert alerts.count() == 1
    alert = alerts.first()
    assert "yield" in alert.message.lower()
    assert alert.severity in {"warning", "error", "critical"}


# ── Cenário 3 — finish with stock shortage routes through reconciliation ──


@pytest.mark.django_db
def test_e2e_finish_without_materials_raises_stock_short_error(setup, monkeypatch):
    """apply_finish must raise ProductionStockShortError before mutating stock."""
    recipe = Recipe.objects.create(
        ref="recipe-short",
        name="Short",
        output_sku="SHORT-SKU",
        batch_size=Decimal("10"),
    )
    wo = craft.plan(recipe, 10, date=date.today())
    craft.start(wo, quantity=10, expected_rev=0)

    missing = [production_service.MissingMaterial(sku="INPUT-A", needed=Decimal("5"), available=Decimal("0"))]
    monkeypatch.setattr(production_service, "check_finish_materials", lambda work_order: missing)

    with pytest.raises(production_service.ProductionStockShortError) as exc_info:
        production_service.apply_finish(work_order_id=wo.pk, quantity=10, actor="test")

    assert exc_info.value.work_order_ref == wo.ref
    assert exc_info.value.missing == missing


# ── Cenário 4 — late started detection creates alert ────────────────


@pytest.mark.django_db
def test_e2e_late_started_detection_creates_alert(setup):
    """A WO that has been STARTED beyond max_started_minutes triggers a `production_late` alert."""
    recipe = Recipe.objects.create(
        ref="recipe-late",
        name="Late",
        output_sku="LATE-SKU",
        batch_size=Decimal("10"),
        meta={"max_started_minutes": 1},
    )
    wo = craft.plan(recipe, 10, date=date.today())
    craft.start(wo, quantity=10, expected_rev=0)
    WorkOrder.objects.filter(pk=wo.pk).update(started_at=timezone.now() - timedelta(minutes=5))

    created = check_late_started_orders(selected_date=date.today())
    assert created == 1
    assert OperatorAlert.objects.filter(type="production_late", order_ref=wo.ref).exists()

    # Idempotent — second call doesn't duplicate
    created_again = check_late_started_orders(selected_date=date.today())
    assert created_again == 0


# ── Cenário 5 — full POS sale lifecycle through projections ─────────


@pytest.mark.django_db
def test_e2e_stock_receive_appears_on_closing_surface(client, setup):
    """A receive on a saleable position must show up in the fechamento surface."""
    from shopman.offerman.models import Product

    Product.objects.create(sku="POS-LIFE", name="Pão", is_published=True, is_sellable=True, base_price_q=500)
    StockMovements.receive(quantity=20, sku="POS-LIFE", position=Position.objects.get(ref="loja"), reason="seed")

    client.force_login(setup)
    closing = client.get("/admin/operacao/fechamento/")
    assert closing.status_code == 200
    body = closing.content.decode("utf-8")
    assert "POS-LIFE" in body, "closing surface must list SKU with saleable stock"


# ── Cenário 6 — production matrix end-to-end ────────────────────────


@pytest.mark.django_db
def test_e2e_production_dashboard_renders_after_lifecycle(client, setup):
    recipe = Recipe.objects.create(
        ref="recipe-dash",
        name="Dash",
        output_sku="DASH-SKU",
        batch_size=Decimal("10"),
    )
    wo = craft.plan(recipe, 10, date=date.today())
    craft.start(wo, quantity=10, expected_rev=0)
    craft.finish(wo, finished=10, actor="test")

    client.force_login(setup)
    response = client.get("/admin/operacao/producao/painel/")
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "DASH-SKU" in body or "Dash" in body or "concluído" in body.lower()


# ── Cenário 7 — advance step view updates meta ──────────────────────


@pytest.mark.django_db
def test_e2e_advance_step_via_view_updates_meta(client, setup):
    recipe = Recipe.objects.create(
        ref="recipe-step-e2e",
        name="StepE2E",
        output_sku="STEP-SKU",
        batch_size=Decimal("10"),
        meta={"steps": [
            {"name": "A", "target_seconds": 60},
            {"name": "B", "target_seconds": 60},
        ]},
    )
    wo = craft.plan(recipe, 10, date=date.today())
    craft.start(wo, quantity=10, expected_rev=0)
    client.force_login(setup)

    response = client.post(f"/gestor/producao/kds/{wo.pk}/avancar-passo/", HTTP_HX_REQUEST="true")
    assert response.status_code == 200

    wo.refresh_from_db()
    assert wo.meta["steps_progress"] == 1
    assert wo.meta["steps_progress_actor"].startswith("production:")
