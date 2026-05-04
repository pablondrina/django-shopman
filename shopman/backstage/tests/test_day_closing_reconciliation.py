from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType

from shopman.backstage.models import DayClosing
from shopman.backstage.projections.closing import ReconciliationError, build_day_closing
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.offerman.models import Product
from shopman.orderman.models import Order, OrderItem
from shopman.shop.models import Shop
from shopman.stockman import Position
from shopman.stockman.services.movements import StockMovements


@pytest.fixture
def closing_user(db):
    user = User.objects.create_user("closing-recon", password="pw", is_staff=True)
    permission = Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename="perform_closing",
    )
    user.user_permissions.add(permission)
    return user


@pytest.fixture
def setup_stock(db):
    Shop.objects.create(name="Loja")
    loja = Position.objects.create(ref="loja", name="Loja", is_saleable=True)
    Position.objects.create(ref="ontem", name="Ontem")
    Product.objects.create(sku="RECON-SKU", name="Recon SKU", shelf_life_days=0)
    StockMovements.receive(quantity=2, sku="RECON-SKU", position=loja, reason="seed")
    return loja


@pytest.mark.django_db
def test_build_day_closing_exposes_empty_production_summary(setup_stock):
    closing = build_day_closing()

    assert closing.production_summary == {}
    assert closing.reconciliation_errors == ()


@pytest.mark.django_db
def test_build_day_closing_exposes_today_production_summary(setup_stock):
    recipe = Recipe.objects.create(ref="recon-recipe", name="Recon", output_sku="RECON-SKU", batch_size=Decimal("10"))
    wo = craft.plan(recipe, 10, date=date.today())
    craft.start(wo, quantity=10, expected_rev=0)
    craft.finish(wo, finished=8, actor="test")

    closing = build_day_closing()

    assert closing.production_summary["recon-recipe"]["planned"] == 10
    assert closing.production_summary["recon-recipe"]["finished"] == 8
    assert closing.production_summary["recon-recipe"]["loss"] == 2


@pytest.mark.django_db
def test_perform_day_closing_persists_production_summary(client, setup_stock, closing_user):
    recipe = Recipe.objects.create(ref="recon-close", name="Recon Close", output_sku="RECON-SKU", batch_size=Decimal("10"))
    wo = craft.plan(recipe, 5, date=date.today())
    craft.start(wo, quantity=5, expected_rev=0)
    craft.finish(wo, finished=4, actor="test")
    client.force_login(closing_user)

    response = client.post("/admin/operacao/fechamento/", {"qty_RECON-SKU": "1"})

    assert response.status_code == 302
    closing = DayClosing.objects.get()
    assert closing.data["production_summary"]["recon-close"]["finished"] == 4
    assert "reconciliation_errors" in closing.data


@pytest.mark.django_db
def test_reconciliation_error_when_sold_exceeds_available(client, setup_stock, closing_user):
    order = Order.objects.create(ref="RECON-ORD", channel_ref="web", status="completed", total_q=3000)
    OrderItem.objects.create(order=order, line_id="1", sku="RECON-SKU", name="Recon", qty=5, unit_price_q=100, line_total_q=500)
    client.force_login(closing_user)

    response = client.post("/admin/operacao/fechamento/", {"qty_RECON-SKU": "0"})

    assert response.status_code == 302
    error = DayClosing.objects.get().data["reconciliation_errors"][0]
    assert error["sku"] == "RECON-SKU"
    assert error["deficit"] == 3

    closing = build_day_closing()
    assert len(closing.reconciliation_errors) == 1
    typed = closing.reconciliation_errors[0]
    assert isinstance(typed, ReconciliationError)
    assert typed.sku == "RECON-SKU"
    assert typed.sold_qty == 5
    assert typed.deficit_qty == 3
    assert typed.available_qty == 2


def test_reconciliation_error_from_dict():
    raw = {"sku": "X", "sold": 10, "available": 6, "deficit": 4}
    err = ReconciliationError.from_dict(raw)
    assert err == ReconciliationError(sku="X", sold_qty=10, available_qty=6, deficit_qty=4)
