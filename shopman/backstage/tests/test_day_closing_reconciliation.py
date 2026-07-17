from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.offerman.models import Product
from shopman.orderman.models import Order, OrderItem
from shopman.stockman import Position
from shopman.stockman.services.movements import StockMovements

from shopman.backstage.models import CashShift, DayClosing, POSTerminal
from shopman.backstage.projections.closing import ReconciliationError, build_day_closing
from shopman.shop.models import Shop


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

    response = client.post(
        "/api/v1/backstage/closing/",
        {"quantities": {"RECON-SKU": "1"}},
        content_type="application/json",
    )

    assert response.status_code == 200
    closing = DayClosing.objects.get()
    assert closing.data["production_summary"]["recon-close"]["finished"] == 4
    assert "reconciliation_errors" in closing.data


@pytest.mark.django_db
def test_perform_day_closing_persists_cash_shift_summary(client, setup_stock, closing_user):
    terminal = POSTerminal.default()
    shift = CashShift.objects.create(
        terminal=terminal,
        operator=closing_user,
        opening_amount_q=1000,
    )
    shift.close(blind_closing_amount_q=1000)
    client.force_login(closing_user)

    response = client.post(
        "/api/v1/backstage/closing/",
        {"quantities": {"RECON-SKU": "0"}},
        content_type="application/json",
    )

    assert response.status_code == 200
    summary = DayClosing.objects.get().data["cash_shift_summary"]
    assert summary["closed_shifts"][0]["id"] == shift.pk
    assert summary["totals"]["blind_closing_amount_q"] == 1000


@pytest.mark.django_db
def test_day_closing_summarizes_payment_methods_and_cod_pending(client, setup_stock, closing_user):
    Order.objects.create(
        ref="RECON-PAY-SPLIT",
        channel_ref="pdv",
        status="completed",
        total_q=1500,
        data={
            "payment": {
                "method": "mixed",
                "tenders": [
                    {"method": "cash", "amount_q": 500, "collection": "terminal", "status": "received"},
                    {"method": "pix", "amount_q": 1000, "collection": "terminal", "status": "received"},
                ],
            }
        },
    )
    Order.objects.create(
        ref="RECON-PAY-COD",
        channel_ref="pdv",
        status="dispatched",
        total_q=1200,
        data={
            "payment": {
                "method": "cash",
                "collection": "on_delivery",
                "tenders": [{"method": "cash", "amount_q": 1200, "collection": "on_delivery", "status": "pending"}],
            }
        },
    )
    client.force_login(closing_user)

    response = client.post(
        "/api/v1/backstage/closing/",
        {"quantities": {"RECON-SKU": "0"}},
        content_type="application/json",
    )

    assert response.status_code == 200
    methods = DayClosing.objects.get().data["cash_shift_summary"]["payment_method_totals"]
    assert methods["cash"] == 500
    assert methods["pix"] == 1000
    assert methods["cod_pending_q"] == 1200
    assert methods["cod_pending_count"] == 1


@pytest.mark.django_db
def test_reconciliation_error_when_sold_exceeds_available(client, setup_stock, closing_user):
    order = Order.objects.create(ref="RECON-ORD", channel_ref="web", status="completed", total_q=3000)
    OrderItem.objects.create(order=order, line_id="1", sku="RECON-SKU", name="Recon", qty=5, unit_price_q=100, line_total_q=500)
    client.force_login(closing_user)

    response = client.post(
        "/api/v1/backstage/closing/",
        {"quantities": {"RECON-SKU": "0"}},
        content_type="application/json",
    )

    assert response.status_code == 200
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


@pytest.mark.django_db
def test_future_preorder_does_not_create_false_deficit(client, setup_stock, closing_user):
    """WP-D: encomenda vendida hoje para data futura NÃO conta como vendida
    hoje na reconciliação de estoque — a baixa só acontece na data combinada.
    Contá-la hoje fabricava um deficit falso (estoque nunca saiu)."""
    from datetime import timedelta

    from django.utils import timezone

    preorder = Order.objects.create(
        ref="RECON-ENC",
        channel_ref="web",
        status="confirmed",
        total_q=500,
        data={"delivery_date": (timezone.localdate() + timedelta(days=2)).isoformat()},
    )
    OrderItem.objects.create(order=preorder, line_id="1", sku="RECON-SKU", name="Recon", qty=5, unit_price_q=100, line_total_q=500)
    client.force_login(closing_user)

    response = client.post(
        "/api/v1/backstage/closing/",
        {"quantities": {"RECON-SKU": "2"}},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert DayClosing.objects.get().data["reconciliation_errors"] == []


@pytest.mark.django_db
def test_preorder_counts_in_reconciliation_of_the_delivery_day(setup_stock):
    """Contraprova: no fechamento DA DATA combinada a encomenda conta como
    vendida — ali o estoque saiu de verdade."""
    from datetime import timedelta

    from django.utils import timezone

    from shopman.backstage.services.closing import _reconciliation_errors

    delivery_day = timezone.localdate() + timedelta(days=2)
    preorder = Order.objects.create(
        ref="RECON-ENC-DIA",
        channel_ref="web",
        status="confirmed",
        total_q=500,
        data={"delivery_date": delivery_day.isoformat()},
    )
    OrderItem.objects.create(order=preorder, line_id="1", sku="RECON-SKU", name="Recon", qty=5, unit_price_q=100, line_total_q=500)

    errors = _reconciliation_errors(closing_date=delivery_day, items=[])

    assert errors == [{"sku": "RECON-SKU", "sold": 5, "available": 0, "deficit": 5}]


@pytest.mark.django_db
def test_build_day_closing_lists_upcoming_preorders(setup_stock):
    """WP-D: o fechamento informa as encomendas dos próximos dias (qtd + total),
    agregadas pela data combinada."""
    from datetime import timedelta

    from django.utils import timezone

    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    saturday = (timezone.localdate() + timedelta(days=3)).isoformat()
    Order.objects.create(ref="ENC-1", channel_ref="web", status="confirmed", total_q=1500, data={"delivery_date": tomorrow})
    Order.objects.create(ref="ENC-2", channel_ref="web", status="confirmed", total_q=2500, data={"delivery_date": tomorrow})
    Order.objects.create(ref="ENC-3", channel_ref="web", status="confirmed", total_q=1000, data={"delivery_date": saturday})
    # Cancelada e de hoje ficam de fora.
    Order.objects.create(ref="ENC-4", channel_ref="web", status="cancelled", total_q=999, data={"delivery_date": tomorrow})
    Order.objects.create(ref="HOJE-1", channel_ref="web", status="confirmed", total_q=999, data={"delivery_date": timezone.localdate().isoformat()})

    closing = build_day_closing()

    assert closing.has_upcoming_preorders is True
    assert [(row.date_display, row.orders_count, row.total_display) for row in closing.upcoming_preorders] == [
        ("amanhã", 2, "R$ 40,00"),
        (closing.upcoming_preorders[1].date_display, 1, "R$ 10,00"),
    ]
    assert closing.upcoming_preorders[0].total_q == 4000
