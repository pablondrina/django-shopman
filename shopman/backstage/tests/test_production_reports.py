from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from shopman.backstage.projections.production import build_production_reports
from shopman.backstage.services.production import export_reports_csv
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.shop.models import Shop
from shopman.stockman import Position


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="report-cafe",
        name="Café especial",
        output_sku="CAFE-ESP",
        batch_size=Decimal("10"),
        meta={"capacity_per_day": 100},
    )


@pytest.fixture
def other_recipe(db):
    return Recipe.objects.create(
        ref="report-pao",
        name="Pão francês",
        output_sku="PAO-FRA",
        batch_size=Decimal("10"),
    )


@pytest.fixture
def report_data(db, recipe, other_recipe):
    Position.objects.create(ref="forno", name="Forno", is_default=True)
    Position.objects.create(ref="balcao", name="Balcão")
    today = date.today()
    planned = craft.plan(recipe, 20, date=today, position_ref="forno", operator_ref="ana")
    started = craft.plan(recipe, 30, date=today, position_ref="forno", operator_ref="bia")
    craft.start(started, quantity=30, position_ref="forno", operator_ref="bia", expected_rev=0)
    finished = craft.plan(recipe, 40, date=today, position_ref="forno", operator_ref="ana")
    craft.start(finished, quantity=40, position_ref="forno", operator_ref="ana", expected_rev=0)
    craft.finish(finished, finished=36, actor="ana")
    old = craft.plan(other_recipe, 10, date=today - timedelta(days=10), position_ref="balcao", operator_ref="caio")
    return {"today": today, "planned": planned, "started": started, "finished": finished, "old": old}


@pytest.mark.django_db
def test_history_report_returns_work_order_shape(report_data):
    report = build_production_reports({"date_from": report_data["today"], "date_to": report_data["today"]})

    assert len(report.history_rows) == 3
    row = next(row for row in report.history_rows if row.ref == report_data["finished"].ref)
    assert row.recipe_ref == "report-cafe"
    assert row.qty_planned == "40"
    assert row.qty_finished == "36"
    assert row.qty_loss == "4"
    assert row.yield_rate == "90%"


@pytest.mark.django_db
def test_operator_productivity_aggregates_finished_only(report_data):
    report = build_production_reports({
        "date_from": report_data["today"],
        "date_to": report_data["today"],
        "report_kind": "operator_productivity",
    })

    assert [row.operator_ref for row in report.operator_rows] == ["ana"]
    assert report.operator_rows[0].wo_count == 1
    assert report.operator_rows[0].qty_total == "36"


@pytest.mark.django_db
def test_recipe_waste_returns_top_waste_rows(report_data):
    report = build_production_reports({
        "date_from": report_data["today"],
        "date_to": report_data["today"],
        "report_kind": "recipe_waste",
    })

    assert report.waste_rows[0].recipe_ref == "report-cafe"
    assert report.waste_rows[0].loss_total == "4"


@pytest.mark.django_db
def test_date_range_filter_excludes_old_work_orders(report_data):
    report = build_production_reports({"date_from": report_data["today"], "date_to": report_data["today"]})

    assert report_data["old"].ref not in [row.ref for row in report.history_rows]


@pytest.mark.django_db
def test_recipe_filter_reduces_history_set(report_data):
    report = build_production_reports({
        "date_from": report_data["today"] - timedelta(days=20),
        "date_to": report_data["today"],
        "recipe_ref": "report-pao",
    })

    assert [row.ref for row in report.history_rows] == [report_data["old"].ref]


@pytest.mark.django_db
def test_position_operator_and_status_filters(report_data):
    report = build_production_reports({
        "date_from": report_data["today"],
        "date_to": report_data["today"],
        "position_ref": "forno",
        "operator_ref": "bia",
        "status": WorkOrder.Status.STARTED,
    })

    assert [row.ref for row in report.history_rows] == [report_data["started"].ref]


