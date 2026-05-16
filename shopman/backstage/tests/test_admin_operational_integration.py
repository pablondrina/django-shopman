"""Admin/Unfold integration guardrails for operational Backstage surfaces."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.contrib.admin_unfold import admin as craftsman_admin
from shopman.craftsman.contrib.admin_unfold.admin import (
    WORK_ORDER_DATE_FROM_PARAM,
    WORK_ORDER_DATE_TO_PARAM,
)
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder
from shopman.offerman.models import Product
from shopman.orderman.admin import OrderAdmin
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.admin import navigation
from shopman.backstage.admin_console import production as admin_production
from shopman.backstage.projections.dashboard import build_dashboard
from shopman.shop.models import Shop


class AdminNavigationTests(TestCase):
    def test_sidebar_prioritizes_live_operation_and_backoffice_tools(self) -> None:
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("admin", "admin@example.com", "pw")

        groups = admin.site.get_sidebar_list(request)
        titles = [group["title"] for group in groups]

        self.assertEqual(titles[0], "Operação ao vivo")
        self.assertIn("Pedidos e canais", titles)
        self.assertIn("Produção", titles)
        self.assertIn("Auditoria e acesso", titles)
        self.assertNotIn("Regras", titles)

        live_items = [item["title"] for item in groups[0]["items"] if item["has_permission"]]
        self.assertEqual(live_items[:3], ["Pedidos", "Produção", "Fechamento"])

        production_group = next(group for group in groups if group["title"] == "Produção")
        production_items = [item["title"] for item in production_group["items"] if item["has_permission"]]
        self.assertEqual(
            production_items,
            ["Painel", "Planejamento", "Produção", "Fichas técnicas", "Relatórios"],
        )

    def test_sidebar_badges_count_operational_attention(self) -> None:
        Order.objects.create(
            ref="NAV-NEW",
            channel_ref="web",
            session_key="nav-session",
            status=Order.Status.NEW,
            total_q=1000,
            data={"payment": {"method": "cash"}},
        )

        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("admin2", "admin2@example.com", "pw")

        self.assertEqual(navigation.badge_new_orders(request), "1")

    def test_production_tabs_prioritize_work_orders(self) -> None:
        production_tabs = next(
            tab for tab in settings.UNFOLD["TABS"] if "craftsman.workorder" in tab["models"]
        )

        self.assertEqual(
            [item["title"] for item in production_tabs["items"]],
            ["Painel", "Planejamento", "Produção", "Fichas técnicas", "Relatórios"],
        )
        self.assertEqual(str(WorkOrder._meta.verbose_name_plural), "Produção")


class AdminDashboardSemanticsTests(TestCase):
    def test_production_kpi_uses_product_quantities_not_only_work_order_counts(self) -> None:
        recipe = Recipe.objects.create(
            ref="admin-ciabatta",
            name="Ciabatta",
            output_sku="CIABATTA",
            batch_size=10,
        )
        planned = craft.plan(recipe, 13, date=date.today())
        started = craft.plan(recipe, 8, date=date.today(), operator_ref="user:ana")
        craft.start(started, quantity=8, actor="test")
        finished = craft.plan(recipe, 5, date=date.today(), operator_ref="user:bia")
        craft.start(finished, quantity=5, actor="test")
        craft.finish(finished, finished=4, actor="test")

        production = build_dashboard().production

        self.assertEqual(production.open, 2)
        self.assertEqual(production.done, 1)
        self.assertEqual(production.planned_qty, "26")
        self.assertEqual(production.started_qty, "13")
        self.assertEqual(production.finished_qty, "4")
        self.assertEqual(production.loss_qty, "1")
        self.assertIn(planned.ref, [row.ref for row in production.wos])


class AdminProductionConsoleTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_superuser("operator", "operator@example.com", "pw")
        Shop.objects.create(name="Loja Operacional")
        self.client.defaults["HTTP_HOST"] = "localhost"
        self.client.force_login(self.user)
        self.recipe = Recipe.objects.create(
            ref="console-ciabatta",
            name="Ciabatta",
            output_sku="CIABATTA",
            batch_size=10,
        )

    def test_admin_production_console_renders_operational_surface(self) -> None:
        response = self.client.get(reverse("admin_console_production"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produção")
        self.assertContains(response, "Produção do dia")
        self.assertNotContains(response, "Piloto")
        self.assertNotContains(response, "Mapa de produção")
        self.assertNotContains(response, "Em produção")
        self.assertNotContains(response, "Perda")
        self.assertContains(response, reverse("admin_console_production_planning"))
        self.assertContains(response, reverse("admin_console_production_dashboard"))
        self.assertContains(response, reverse("admin_console_production_reports"))
        self.assertContains(response, reverse("admin:craftsman_recipe_changelist"))

    def test_operator_production_legacy_routes_do_not_exist(self) -> None:
        for route_name in (
            "backstage:production",
            "backstage:production_dashboard",
            "backstage:production_reports",
            "backstage:production_action",
            "backstage:production_void",
            "backstage:bulk_create_work_orders",
            "backstage:production_work_order_commitments",
        ):
            with self.assertRaises(NoReverseMatch, msg=route_name):
                reverse(route_name)

    def test_admin_production_console_links_to_work_order_range_filter(self) -> None:
        response = self.client.get(reverse("admin_console_production"))

        self.assertEqual(response.status_code, 200)
        today = timezone.localdate().isoformat()
        work_order_url = response.context["production_work_orders_today_url"]
        self.assertIn(f"{WORK_ORDER_DATE_FROM_PARAM}={today}", work_order_url)
        self.assertIn(f"{WORK_ORDER_DATE_TO_PARAM}={today}", work_order_url)
        self.assertNotIn("target_date__year", work_order_url)

    def test_admin_production_console_uses_unfold_expandable_table_data(self) -> None:
        craft.plan(self.recipe, 13, date=date.today())

        response = self.client.get(reverse("admin_console_production"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'x-data="{ rowOpen: false }"')
        self.assertContains(response, "expand_more")

        table = response.context["production_matrix_table"]
        self.assertTrue(table["collapsible"])
        self.assertEqual(table["headers"], ["", "SKU", "Planejado", "Produzido"])
        self.assertIn("Planejado", table["headers"])
        self.assertIn("Produzido", table["headers"])
        self.assertNotIn("Em produção", table["headers"])
        self.assertNotIn("Perda", table["headers"])
        self.assertEqual(table["rows"][0]["table"]["collapsible"], True)
        self.assertEqual(table["headers"][0], "")
        self.assertIn("CIABATTA", str(table["rows"][0]["cols"][1]))
        produced_cell = str(table["rows"][0]["cols"][3])
        self.assertIn("13 un.", produced_cell)
        self.assertIn("task_alt", produced_cell)

    def test_admin_production_planning_renders_controlled_planning_page(self) -> None:
        craft.plan(self.recipe, 13, date=date.today())

        response = self.client.get(reverse("admin_console_production_planning"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Planejamento")
        self.assertContains(response, "Planejamento do dia")
        self.assertContains(response, reverse("admin_console_production_weighing"))
        self.assertContains(response, "Recomendado")
        self.assertContains(response, "Compromisso")
        self.assertContains(response, "Planejado")
        self.assertContains(response, "Ajustar planejado")
        self.assertContains(response, 'role="dialog"')
        self.assertContains(response, "CIABATTA")
        self.assertEqual(
            response.context["production_planning_sections"][0]["table"]["headers"],
            ["", "SKU", "Recomendado", "Compromisso", "Planejado"],
        )

    def test_admin_planning_keeps_recommendation_and_commitment_independent_of_produced(self) -> None:
        finished_without_commitment = SimpleNamespace(
            committed_qty="12",
            order_commitments=(),
        )
        row = SimpleNamespace(
            recipe_pk=1,
            output_sku="CIABATTA",
            suggestion=SimpleNamespace(quantity="6", committed="6"),
            planned_orders=(),
            started_orders=(),
            finished_orders=(finished_without_commitment,),
            planned_qty="",
        )
        board = SimpleNamespace(
            selected_date=date.today().isoformat(),
            selected_position_ref="",
            selected_operator_ref="",
            selected_base_recipe="",
        )

        self.assertEqual(admin_production._row_suggested_qty(row), "6")
        self.assertEqual(admin_production._row_committed_qty(row), "6")
        self.assertEqual(admin_production._row_recommended_qty(row), "6")

        planning_entry = admin_production._planning_entry(row, board)
        self.assertIsNotNone(planning_entry)
        self.assertEqual(planning_entry["form"].initial["quantity"], "6")

    def test_admin_planning_uses_committed_units_as_recommended_floor(self) -> None:
        linked_order = SimpleNamespace(
            committed_qty="8",
            order_commitments=(SimpleNamespace(ref="O-1"),),
        )
        row = SimpleNamespace(
            recipe_pk=1,
            output_sku="CIABATTA",
            suggestion=SimpleNamespace(quantity="4", committed="6"),
            planned_orders=(linked_order,),
            started_orders=(),
            finished_orders=(),
            planned_qty="",
        )

        self.assertEqual(admin_production._row_suggested_qty(row), "4")
        self.assertEqual(admin_production._row_committed_qty(row), "8")
        self.assertEqual(admin_production._row_recommended_qty(row), "8")

    def test_admin_production_weighing_renders_thermal_tickets_from_saved_plan(self) -> None:
        base_recipe = Recipe.objects.create(
            ref="massa-ciabatta",
            name="Massa Ciabatta",
            output_sku="MASSA-CIABATTA",
            batch_size=10,
        )
        RecipeItem.objects.create(
            recipe=base_recipe,
            input_sku="FARINHA",
            quantity=Decimal("6"),
            unit="kg",
        )
        RecipeItem.objects.create(
            recipe=self.recipe,
            input_sku="MASSA-CIABATTA",
            quantity=Decimal("5"),
            unit="kg",
        )
        craft.plan(self.recipe, Decimal("20"), date=date.today())

        response = self.client.get(reverse("admin_console_production_weighing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Filipetas de pesagem")
        self.assertContains(response, "Derivadas do planejado salvo")
        self.assertContains(response, "Massa Ciabatta")
        self.assertContains(response, "10 kg")
        self.assertContains(response, "FARINHA")
        self.assertContains(response, "6 kg")
        self.assertContains(response, "CIABATTA 20 un.")
        self.assertNotContains(response, "planejado aprovado")
        self.assertEqual(len(response.context["production_weighing"].tickets), 1)

    def test_admin_production_does_not_split_operator_focus_by_status_tabs(self) -> None:
        craft.plan(self.recipe, 13, date=date.today())

        response = self.client.get(reverse("admin_console_production"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("production_tabs", response.context)
        self.assertNotContains(response, "Planejadas")

    def test_admin_production_console_mutates_through_shared_production_handler(self) -> None:
        response = self.client.post(
            reverse("admin_console_production"),
            {
                "action": "set_planned",
                "recipe": str(self.recipe.pk),
                "quantity": "13",
                "target_date": date.today().isoformat(),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("admin_console_production")))
        self.assertTrue(
            WorkOrder.objects.filter(
                recipe=self.recipe,
                output_sku="CIABATTA",
                quantity=13,
            ).exists()
        )

    def test_admin_production_produced_action_uses_approved_modal_wrapper(self) -> None:
        craft.plan(self.recipe, 13, date=date.today())

        response = self.client.get(reverse("admin_console_production"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produzir CIABATTA")
        self.assertContains(response, "Salvar produzido")
        self.assertContains(response, 'name="quantity"')
        self.assertContains(response, 'role="dialog"')
        self.assertContains(response, "z-[1000]")

    def test_admin_production_produced_action_blocks_ambiguous_multiple_open_orders(self) -> None:
        first = craft.plan(self.recipe, 20, date=date.today())
        second = craft.plan(self.recipe, 12, date=date.today())

        response = self.client.get(reverse("admin_console_production"))

        self.assertEqual(response.status_code, 200)
        produced_cell = str(response.context["production_matrix_table"]["rows"][0]["cols"][3])
        self.assertIn("2 OPs abertas", produced_cell)
        self.assertIn("Resolver", produced_cell)
        self.assertIn(first.ref, produced_cell)
        self.assertIn(second.ref, produced_cell)
        self.assertNotIn("20 un.", produced_cell)
        self.assertNotIn("12 un.", produced_cell)
        self.assertNotIn("task_alt", produced_cell)

    def test_admin_production_dashboard_renders_unfold_projection_page(self) -> None:
        craft.plan(self.recipe, 13, date=date.today())

        response = self.client.get(reverse("admin_console_production_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Painel de produção")
        self.assertContains(response, "Data agendada")
        self.assertContains(response, "Planejado")
        self.assertContains(response, "Rendimento médio")
        self.assertContains(response, "Tempo (min)")
        self.assertContains(response, "13 un.")
        self.assertContains(response, "1 OP")
        self.assertEqual(response.context["production_dashboard"].planned_qty, "13")
        self.assertIn("headers", response.context["production_dashboard_late_table"])

    def test_admin_production_reports_render_unfold_projection_page(self) -> None:
        work_order = craft.plan(self.recipe, 13, date=date.today())
        craft.finish(work_order, finished=12, actor="test")

        response = self.client.get(
            reverse("admin_console_production_reports"),
            {
                "report_kind": "history",
                "date_from": date.today().isoformat(),
                "date_to": date.today().isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Relatórios de produção")
        self.assertContains(response, "Histórico de ordens")
        self.assertContains(response, "Produtividade")
        self.assertContains(response, "Desperdício")
        self.assertContains(response, "Filtros do relatório")
        self.assertContains(response, 'role="dialog"')
        self.assertContains(response, "Data agendada")
        self.assertContains(response, "Concluído")
        self.assertContains(response, "Rendimento")
        self.assertContains(response, "Tempo (min)")
        self.assertContains(response, "CIABATTA")
        self.assertContains(response, "13 un.")
        self.assertContains(response, "12 un.")
        self.assertEqual(response.context["production_reports"].history_rows[0].ref, work_order.ref)
        self.assertEqual(
            [tab["title"] for tab in response.context["production_reports_tabs"]],
            ["Histórico de ordens", "Produtividade", "Desperdício"],
        )

    def test_admin_production_reports_export_csv(self) -> None:
        craft.plan(self.recipe, 13, date=date.today())

        response = self.client.get(
            reverse("admin_console_production_reports"),
            {
                "date_from": date.today().isoformat(),
                "date_to": date.today().isoformat(),
                "format": "csv",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment;", response["Content-Disposition"])


class OrderAdminSemanticsTests(TestCase):
    def test_order_admin_distinguishes_lines_from_units(self) -> None:
        order = Order.objects.create(
            ref="ADM-ORDER",
            channel_ref="web",
            session_key="adm-order-session",
            status=Order.Status.CONFIRMED,
            total_q=3000,
            data={"payment": {"method": "cash"}},
        )
        OrderItem.objects.create(
            order=order,
            line_id="1",
            sku="CIABATTA",
            name="Ciabatta",
            qty=3,
            unit_price_q=1000,
            line_total_q=3000,
        )
        OrderItem.objects.create(
            order=order,
            line_id="2",
            sku="BAGUETTE",
            name="Baguette",
            qty=10,
            unit_price_q=0,
            line_total_q=0,
        )

        model_admin = OrderAdmin(Order, admin.site)

        self.assertEqual(model_admin.items_count_display(order), "2")
        self.assertEqual(model_admin.units_count_display(order), "13")


class WorkOrderAdminSemanticsTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_superuser("wo-admin", "wo-admin@example.com", "pw")
        Shop.objects.create(name="Loja Operacional")
        self.client.force_login(self.user)

    def test_work_order_admin_defaults_to_today_range_filter(self) -> None:
        response = self.client.get(reverse("admin:craftsman_workorder_changelist"))

        self.assertEqual(response.status_code, 302)
        today = timezone.localdate().isoformat()
        self.assertIn(f"{WORK_ORDER_DATE_FROM_PARAM}={today}", response["Location"])
        self.assertIn(f"{WORK_ORDER_DATE_TO_PARAM}={today}", response["Location"])
        self.assertNotIn("target_date__year", response["Location"])

    def test_work_order_admin_keeps_focus_on_changelist(self) -> None:
        today = timezone.localdate().isoformat()

        response = self.client.get(
            reverse("admin:craftsman_workorder_changelist"),
            {
                WORK_ORDER_DATE_FROM_PARAM: today,
                WORK_ORDER_DATE_TO_PARAM: today,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produção do dia")
        self.assertNotContains(response, "Todas as OPs do dia")
        self.assertNotContains(response, "Agenda vencida")

    def test_work_order_admin_navigation_uses_unfold_row_actions(self) -> None:
        model_admin = admin.site._registry[WorkOrder]

        self.assertNotIn("operation_link_display", model_admin.list_display)
        self.assertIn("production_board_row", model_admin.actions_row)
        self.assertIn("commitments_row", model_admin.actions_row)
        self.assertIn("close_wo_row", model_admin.actions_row)
        self.assertIn("void_wo_row", model_admin.actions_row)

    def test_work_order_admin_expandable_row_shows_event_history(self) -> None:
        model_admin = admin.site._registry[WorkOrder]
        section = model_admin.list_sections[0]

        self.assertEqual(section.related_name, "events")
        self.assertEqual(str(section.verbose_name), "Histórico operacional")
        self.assertEqual(section.created_at.short_description, "Registrado em")

    def test_work_order_admin_displays_operator_quantities_without_decimal_noise(self) -> None:
        recipe = Recipe.objects.create(
            ref="wo-qty-ciabatta",
            name="Ciabatta",
            output_sku="CIABATTA",
            batch_size=10,
        )
        work_order = craft.plan(recipe, Decimal("14.000"), date=date.today())
        craft.finish(work_order, finished=Decimal("12.000"), expected_rev=0)
        work_order.refresh_from_db()
        model_admin = admin.site._registry[WorkOrder]

        planned = str(model_admin.planned_display(work_order))
        produced = str(model_admin.produced_display(work_order))
        loss = str(model_admin.loss_display(work_order))

        self.assertIn("14 un.", planned)
        self.assertIn("12 un.", produced)
        self.assertIn("2 un.", loss)
        self.assertNotIn("<span", planned)
        self.assertNotIn("14.00", planned)
        self.assertNotIn("12.00", produced)

    def test_work_order_admin_commitments_show_only_committed_units(self) -> None:
        recipe = Recipe.objects.create(
            ref="wo-commit-ciabatta",
            name="Ciabatta",
            output_sku="CIABATTA",
            batch_size=10,
        )
        work_order = craft.plan(recipe, Decimal("14.000"), date=date.today())
        model_admin = admin.site._registry[WorkOrder]

        with (
            patch.object(craftsman_admin, "_committed_order_refs", return_value=("O-1", "O-2")),
            patch.object(craftsman_admin, "_committed_qty_for_work_order", return_value=Decimal("14.000")),
        ):
            commitment = str(model_admin.commitments_display(work_order))

        self.assertIn("14 un.", commitment)
        self.assertNotIn("ped.", commitment)
        self.assertNotIn("<span", commitment)


class RecipeAdminSemanticsTests(TestCase):
    def test_recipe_admin_edits_ingredients_as_canonical_tabular_inline(self) -> None:
        Product.objects.create(sku="INS-FARINHA-T65", name="Farinha T65", unit="kg")
        recipe = Recipe.objects.create(
            ref="massa-base",
            name="Massa Base",
            output_sku="MASSA-BASE",
            batch_size=10,
        )
        model_admin = admin.site._registry[Recipe]
        inline = model_admin.inlines[0]
        form = craftsman_admin.RecipeItemInlineForm()
        recipe_form = craftsman_admin.RecipeAdminForm()
        sku_choices = dict(form.fields["input_sku"].choices)

        self.assertEqual(inline, craftsman_admin.RecipeItemInline)
        self.assertEqual(str(inline.verbose_name_plural), "Ingredientes")
        self.assertEqual(
            tuple(inline.fields),
            ("sort_order", "input_sku", "quantity", "unit", "is_optional"),
        )
        self.assertEqual(inline.ordering_field, "sort_order")
        self.assertTrue(inline.hide_ordering_field)
        self.assertIsInstance(form.fields["input_sku"].widget, craftsman_admin.UnfoldAdminSelect2Widget)
        self.assertIsInstance(form.fields["unit"].widget, craftsman_admin.UnfoldAdminSelectWidget)
        self.assertIsInstance(recipe_form.fields["output_sku"].widget, craftsman_admin.UnfoldAdminSelect2Widget)
        self.assertEqual(str(Recipe._meta.verbose_name), "Ficha técnica")
        self.assertEqual(str(Recipe._meta.verbose_name_plural), "Fichas técnicas")
        self.assertEqual(str(Recipe._meta.get_field("output_sku").verbose_name), "SKU produzido")
        self.assertEqual(str(recipe_form.fields["output_sku"].label), "SKU produzido")
        self.assertEqual(str(recipe_form.fields["batch_size"].label), "Rendimento base")
        self.assertEqual(str(Recipe._meta.get_field("batch_size").verbose_name), "Rendimento base")
        self.assertIn("ficha técnica base", str(Recipe._meta.get_field("batch_size").help_text))
        flattened_fieldsets = _flatten_fieldsets(model_admin.fieldsets)
        self.assertIn("steps_text", flattened_fieldsets)
        self.assertIn("max_started_minutes", flattened_fieldsets)
        self.assertIn("capacity_per_day", flattened_fieldsets)
        self.assertIn("requires_batch_tracking", flattened_fieldsets)
        self.assertNotIn("steps", flattened_fieldsets)
        self.assertNotIn("meta", flattened_fieldsets)
        self.assertIn("INS-FARINHA-T65", sku_choices)
        self.assertIn("MASSA-BASE", sku_choices)
        self.assertIn(("kg", "kg"), RecipeItem._meta.get_field("unit").choices)
        self.assertNotIn(("zufts", "zufts"), RecipeItem._meta.get_field("unit").choices)

        item = RecipeItem(recipe=recipe, input_sku="INS-FARINHA-T65", quantity=Decimal("1"), unit="zufts")
        with self.assertRaises(ValidationError):
            item.full_clean()

        mismatched = RecipeItem(recipe=recipe, input_sku="INS-FARINHA-T65", quantity=Decimal("100"), unit="g")
        with self.assertRaises(ValidationError):
            mismatched.full_clean()

    def test_recipe_admin_maps_operational_fields_to_structured_recipe_data(self) -> None:
        Product.objects.create(sku="CIABATTA", name="Ciabatta", unit="un")

        form = craftsman_admin.RecipeAdminForm(data={
            "ref": "ciabatta-v1",
            "name": "Ciabatta",
            "is_active": "on",
            "output_sku": "CIABATTA",
            "batch_size": "12",
            "steps_text": "Mistura\nModelagem\nForno",
            "max_started_minutes": "90",
            "capacity_per_day": "120",
            "requires_batch_tracking": "on",
            "shelf_life_days": "1",
        })

        self.assertTrue(form.is_valid(), form.errors)
        recipe = form.save()

        self.assertEqual(recipe.steps, ["Mistura", "Modelagem", "Forno"])
        self.assertEqual(recipe.meta["max_started_minutes"], 90)
        self.assertEqual(recipe.meta["capacity_per_day"], "120")
        self.assertEqual(recipe.meta["requires_batch_tracking"], True)
        self.assertEqual(recipe.meta["shelf_life_days"], 1)


def test_legacy_admin_operational_templates_removed():
    root = Path(__file__).resolve().parents[3]

    assert not (root / "shopman/shop/templates/admin/shop/production.html").exists()
    assert not (root / "shopman/shop/templates/admin/shop/closing.html").exists()


def _flatten_fieldsets(fieldsets) -> list[str]:
    result: list[str] = []
    for _, options in fieldsets:
        for field in options.get("fields", ()):
            if isinstance(field, (tuple, list)):
                result.extend(field)
            else:
                result.append(field)
    return result
