"""Persona 2 — o cliente fiel (membro de um grupo/segmento de loyalty).

Cobre o furo em que uma promoção restrita a um grupo/segmento
(``Promotion.customer_segments=["fieis"]``) era ACEITA para um membro elegível
mas descontava ZERO na loja.

Causa raiz: duas fontes distintas do grupo do cliente. O gate de elegibilidade
lia ``customer.group.ref`` do request e passava; já o ``DiscountModifier`` (e o
``StorefrontPricingBackend`` do cardápio) liam o grupo/segmento do CONTEXTO de
pricing, que a loja nunca populava — só o PDV escrevia ``customer.group`` na
sessão.

Correção (ver ``PERSONA_FINDINGS.md``):
- a loja vincula o cliente (ref + grupo) à sessão do carrinho a cada escrita;
- o ``DiscountModifier`` resolve grupo/segmento da própria sessão, a cada reprice;
- cardápio/PDP passam ``customer_group``/``customer_segment`` no contexto de preço.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.guestman.models import Customer, CustomerGroup
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.shop.models import Channel, Shop
from shopman.shop.services import cart as cart_mutations
from shopman.shop.services import sessions
from shopman.storefront.cart import CartService
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.models import Coupon, Promotion

pytestmark = pytest.mark.django_db

SKU = "PAO-FIEL"
PRICE_Q = 750  # R$ 7,50 → 10% = R$ 0,75


class _CustomerInfo:
    """Minimal stand-in for what AuthCustomerMiddleware sets on request.customer."""

    def __init__(self, uuid):
        self.uuid = uuid


class _FakeRequest:
    def __init__(self, *, session_key: str | None = None, customer_uuid=None):
        self.session = {"cart_session_key": session_key} if session_key else {}
        self.customer = _CustomerInfo(customer_uuid) if customer_uuid else None


def _seed_stock(sku: str) -> None:
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stock.receive(
        quantity=Decimal("1000"),
        sku=sku,
        position=position,
        target_date=date.today(),
        reason="e2e seed",
    )


def _seed_listing(channel: Channel, product: Product, price_q: int) -> None:
    listing, _ = Listing.objects.get_or_create(
        ref=channel.ref,
        defaults={"name": channel.ref, "is_active": True, "priority": 10},
    )
    ListingItem.objects.get_or_create(
        listing=listing,
        product=product,
        defaults={"price_q": price_q, "is_published": True, "is_sellable": True},
    )


@pytest.fixture
def loyal_setup(db):
    Shop.objects.create(name="Test Shop")
    channel = Channel.objects.create(ref=STOREFRONT_CHANNEL_REF, name="Web")
    product = Product.objects.create(
        sku=SKU, name="Pão", base_price_q=PRICE_Q, is_published=True, is_sellable=True
    )
    _seed_stock(SKU)
    _seed_listing(channel, product, PRICE_Q)

    group = CustomerGroup.objects.create(ref="fieis", name="Fiéis")
    member = Customer.objects.create(
        ref="CUST-FIEL01", first_name="Ana", last_name="Fiel", group=group
    )
    return member


@pytest.fixture
def segmented_coupon(loyal_setup):
    now = timezone.now()
    promo = Promotion.objects.create(
        name="Fiéis 10%",
        type=Promotion.PERCENT,
        value=10,
        customer_segments=["fieis"],
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    Coupon.objects.create(code="FIEL10", promotion=promo)
    return loyal_setup


@pytest.fixture
def segmented_auto_promo(loyal_setup):
    """Promoção AUTOMÁTICA (sem cupom) restrita ao grupo 'fieis'."""
    now = timezone.now()
    Promotion.objects.create(
        name="Clube dos Fiéis",
        type=Promotion.PERCENT,
        value=10,
        customer_segments=["fieis"],
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    return loyal_setup


def _cart_session_with_item() -> str:
    session = sessions.create_session(STOREFRONT_CHANNEL_REF)
    sessions.modify_session(
        session_key=session.session_key,
        channel_ref=STOREFRONT_CHANNEL_REF,
        ops=[{"op": "add_line", "sku": SKU, "name": "Pão", "qty": 1, "unit_price_q": PRICE_Q}],
    )
    return session.session_key


def _open(session_key: str):
    return cart_mutations.get_open_session(
        session_key=session_key, channel_ref=STOREFRONT_CHANNEL_REF
    )


def _coupon_discount_q(session_key: str) -> int:
    return int((_open(session_key).pricing or {}).get("coupon", {}).get("discount_q", 0))


def _line_unit_price_q(session_key: str) -> int:
    items = _open(session_key).items or []
    return int(items[0].get("unit_price_q", 0)) if items else 0


# ── Cupom segmentado ────────────────────────────────────────────────


def test_group_coupon_should_discount_for_member(segmented_coupon):
    """Membro 'fieis' aplica FIEL10 (10% de R$7,50) → desconta R$0,75."""
    member = segmented_coupon
    session_key = _cart_session_with_item()
    request = _FakeRequest(session_key=session_key, customer_uuid=member.uuid)

    result = CartService.apply_coupon(request, "FIEL10")

    assert result["ok"] is True
    assert _coupon_discount_q(session_key) == 75


def test_group_coupon_discount_survives_reprice(segmented_coupon):
    """O desconto do cupom segmentado sobrevive a um reprice posterior.

    Antes o grupo vinha só do ctx efêmero do apply; qualquer reprice seguinte
    reavaliava o cupom com contexto vazio e zerava o desconto.
    """
    member = segmented_coupon
    session_key = _cart_session_with_item()
    request = _FakeRequest(session_key=session_key, customer_uuid=member.uuid)

    CartService.apply_coupon(request, "FIEL10")
    assert _coupon_discount_q(session_key) == 75

    cart_mutations.reprice(session_key=session_key, channel_ref=STOREFRONT_CHANNEL_REF)
    assert _coupon_discount_q(session_key) == 75


def test_group_coupon_rejected_for_non_member(segmented_coupon):
    """Cliente fora do grupo é recusado no gate (não grava cupom mudo)."""
    other = CustomerGroup.objects.create(ref="novatos", name="Novatos")
    outsider = Customer.objects.create(
        ref="CUST-NOV01", first_name="Beto", last_name="Novato", group=other
    )
    session_key = _cart_session_with_item()
    request = _FakeRequest(session_key=session_key, customer_uuid=outsider.uuid)

    result = CartService.apply_coupon(request, "FIEL10")

    assert result == {"ok": False, "error": "coupon_not_eligible"}
    assert _coupon_discount_q(session_key) == 0


# ── Promoção automática segmentada (sem cupom) ──────────────────────


def test_group_auto_promo_discounts_cart_for_member(segmented_auto_promo):
    """Membro adiciona item ao carrinho → a promoção automática do grupo desconta.

    Exercita o vínculo do cliente à sessão feito pelo ``CartService.add_item`` e a
    resolução de grupo/segmento pelo ``DiscountModifier`` a cada reprice.
    """
    member = segmented_auto_promo
    request = _FakeRequest(customer_uuid=member.uuid)

    CartService.add_item(request, SKU, qty=1, unit_price_q=PRICE_Q, name="Pão")
    session_key = request.session["cart_session_key"]

    assert _line_unit_price_q(session_key) == 675  # 750 − 10%
    discount = (_open(session_key).pricing or {}).get("discount", {})
    assert int(discount.get("total_discount_q", 0)) == 75


def test_group_auto_promo_not_applied_for_anonymous(segmented_auto_promo):
    """Visitante anônimo não recebe a promoção do grupo (paga o preço cheio)."""
    request = _FakeRequest()  # sem cliente

    CartService.add_item(request, SKU, qty=1, unit_price_q=PRICE_Q, name="Pão")
    session_key = request.session["cart_session_key"]

    assert _line_unit_price_q(session_key) == 750


def test_add_item_links_customer_to_session(segmented_auto_promo):
    """A identidade do cliente (ref + grupo) fica persistida na sessão do carrinho."""
    member = segmented_auto_promo
    request = _FakeRequest(customer_uuid=member.uuid)

    CartService.add_item(request, SKU, qty=1, unit_price_q=PRICE_Q, name="Pão")
    session_key = request.session["cart_session_key"]

    customer = (_open(session_key).data or {}).get("customer") or {}
    assert customer.get("ref") == "CUST-FIEL01"
    assert customer.get("group") == "fieis"


# ── Vitrine (cardápio) ──────────────────────────────────────────────


def test_menu_shows_group_promo_price_for_member(segmented_auto_promo):
    """No cardápio, o membro vê o preço promocional do grupo; o anônimo não."""
    from shopman.storefront.presentation.catalog import build_catalog_items_for_skus

    member = segmented_auto_promo

    member_items = build_catalog_items_for_skus(
        [SKU],
        channel_ref=STOREFRONT_CHANNEL_REF,
        request=_FakeRequest(customer_uuid=member.uuid),
    )
    anon_items = build_catalog_items_for_skus(
        [SKU], channel_ref=STOREFRONT_CHANNEL_REF, request=_FakeRequest()
    )

    assert member_items[0].base_price_q == 675  # desconto do grupo aplicado
    assert member_items[0].has_promotion is True
    assert anon_items[0].base_price_q == 750     # preço cheio
    assert anon_items[0].has_promotion is False
