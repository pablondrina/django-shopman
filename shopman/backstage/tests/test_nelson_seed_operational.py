"""Nelson seed coverage for operator production surfaces."""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder
from shopman.guestman.models import Customer
from shopman.offerman.models import Product
from shopman.orderman.models import IdempotencyKey, Order, OrderItem, Session
from shopman.payman.models import PaymentIntent
from shopman.stockman.models import Batch, Position

from shopman.backstage.models import (
    KDSInstance,
    OperationChecklistRun,
    OperationChecklistTemplate,
    OperatorAlert,
    POSTab,
)
from shopman.backstage.services.omotenashi_qa import build_omotenashi_qa_report


@pytest.mark.django_db
def test_nelson_seed_populates_production_history_alerts_and_batches(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")
    call_command("seed", "--flush", stdout=StringIO())

    assert not Product.objects.filter(sku__startswith="DEMO-").exists()
    for sku in ("BAGUETE", "ESPRESSO", "COMBO-PETIT-DEJ"):
        fiscal = Product.objects.get(sku=sku).metadata["fiscal"]
        assert fiscal["ncm"]
        assert fiscal["cfop"] == "5102"
        assert fiscal["icms_situacao_tributaria"] == "102"
    croissant_history = [
        item
        for item in OrderItem.objects.filter(sku="CROISSANT").select_related("order")
        if (item.meta or {}).get("source") == "production_demand_history"
    ]
    assert len(croissant_history) >= 4
    assert not Order.objects.filter(ref__startswith="NB-").exists()
    assert all(
        ref.split("-")[1] == created_at.strftime("%y%m%d")
        for ref, created_at in Order.objects.values_list("ref", "created_at")
        if len(ref.split("-")) >= 3
    )
    assert set(POSTab.objects.values_list("ref", flat=True)) >= {
        "00001007",
        "00001008",
        "00001009",
        "00001010",
        "00001011",
        "00001012",
    }
    assert Session.objects.filter(
        channel_ref="pdv",
        state="open",
        handle_type="pos_tab",
        handle_ref="00001007",
        data__tab_ref="00001007",
    ).exists()

    recipe = Recipe.objects.get(ref="croissant")
    assert recipe.meta["requires_batch_tracking"] is True
    assert recipe.meta["max_started_minutes"] > 0
    assert recipe.steps

    # Buyman Material master (WP-B4): insumos viram Material first-class (sku sem
    # prefixo INS-), com unit + shelf-life. Os input_sku das receitas resolvem.
    from shopman.buyman.models import Material

    assert Material.objects.count() == 23
    farinha = Material.objects.get(sku="FARINHA-T65")
    assert (farinha.unit, farinha.shelf_life_days) == ("kg", 180)
    assert farinha.metadata["allergens"] == ["glúten"]
    assert Material.objects.get(sku="AGUA").shelf_life_days is None  # não perecível
    assert Material.objects.get(sku="FERMENTO-NAT").shelf_life_days == 7
    # Todo input de receita resolve: insumo cru (Material), intermediário (output
    # de outra receita, ex. MASSA-*) ou produto. Sem inputs órfãos pós-rename.
    recipe_inputs = set(RecipeItem.objects.values_list("input_sku", flat=True))
    material_skus = set(Material.objects.values_list("sku", flat=True))
    intermediate_skus = set(Recipe.objects.values_list("output_sku", flat=True))
    product_skus = set(Product.objects.values_list("sku", flat=True))
    unresolved = recipe_inputs - material_skus - intermediate_skus - product_skus
    assert not unresolved, f"inputs de receita sem resolução: {unresolved}"
    # E os insumos crus de fato vêm do Material (interseção não-vazia).
    assert recipe_inputs & material_skus

    suggestions = craft.suggest(date.today() + timedelta(days=1), output_skus=["CROISSANT"])
    assert suggestions
    assert suggestions[0].quantity > 0

    assert WorkOrder.objects.filter(source_ref__startswith="seed:production:today:").exists()
    assert Batch.objects.filter(sku="CROISSANT").exists()
    assert set(Position.objects.filter(ref__in=["massa", "molde", "forno"]).values_list("ref", flat=True)) == {
        "massa",
        "molde",
        "forno",
    }
    assert OperatorAlert.objects.filter(type="production_late", acknowledged=False).exists()
    assert OperatorAlert.objects.filter(type="production_low_yield", acknowledged=False).exists()
    assert OperatorAlert.objects.filter(type="production_stock_short", acknowledged=False).exists()
    assert set(KDSInstance.objects.values_list("ref", flat=True)) >= {"cafes", "lanches", "encomendas", "expedicao"}
    assert set(OperationChecklistTemplate.objects.values_list("ref", flat=True)) >= {
        "nelson-opening",
        "nelson-routine",
        "nelson-closing",
    }
    assert OperationChecklistRun.objects.filter(template__ref="nelson-opening", status="completed").exists()
    assert OperationChecklistRun.objects.filter(template__ref="nelson-routine", status="open").exists()
    assert OperationChecklistRun.objects.filter(template__ref="nelson-closing", status="completed").exists()

    edge_orders = list(Order.objects.filter(snapshot__seed_namespace="security_reliability_edges"))
    edge_keys = {order.snapshot["seed_key"] for order in edge_orders}
    assert edge_keys >= {
        "security:payment-pending-near-expiry",
        "security:payment-expired-low-attention",
        "security:payment-after-cancel",
        "security:ifood-stale-confirmation",
    }

    edge_order_refs = {order.ref for order in edge_orders}
    assert PaymentIntent.objects.filter(order_ref__in=edge_order_refs, status=PaymentIntent.Status.PENDING).count() >= 2
    assert PaymentIntent.objects.filter(order_ref__in=edge_order_refs, status=PaymentIntent.Status.CAPTURED).exists()
    for intent in PaymentIntent.objects.filter(status=PaymentIntent.Status.CAPTURED):
        order = Order.objects.get(ref=intent.order_ref)
        assert ((order.data or {}).get("payment") or {}).get("intent_ref") == intent.ref
    assert OperatorAlert.objects.filter(type="payment_after_cancel", severity="critical", acknowledged=False).exists()
    assert OperatorAlert.objects.filter(type="stale_new_order", severity="error", acknowledged=False).exists()
    assert IdempotencyKey.objects.filter(scope="webhook:efi-pix", status="done").exists()
    assert IdempotencyKey.objects.filter(scope="webhook:ifood", status="done").exists()

    low_attention = Customer.objects.get(ref="CLI-001")
    assert low_attention.metadata["seed_persona"] == "low_attention"

    qa_report = build_omotenashi_qa_report()
    missing = [check.id for check in qa_report.checks if check.status == "missing"]
    assert qa_report.ready_count == len(qa_report.checks)
    assert not missing


@pytest.mark.django_db
def test_nelson_seed_rejects_default_admin_password_when_not_debug(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    with override_settings(DEBUG=False):
        with pytest.raises(CommandError):
            call_command("seed", stdout=StringIO())