@pytest.mark.django_db
def test_inverted_range_is_normalized(report_data):
    report = build_production_reports({"date_from": report_data["today"], "date_to": report_data["today"] - timedelta(days=1)})

    assert report.filters.date_from == report_data["today"] - timedelta(days=1)
    assert report.filters.date_to == report_data["today"]


@pytest.mark.django_db
def test_missing_recipe_filter_returns_empty(report_data):
    report = build_production_reports({
        "date_from": report_data["today"],
        "date_to": report_data["today"],
        "recipe_ref": "missing",
    })

    assert report.history_rows == ()


@pytest.mark.django_db
def test_csv_export_has_bom_pt_br_header_and_accents(report_data):
    data = export_reports_csv("history", {"date_from": report_data["today"], "date_to": report_data["today"]})

    assert data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    assert "Qtd planejada" in text
    assert "Café especial" in text
    assert report_data["today"].isoformat() in text


@pytest.mark.django_db
def test_csv_export_operator_productivity_header(report_data):
    text = export_reports_csv(
        "operator_productivity",
        {"date_from": report_data["today"], "date_to": report_data["today"]},
    ).decode("utf-8-sig")

    assert "Operador,Nome,Ordens finalizadas,Qtd total,Yield médio" in text


@pytest.mark.django_db
def test_csv_export_recipe_waste_header(report_data):
    text = export_reports_csv(
        "recipe_waste",
        {"date_from": report_data["today"], "date_to": report_data["today"]},
    ).decode("utf-8-sig")

    first_line = text.splitlines()[0]
    assert "Receita" in first_line
    assert "Perda" in first_line or "Loss" in first_line.lower()


@pytest.mark.django_db
def test_reports_view_permission_and_csv_download(client, report_data):
    Shop.objects.create(name="Loja")
    staff = User.objects.create_user("staff", password="pw", is_staff=True)
    client.force_login(staff)

    response = client.get(reverse("backstage:production_reports"))
    assert response.status_code == 403

    admin = User.objects.create_superuser("admin", "a@test.com", "pw")
    client.force_login(admin)
    response = client.get(reverse("backstage:production_reports"), {
        "date_from": report_data["today"].isoformat(),
        "date_to": report_data["today"].isoformat(),
        "format": "csv",
    })
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith('attachment; filename="producao_history_')


@pytest.mark.django_db
def test_csv_response_has_utf8_content_type_and_bom(client, report_data):
    Shop.objects.create(name="Loja")
    admin = User.objects.create_superuser("admin", "a@test.com", "pw")
    client.force_login(admin)

    response = client.get(reverse("backstage:production_reports"), {
        "date_from": report_data["today"].isoformat(),
        "date_to": report_data["today"].isoformat(),
        "format": "csv",
        "report_kind": "operator_productivity",
    })
    assert response.status_code == 200
    assert "text/csv" in response["Content-Type"]
    assert "charset=utf-8" in response["Content-Type"]
    body = b"".join(response.streaming_content)
    assert body.startswith(b"\xef\xbb\xbf")
    assert "Operador" in body.decode("utf-8-sig")


@pytest.mark.django_db
def test_invalid_report_kind_falls_back_to_history(client, report_data):
    Shop.objects.create(name="Loja")
    admin = User.objects.create_superuser("admin", "a@test.com", "pw")
    client.force_login(admin)

    response = client.get(reverse("backstage:production_reports"), {
        "date_from": report_data["today"].isoformat(),
        "date_to": report_data["today"].isoformat(),
        "report_kind": "; DROP TABLE",
    })
    assert response.status_code == 200
    # invalid kind silently coerced to history
    assert response.context["report_kind"] == "history"


@pytest.mark.django_db
def test_invalid_dates_fall_back_to_default_window(client, report_data):
    Shop.objects.create(name="Loja")
    admin = User.objects.create_superuser("admin", "a@test.com", "pw")
    client.force_login(admin)

    response = client.get(reverse("backstage:production_reports"), {
        "date_from": "not-a-date",
        "date_to": "also-not-a-date",
    })
    assert response.status_code == 200
    filters = response.context["filters"]
    today = date.today()
    assert filters.date_to == today
    assert filters.date_from == today - timedelta(days=6)
