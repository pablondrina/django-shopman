"""Cupom de valor FIXO é desconto de PEDIDO, aplicado uma vez — nunca por unidade.

Regressão do QA exploratório (P1): PRIMEIRACOMPRA (R$5) descontava R$5 em CADA
unidade de CADA linha — 6 pães (R$90) recebiam R$30 de desconto. A intenção
(sinalizada pelo ``min_order_q``) sempre foi um desconto único por pedido.

Cupom/promoção PERCENTUAL continua per-line (uma % é intrinsecamente por unidade).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.shop.models import Channel, Shop
from shopman.shop.services import sessions
from shopman.storefront.models import Coupon, Promotion

pytestmark = pytest.mark.django_db


def _seed(*, promo_type: str, value: int, min_order_q: int = 0, code: str = "CUPOM") -> None:
    Shop.objects.get_or_create(name="Test Shop")
    Channel.objects.get_or_create(ref="web", defaults={"name": "Web"})
    Product.objects.get_or_create(
        sku="PAO",
        defaults={"name": "Pão", "base_price_q": 1500, "is_published": True, "is_sellable": True},
    )
    now = timezone.now()
    promo = Promotion.objects.create(
        name="Cupom Teste",
        type=promo_type,
        value=value,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        min_order_q=min_order_q,
    )
    Coupon.objects.create(code=code, promotion=promo, max_uses=0, is_active=True)


def _cart_with_coupon(*, sku: str, qty: int, unit_price_q: int, code: str):
    session = sessions.create_session("web")
    sessions.modify_session(
        session_key=session.session_key,
        channel_ref="web",
        ops=[
            {"op": "add_line", "sku": sku, "name": "Pão", "qty": qty, "unit_price_q": unit_price_q},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
            {"op": "set_data", "path": "coupon_code", "value": code},
        ],
    )
    session.refresh_from_db()
    return session


def _order_total_q(session) -> int:
    return sum(int(i.get("line_total_q", 0)) for i in (session.items or []))


def test_fixed_coupon_discounts_the_order_once_not_per_unit():
    """6 un × R$15 = R$90; cupom fixo R$5 → total R$85 (não R$60)."""
    _seed(promo_type=Promotion.FIXED, value=500, min_order_q=3000, code="PRIMEIRA")
    session = _cart_with_coupon(sku="PAO", qty=6, unit_price_q=1500, code="PRIMEIRA")

    assert _order_total_q(session) == 9000 - 500
    assert session.pricing["coupon"]["discount_q"] == 500
    assert session.pricing["discount"]["total_discount_q"] == 500


def test_fixed_coupon_capped_at_order_subtotal():
    """Cupom fixo nunca torna o total negativo — limita ao subtotal elegível."""
    _seed(promo_type=Promotion.FIXED, value=5000, code="GRANDE")
    session = _cart_with_coupon(sku="PAO", qty=1, unit_price_q=1500, code="GRANDE")

    assert _order_total_q(session) == 0
    assert session.pricing["coupon"]["discount_q"] == 1500


def test_fixed_coupon_below_min_order_does_not_apply():
    """Abaixo do pedido mínimo, o cupom fixo não desconta."""
    _seed(promo_type=Promotion.FIXED, value=500, min_order_q=3000, code="PRIMEIRA")
    session = _cart_with_coupon(sku="PAO", qty=1, unit_price_q=1500, code="PRIMEIRA")

    assert _order_total_q(session) == 1500
    assert int(session.pricing.get("coupon", {}).get("discount_q", 0)) == 0


def test_percent_coupon_stays_per_unit():
    """Cupom PERCENTUAL continua per-line: 10% em cada uma das 6 unidades."""
    _seed(promo_type=Promotion.PERCENT, value=10, code="DEZ")
    session = _cart_with_coupon(sku="PAO", qty=6, unit_price_q=1500, code="DEZ")

    # 10% de R$15 = R$1,50 por unidade × 6 = R$9 de desconto no pedido de R$90.
    assert _order_total_q(session) == 9000 - 900
    assert session.pricing["coupon"]["discount_q"] == 900


# ── Sem stacking (canoniza o pentest do QA) ──────────────────────────────


def _seed_auto_promo(*, value: int) -> None:
    """Promoção automática percentual para TODOS os SKUs (sem cupom)."""
    now = timezone.now()
    Promotion.objects.create(
        name="Promo Automática",
        type=Promotion.PERCENT,
        value=value,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )


def test_coupon_does_not_stack_with_auto_promo_best_wins():
    """Cupom % + promoção automática % na MESMA linha: só o maior aplica, nunca a
    soma. 'Maior desconto ganha' por item — sem stacking."""
    # Cupom 20% vence a promo automática de 10% na mesma linha.
    _seed(promo_type=Promotion.PERCENT, value=20, code="VINTE")
    _seed_auto_promo(value=10)
    session = _cart_with_coupon(sku="PAO", qty=2, unit_price_q=1500, code="VINTE")

    # 20% de R$30 = R$6 (não 30% = R$9). Um único desconto por linha.
    assert _order_total_q(session) == 3000 - 600
    # Exatamente um desconto registrado para a linha (o cupom venceu; sem soma).
    pao_discounts = [d for d in session.pricing["discount"]["items"] if d["sku"] == "PAO"]
    assert len(pao_discounts) == 1
    assert pao_discounts[0]["type"] == "coupon"


def test_only_one_coupon_code_is_ever_active():
    """Aplicar um segundo cupom substitui o primeiro — cupons não empilham."""
    _seed(promo_type=Promotion.PERCENT, value=10, code="DEZ")
    _seed(promo_type=Promotion.PERCENT, value=20, code="VINTE")

    session = sessions.create_session("web")
    sessions.modify_session(
        session_key=session.session_key,
        channel_ref="web",
        ops=[
            {"op": "add_line", "sku": "PAO", "name": "Pão", "qty": 2, "unit_price_q": 1500},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        ],
    )

    def _apply(code):
        sessions.modify_session(
            session_key=session.session_key,
            channel_ref="web",
            ops=[{"op": "set_data", "path": "coupon_code", "value": code}],
        )
        session.refresh_from_db()

    _apply("DEZ")
    _apply("VINTE")  # substitui o cupom anterior, não soma

    assert session.data["coupon_code"] == "VINTE"
    # Só o cupom VINTE (20%) conta: R$30 - R$6 = R$24.
    assert _order_total_q(session) == 3000 - 600
    assert session.pricing["coupon"]["code"] == "VINTE"
    assert session.pricing["coupon"]["discount_q"] == 600
