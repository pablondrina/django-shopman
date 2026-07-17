"""Headless production reports API (api/v1/backstage/production/reports|management|weighing/blind-map).

Covers the manager-persona REST surface that the ``/reports`` page of the
production-nuxt app (``fournil.``) consumes: report rows (history, operator
productivity, recipe waste) with CSV export, the day-level management KPIs
(average yield, capacity, late orders) and the blind-code ↔ prep map. Gated by
the fine-grained ``backstage.view_production_reports`` permission — the coarse
floor gate (``backstage.operate_production``) does NOT open these endpoints,
so the kiosk screens stay blind by design.

Reuses ``build_production_reports``/``build_production_dashboard``/
``export_reports_csv``; no report logic is duplicated here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.stockman import Position

from shopman.backstage.models import DayClosing


def _perm(codename: str) -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename=codename,
    )


@pytest.fixture
def floor_operator(db):
    """Operador de chão: só o gate grosso do kiosk — SEM relatórios."""
    user = User.objects.create_user("prod-floor", password="pw", is_staff=True)
    user.user_permissions.add(_perm("operate_production"))
    return user


@pytest.fixture
def manager(db):
    user = User.objects.create_user("prod-manager", password="pw", is_staff=True)
    user.user_permissions.add(_perm("view_production_reports"))
    return user


@pytest.fixture
def report_data(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Relatórios")
    Position.objects.create(ref="forno", name="Forno", is_default=True)
    recipe = Recipe.objects.create(
        ref="report-api-pao",
        name="Pão de Relatório",
        output_sku="PAO-REL",
        batch_size=Decimal("10"),
        meta={"capacity_per_day": 100},
    )
    today = date.today()
    finished = craft.plan(recipe, 20, date=today, position_ref="forno", operator_ref="ana")
    craft.start(finished, quantity=20, position_ref="forno", operator_ref="ana", expected_rev=0)
    craft.finish(finished, finished=18, actor="ana")
    planned = craft.plan(recipe, 30, date=today, position_ref="forno", operator_ref="bia")
    return {"today": today, "recipe": recipe, "finished": finished, "planned": planned}


# ── Gate (perm fina ≠ gate grosso do chão) ───────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    [
        "api-backstage-production-reports",
        "api-backstage-production-management",
        "api-backstage-production-blind-map",
    ],
)
def test_floor_gate_does_not_open_manager_endpoints(client, floor_operator, url_name):
    client.force_login(floor_operator)
    assert client.get(reverse(url_name)).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    [
        "api-backstage-production-reports",
        "api-backstage-production-management",
        "api-backstage-production-blind-map",
    ],
)
def test_manager_perm_opens_endpoints(client, manager, report_data, url_name):
    client.force_login(manager)
    assert client.get(reverse(url_name)).status_code == 200


# ── Reports ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_reports_payload_shape(client, manager, report_data):
    client.force_login(manager)
    response = client.get(
        reverse("api-backstage-production-reports"),
        {"date_from": report_data["today"].isoformat(), "date_to": report_data["today"].isoformat()},
    )
    assert response.status_code == 200
    reports = response.json()["reports"]
    assert reports["filters"]["date_from"] == report_data["today"].isoformat()
    assert reports["filters"]["report_kind"] == "history"

    refs = {row["ref"] for row in reports["history_rows"]}
    assert {report_data["finished"].ref, report_data["planned"].ref} <= refs
    finished_row = next(row for row in reports["history_rows"] if row["ref"] == report_data["finished"].ref)
    assert finished_row["qty_planned"] == "20"
    assert finished_row["qty_finished"] == "18"
    assert finished_row["qty_loss"] == "2"
    assert finished_row["yield_rate"] == "90%"

    assert [row["operator_ref"] for row in reports["operator_rows"]] == ["ana"]
    assert reports["waste_rows"][0]["recipe_ref"] == "report-api-pao"
    assert {recipe["ref"] for recipe in reports["available_recipes"]} == {"report-api-pao"}
    assert {position["ref"] for position in reports["available_positions"]} == {"forno"}


@pytest.mark.django_db
def test_reports_filters_reduce_history(client, manager, report_data):
    client.force_login(manager)
    response = client.get(
        reverse("api-backstage-production-reports"),
        {
            "date_from": report_data["today"].isoformat(),
            "date_to": report_data["today"].isoformat(),
            "operator_ref": "bia",
        },
    )
    rows = response.json()["reports"]["history_rows"]
    assert [row["ref"] for row in rows] == [report_data["planned"].ref]


@pytest.mark.django_db
def test_reports_csv_download(client, manager, report_data):
    client.force_login(manager)
    response = client.get(
        reverse("api-backstage-production-reports"),
        {
            "format": "csv",
            "report_kind": "history",
            "date_from": report_data["today"].isoformat(),
            "date_to": report_data["today"].isoformat(),
        },
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    disposition = response["Content-Disposition"]
    assert disposition.startswith('attachment; filename="producao_history_')
    text = response.content.decode("utf-8-sig")
    assert "Qtd planejada" in text
    assert report_data["finished"].ref in text


@pytest.mark.django_db
def test_reports_csv_requires_manager_perm(client, floor_operator):
    client.force_login(floor_operator)
    response = client.get(reverse("api-backstage-production-reports"), {"format": "csv"})
    assert response.status_code == 403


# ── Management KPIs ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_management_returns_day_kpis(client, manager, report_data):
    client.force_login(manager)
    response = client.get(
        reverse("api-backstage-production-management"),
        {"date": report_data["today"].isoformat()},
    )
    assert response.status_code == 200
    management = response.json()["management"]
    assert management["selected_date"] == report_data["today"].isoformat()
    assert management["average_yield_rate"] == "90%"
    # planned 20 + 30 = 50 sobre capacity_per_day 100 → 50%
    assert management["capacity_percent"] == 50
    assert management["finished_orders"] == 1
    assert isinstance(management["late_orders"], list)


# ── Blind map (visão de gestor; o chão segue cego) ──────────────────────────


@pytest.mark.django_db
def test_blind_map_correlates_codes_to_preps(client, manager, report_data):
    client.force_login(manager)
    response = client.get(
        reverse("api-backstage-production-blind-map"),
        {"date": report_data["today"].isoformat()},
    )
    assert response.status_code == 200
    blind_map = response.json()["blind_map"]
    assert blind_map["selected_date"] == report_data["today"].isoformat()
    rows = blind_map["rows"]
    assert len(rows) == 1  # só a OP planejada segue aberta (a concluída não pesa mais)
    assert rows[0]["name"] == "Pão de Relatório"
    assert rows[0]["code"]
    assert set(rows[0]) == {"code", "name", "output_quantity_display"}
