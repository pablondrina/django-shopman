"""Admin/Unfold integration guardrails for operational Backstage surfaces."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse
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
from shopman.backstage.projections.dashboard import build_dashboard
from shopman.shop.models import Shop


class AdminNavigationTests(TestCase):
    def test_sidebar_prioritizes_live_operation_and_backoffice_tools(self) -> None:
        from django.test import override_settings

        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("admin", "admin@example.com", "pw")

        # Pedidos e Produção são apps Nuxt headless (env-gated); configurados,
        # lideram a operação ao vivo. O console Admin de produção saiu
        # (WP-ADM-7d): "Produção ao vivo" (Fournil) é o único item de produção,
        # e carrega o badge de OPs iniciadas.
        with override_settings(
            SHOPMAN_ORDERS_BASE_URL="https://gestor.example.com",
            SHOPMAN_PRODUCTION_BASE_URL="https://fournil.example.com",
        ):
            groups = admin.site.get_sidebar_list(request)
        titles = [group["title"] for group in groups]

        self.assertEqual(titles[0], "Operação ao vivo")
        self.assertIn("Pedidos e canais", titles)
        self.assertIn("Produção", titles)
        self.assertIn("Auditoria e acesso", titles)
        self.assertNotIn("Regras", titles)

        live = {item["title"]: item for item in groups[0]["items"] if item["has_permission"]}
        live_items = list(live)
        self.assertEqual(live_items[:2], ["Pedidos", "Fechamento"])
        self.assertNotIn("Produção", live_items)
        self.assertIn("Produção ao vivo", live_items)
        self.assertEqual(live["Produção ao vivo"]["link"], "https://fournil.example.com")

        with override_settings(SHOPMAN_PRODUCTION_BASE_URL="https://fournil.example.com"):
            raw_live = navigation.get_sidebar_navigation(request)[0]["items"]
        raw_fournil = next(item for item in raw_live if item["title"] == "Produção ao vivo")
        self.assertEqual(
            raw_fournil["badge"],
            "shopman.backstage.admin.navigation.badge_started_work_orders",
        )

    def test_pos_nav_item_hidden_without_url_shown_when_configured(self) -> None:
        """POS é Nuxt headless: sem SHOPMAN_POS_BASE_URL o item some (sem link morto);
        configurado, aponta para a superfície Nuxt."""
        from django.test import override_settings

        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("posnav", "posnav@example.com", "pw")

        with override_settings(SHOPMAN_POS_BASE_URL=""):
            groups = admin.site.get_sidebar_list(request)
            live = {item["title"]: item for item in groups[0]["items"]}
            self.assertNotIn("POS", live)

        with override_settings(
            SHOPMAN_POS_BASE_URL="https://pos.example.com",
            SHOPMAN_PRODUCTION_BASE_URL="",
        ):
            groups = admin.site.get_sidebar_list(request)
            live = {item["title"]: item for item in groups[0]["items"]}
            self.assertIn("POS", live)
            self.assertEqual(live["POS"]["link"], "https://pos.example.com")

        # WP-ADM-7d: sem base URL do Fournil o grupo Produção fica só com o CRUD
        # de fichas; "Relatórios" (superfície Nuxt) é env-gated e some.
        production_group = next(group for group in groups if group["title"] == "Produção")
        production_items = [item["title"] for item in production_group["items"] if item["has_permission"]]
        self.assertEqual(production_items, ["Fichas técnicas"])

        audit_group = next(group for group in groups if group["title"] == "Auditoria e acesso")
        audit_items = [item["title"] for item in audit_group["items"] if item["has_permission"]]
        self.assertIn("Pagamentos", audit_items)

    def test_production_reports_nav_item_is_env_gated_to_fournil(self) -> None:
        """WP-ADM-7d: "Relatórios" do grupo Produção aponta p/ o Fournil
        (/reports) e some sem SHOPMAN_PRODUCTION_BASE_URL (sem link morto)."""
        from django.test import override_settings

        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("prodnav", "prodnav@example.com", "pw")

        with override_settings(SHOPMAN_PRODUCTION_BASE_URL="https://fournil.example.com"):
            groups = admin.site.get_sidebar_list(request)
        production_group = next(group for group in groups if group["title"] == "Produção")
        items = {item["title"]: item for item in production_group["items"] if item["has_permission"]}

        self.assertEqual(list(items), ["Fichas técnicas", "Relatórios"])
        self.assertEqual(items["Relatórios"]["link"], "https://fournil.example.com/reports")

    def test_orders_and_kds_nav_items_are_env_gated(self) -> None:
        """Pedidos e KDS são apps Nuxt headless: sem base URL somem (sem link morto);
        configurados, apontam para a superfície Nuxt."""
        from django.test import override_settings

        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("opsnav", "opsnav@example.com", "pw")

        with override_settings(SHOPMAN_ORDERS_BASE_URL="", SHOPMAN_KDS_BASE_URL=""):
            live = {item["title"]: item for item in admin.site.get_sidebar_list(request)[0]["items"]}
            self.assertNotIn("Pedidos", live)
            self.assertNotIn("KDS", live)

        with override_settings(
            SHOPMAN_ORDERS_BASE_URL="https://gestor.example.com",
            SHOPMAN_KDS_BASE_URL="https://kds.example.com",
        ):
            live = {item["title"]: item for item in admin.site.get_sidebar_list(request)[0]["items"]}
            self.assertEqual(live["Pedidos"]["link"], "https://gestor.example.com")
            self.assertEqual(live["KDS"]["link"], "https://kds.example.com")

    def test_sidebar_groups_all_store_config_under_one_discoverable_group(self) -> None:
        """WP-2 — config da loja num grupo 'Configurações' descobrível."""
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("cfg", "cfg@example.com", "pw")

        groups = admin.site.get_sidebar_list(request)
        config_group = next(group for group in groups if group["title"] == "Configurações")
        config_items = {item["title"] for item in config_group["items"] if item["has_permission"]}

        # Tudo que é config vive aqui — incl. as páginas focadas da Loja (WP-7).
        for expected in {
            "Loja & contato", "Marca & aparência", "Horários & operação",
            "Cardápio", "Pedidos & entrega", "Fidelidade", "PDV & alertas",
            "Produção", "Integrações",
            "Canais", "Promoções", "Cupons",
            "Regras de preço", "Faixas de distância", "Zonas de entrega",
            "Grupos de clientes", "Copy Omotenashi", "Templates de notificação",
            "Estações KDS", "POS tabs",
        }:
            self.assertIn(expected, config_items)

        # E saiu dos grupos de DADOS onde estava disperso.
        orders_group = next(group for group in groups if group["title"] == "Pedidos e canais")
        orders_items = {item["title"] for item in orders_group["items"]}
        self.assertNotIn("Canais", orders_items)
        self.assertNotIn("POS tabs", orders_items)

        catalog_group = next(group for group in groups if group["title"] == "Catálogo")
        catalog_items = {item["title"] for item in catalog_group["items"]}
        self.assertNotIn("Promoções", catalog_items)
        self.assertNotIn("Loja & contato", catalog_items)

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

    def test_production_tabs_keep_crud_only_after_console_removal(self) -> None:
        """WP-ADM-7d: as tabs do craftsman só linkam CRUD (fichas + ordens);
        painel/planejamento/relatórios vivem no Fournil."""
        production_tabs = next(
            tab for tab in settings.UNFOLD["TABS"] if "craftsman.workorder" in tab["models"]
        )

        self.assertEqual(
            [item["title"] for item in production_tabs["items"]],
            ["Fichas técnicas", "Ordens de produção"],
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


# O console Admin/Unfold de produção (matriz, planejamento, painel, pesagem,
# compromissos e relatórios) foi removido no WP-ADM-7d: a superfície canônica
# é o Fournil (surfaces/production-nuxt) via api/v1/backstage/production/*
# (paridade fechada no WP-ADM-7b). A cobertura vive em
# test_api_production_reports.py e nos testes da API de produção.


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
        # WP-ADM-7d: a visão de compromissos saiu com o console de produção;
        # os pedidos vinculados aparecem no board do Fournil.
        self.assertNotIn("commitments_row", model_admin.actions_row)
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
        Product.objects.create(sku="FARINHA-T65", name="Farinha T65", unit="kg")
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
            ("sort_order", "input_sku", "quantity", "unit", "is_optional", "diet", "allergens_text"),
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
        self.assertIn("FARINHA-T65", sku_choices)
        self.assertIn("MASSA-BASE", sku_choices)
        self.assertIn(("kg", "kg"), RecipeItem._meta.get_field("unit").choices)
        self.assertNotIn(("zufts", "zufts"), RecipeItem._meta.get_field("unit").choices)

        item = RecipeItem(recipe=recipe, input_sku="FARINHA-T65", quantity=Decimal("1"), unit="zufts")
        with self.assertRaises(ValidationError):
            item.full_clean()

        mismatched = RecipeItem(recipe=recipe, input_sku="FARINHA-T65", quantity=Decimal("100"), unit="g")
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
