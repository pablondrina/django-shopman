"""Nelson seed coverage for operator production surfaces."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
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

    from shopman.fiscalman.classification import from_metadata, resolve_fiscal_item

    assert not Product.objects.filter(sku__startswith="DEMO-").exists()
    for sku in ("BAGUETE", "ESPRESSO", "COMBO-PETIT-DEJ"):
        metadata = Product.objects.get(sku=sku).metadata
        fiscal = metadata["fiscal"]
        assert fiscal["profile"] == "own_production"
        assert fiscal["ncm"]
        # CFOP/CSOSN são resolvidos do perfil fiscal na emissão (NFC-e intraestadual).
        resolved = resolve_fiscal_item(from_metadata(metadata))
        assert resolved["cfop"] == "5102"
        assert resolved["icms_situacao_tributaria"] == "102"
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

    # Estoque de abertura de insumo no depósito (físico, p/ consumir/checar).
    from shopman.stockman import stock as stock_service
    from shopman.stockman.models import Quant

    deposito = Position.objects.get(ref="deposito")
    assert Quant.objects.filter(sku="FARINHA-T65", position=deposito).exists()
    assert stock_service.available("FARINHA-T65", position=deposito) == Decimal("500")

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
    # O edge "ifood-stale-confirmation" (pedido NEW parado) foi removido de propósito:
    # a coluna Entrada nasce vazia para testar a chegada de pedidos novos ao vivo.
    assert edge_keys >= {
        "security:payment-pending-near-expiry",
        "security:payment-expired-low-attention",
        "security:payment-after-cancel",
    }
    assert "security:ifood-stale-confirmation" not in edge_keys

    edge_order_refs = {order.ref for order in edge_orders}
    assert PaymentIntent.objects.filter(order_ref__in=edge_order_refs, status=PaymentIntent.Status.PENDING).count() >= 2
    assert PaymentIntent.objects.filter(order_ref__in=edge_order_refs, status=PaymentIntent.Status.CAPTURED).exists()
    for intent in PaymentIntent.objects.filter(status=PaymentIntent.Status.CAPTURED):
        order = Order.objects.get(ref=intent.order_ref)
        assert ((order.data or {}).get("payment") or {}).get("intent_ref") == intent.ref
    assert OperatorAlert.objects.filter(type="payment_after_cancel", severity="critical", acknowledged=False).exists()
    # (alerta stale_new_order + webhook:ifood saíram junto com o edge iFood parado — Entrada vazia)
    assert IdempotencyKey.objects.filter(scope="webhook:efi-pix", status="done").exists()

    low_attention = Customer.objects.get(ref="CLI-001")
    assert low_attention.metadata["seed_persona"] == "low_attention"

    qa_report = build_omotenashi_qa_report()
    missing = [check.id for check in qa_report.checks if check.status == "missing"]
    assert qa_report.ready_count == len(qa_report.checks)
    assert not missing


@pytest.mark.django_db
def test_nelson_seed_provisions_operators_with_pins(monkeypatch):
    """Backstage exige operador ativo: staff + PinCredential + permissão da superfície.

    Com ``SHOPMAN_REQUIRE_ACTIVE_OPERATOR`` ligado (staging), nenhuma tela destrava
    sem um operador provisionado. O seed provisiona operadores com PIN 1234 para
    POS/KDS/produção — senão o backstage nasce inacessível após um ``--flush``.
    """
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")
    call_command("seed", "--flush", stdout=StringIO())

    from django.contrib.auth.models import User

    from shopman.backstage.services.operator import eligible_operators, verify_operator_pin

    for perm in (
        "backstage.operate_pos",
        "backstage.operate_kds",
        "backstage.operate_production",
    ):
        operators = list(eligible_operators(perm=perm))
        assert operators, f"nenhum operador elegível para {perm}"
        assert any(verify_operator_pin(u, "1234", required_perm=perm) for u in operators), (
            f"PIN 1234 não destrava {perm}"
        )

    # O superuser 'admin' também opera — PIN destrava qualquer superfície.
    admin = User.objects.get(username="admin")
    assert verify_operator_pin(admin, "1234", required_perm="backstage.operate_pos")
    assert verify_operator_pin(admin, "1234", required_perm="backstage.operate_kds")

    # PIN errado nunca destrava.
    assert not verify_operator_pin(admin, "0000", required_perm="backstage.operate_pos")


@pytest.mark.django_db
def test_nelson_seed_rejects_default_admin_password_when_not_debug(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    with override_settings(DEBUG=False):
        with pytest.raises(CommandError):
            call_command("seed", stdout=StringIO())


@pytest.mark.django_db
def test_nelson_seed_qa_profile_builds_named_scenarios(monkeypatch):
    """Perfil qa (SEED-DATA-QUALITY-PLAN Fase 2): cada cenário nomeado existe com
    ref previsível QA-*, estado estável e datas relativas a localdate().

    Ver docs/reference/qa-seed-scenarios.md — este teste é a âncora de contrato.
    """
    from datetime import timedelta

    from django.utils import timezone
    from shopman.craftsman.models import WorkOrder
    from shopman.payman.models import PaymentIntent, PaymentTransaction

    from shopman.backstage.models import CashShift, KDSTicket, POSTab

    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")
    call_command("seed", "--flush", "--profile", "qa", stdout=StringIO())

    today = timezone.localdate()
    tomorrow = (today + timedelta(days=1)).isoformat()

    # Todas as refs QA-* nomeadas existem.
    named = {
        "QA-PREORDER-01", "QA-PREORDER-02",
        "QA-PAID-READY-01", "QA-PAID-READY-02", "QA-RETURNED-01",
        "QA-PIX-PENDING-01", "QA-IFOOD-01", "QA-NOTES-01", "QA-NAMED-ITEMS-01",
    }
    existing = set(Order.objects.filter(ref__startswith="QA-").values_list("ref", flat=True))
    assert named <= existing, f"faltando cenários qa: {named - existing}"

    # Preorder: novo + confirmado, encomenda para amanhã.
    p1 = Order.objects.get(ref="QA-PREORDER-01")
    assert p1.status == Order.Status.NEW
    assert p1.data["is_preorder"] is True
    assert p1.data["delivery_date"] == tomorrow
    assert Order.objects.get(ref="QA-PREORDER-02").status == Order.Status.CONFIRMED

    # Pago em ready/dispatched com intent capturado.
    ready = Order.objects.get(ref="QA-PAID-READY-01")
    assert ready.status == Order.Status.READY
    assert PaymentIntent.objects.get(order_ref="QA-PAID-READY-01").status == PaymentIntent.Status.CAPTURED
    assert Order.objects.get(ref="QA-PAID-READY-02").status == Order.Status.DISPATCHED

    # Devolvido + estorno (intent refunded com transação de refund).
    ret = Order.objects.get(ref="QA-RETURNED-01")
    assert ret.status == Order.Status.RETURNED
    ret_intent = PaymentIntent.objects.get(order_ref="QA-RETURNED-01")
    assert ret_intent.status == PaymentIntent.Status.REFUNDED
    assert PaymentTransaction.objects.filter(
        intent=ret_intent, type=PaymentTransaction.Type.REFUND
    ).exists()

    # PIX pendente (confirmado, não pago).
    assert Order.objects.get(ref="QA-PIX-PENDING-01").status == Order.Status.CONFIRMED
    assert PaymentIntent.objects.get(order_ref="QA-PIX-PENDING-01").status == PaymentIntent.Status.PENDING

    # iFood (canal marketplace + external_ref).
    ifood = Order.objects.get(ref="QA-IFOOD-01")
    assert ifood.channel_ref == "ifood"
    assert ifood.external_ref == "IFOOD-QA-0001"

    # order_notes do cliente propagado.
    assert Order.objects.get(ref="QA-NOTES-01").data["order_notes"]

    # OrderItem.name preenchido (regressão SKU cru).
    named_items = Order.objects.get(ref="QA-NAMED-ITEMS-01")
    assert all(item.name for item in named_items.items.all())

    # Produção: WO em cada estado hoje + fornada presa de ontem (started).
    today_states = set(
        WorkOrder.objects.filter(
            source_ref__startswith="seed:production:today:", target_date=today
        ).values_list("status", flat=True)
    )
    assert {"planned", "started", "finished"} <= today_states
    stuck = WorkOrder.objects.filter(source_ref__startswith="seed:production:qa-stuck:")
    assert stuck.count() == 1
    stuck_wo = stuck.get()
    assert stuck_wo.status == WorkOrder.Status.STARTED
    assert stuck_wo.target_date == today - timedelta(days=1)

    # Caixa: 1 aberto + 1 fechado com divergência conhecida.
    assert CashShift.objects.filter(status="open").exists()
    closed = CashShift.objects.filter(status="closed")
    assert closed.exists()
    assert closed.first().difference_q != 0

    # Comandas: aberta com itens (00001007) + uma com item disparado à cozinha.
    assert POSTab.objects.filter(ref="00002001").exists()
    assert KDSTicket.objects.filter(session_key="seed-qa-postab-00002001").exists()
    assert Session.objects.filter(
        state="open", handle_type="pos_tab", handle_ref="00001007"
    ).exists()
