"""Costuras estoque↔pedido do audit pré-go-live (fail-open → fail-loud).

Regressões cobertas:
- hold de sessão EXPIRADO era adotado no commit → pedido pago sem baixa e a
  unidade vendida duas vezes (``find_by_reference`` não filtrava ``expires_at``);
- hold adotado continuava com TTL de carrinho → expirava durante um PIX lento;
- adoção com overshoot gravava a qty do HOLD (não a do pedido) → fulfill
  baixava mais estoque que a venda;
- falha de fulfill era só ``logger.error`` — nenhum OperatorAlert;
- cancelamento pós-fulfill não devolvia estoque.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.stockman import HoldStatus, PositionKind
from shopman.stockman.models import Hold, Move, Position, Quant

from shopman.backstage.models import OperatorAlert
from shopman.shop.adapters import get_adapter
from shopman.shop.models import Channel
from shopman.shop.services import stock as stock_service

pytestmark = pytest.mark.django_db

SKU = "AUDIT-STK-1"
SESSION_KEY = "sess-audit-1"
ORDER_REF = "ORD-AUDIT-1"


def _setup_world(stock_qty: int = 100) -> Product:
    Channel.objects.create(ref="web", name="Web", is_active=True)
    product = Product.objects.create(
        sku=SKU, name="Produto", base_price_q=1000, is_published=True, is_sellable=True
    )
    pos, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    Quant.objects.create(sku=SKU, position=pos, _quantity=Decimal(str(stock_qty)))
    return product


def _make_session_hold(qty: int, *, expired: bool = False) -> str:
    adapter = get_adapter("stock")
    result = adapter.create_hold(sku=SKU, qty=Decimal(str(qty)), reference=SESSION_KEY)
    assert result["success"], result
    if expired:
        Hold.objects.filter(pk=int(result["hold_id"].split(":")[1])).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
    return result["hold_id"]


def _make_order(items_qty: int) -> SimpleNamespace:
    return SimpleNamespace(
        ref=ORDER_REF,
        session_key=SESSION_KEY,
        snapshot={"items": [{"sku": SKU, "qty": items_qty}]},
        data={},
        save=lambda update_fields=None: None,
    )


def _sell_moves_total() -> Decimal:
    return -sum(
        (m.delta for m in Move.objects.filter(kind=Move.Kind.SELL)), Decimal("0")
    )


def test_expired_session_hold_is_not_adopted(_=None):
    _setup_world()
    expired_id = _make_session_hold(2, expired=True)

    order = _make_order(2)
    stock_service.hold(order)

    expired_hold = Hold.objects.get(pk=int(expired_id.split(":")[1]))
    # O hold expirado não protege nada: não pode ser adotado.
    assert expired_hold.metadata["reference"] != f"order:{ORDER_REF}"
    # Um hold fresco cobriu o pedido.
    adopted = [e for e in order.data["hold_ids"] if e.get("hold_id")]
    assert len(adopted) == 1
    assert adopted[0]["hold_id"] != expired_id

    stock_service.fulfill(order)
    assert _sell_moves_total() == Decimal("2")


def test_adopted_hold_gets_long_backstop_ttl(_=None):
    _setup_world()
    hold_id = _make_session_hold(2)

    order = _make_order(2)
    stock_service.hold(order)

    adopted = Hold.objects.get(pk=int(hold_id.split(":")[1]))
    # Dono agora é o pedido: o TTL vira um backstop LONGO (não None) — o PIX
    # lento não expira a reserva, mas um pedido travado sem fulfill/release
    # ainda é reclamado eventualmente (não fica órfão para sempre).
    assert adopted.expires_at is not None
    assert adopted.expires_at > timezone.now() + timedelta(hours=24)


def test_overshoot_adoption_consumes_order_qty_not_hold_qty(_=None):
    _setup_world()
    _make_session_hold(2)
    _make_session_hold(3)  # soma 5 para um pedido de 4

    order = _make_order(4)
    stock_service.hold(order)

    assert sum(e["qty"] for e in order.data["hold_ids"]) == 4

    stock_service.fulfill(order)
    # Baixa exatamente a venda (4), nunca a reserva (5).
    assert _sell_moves_total() == Decimal("4")


def test_fulfill_failure_raises_operator_alert(_=None):
    _setup_world()
    hold_id = _make_session_hold(2)
    order = _make_order(2)
    stock_service.hold(order)

    # Simula corrupção: hold liberado por fora antes do fulfill.
    Hold.objects.filter(pk=int(hold_id.split(":")[1])).update(status=HoldStatus.RELEASED)

    stock_service.fulfill(order)

    alert = OperatorAlert.objects.filter(type="stock_fulfill_failed").first()
    assert alert is not None
    assert ORDER_REF in alert.message


def test_cancel_after_fulfill_returns_stock_to_ledger(_=None):
    _setup_world(stock_qty=10)
    _make_session_hold(2)
    order = _make_order(2)
    stock_service.hold(order)
    stock_service.fulfill(order)
    assert _sell_moves_total() == Decimal("2")

    # Cancelamento tardio (janela de arrependimento do PDV): devolve ao ledger.
    stock_service.release(order)          # no-op em hold FULFILLED
    stock_service.revert_fulfilled(order)
    # IDEMPOTENTE: um on_cancelled re-disparado NÃO credita o estoque de novo.
    stock_service.revert_fulfilled(order)

    returns = Move.objects.filter(kind=Move.Kind.RETURN)
    assert sum((m.delta for m in returns), Decimal("0")) == Decimal("2")
    quant = Quant.objects.get(sku=SKU, position__ref="vitrine")
    assert quant.quantity == Decimal("10")
