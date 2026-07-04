"""cart_context delega o preço ao CatalogService (autoridade do Offerman).

Regressão do bug: `_price_q` reimplementava pricing com `order_by("-min_qty").first()`
sem filtro de qty → adicionar 1 unidade cobrava o tier de ATACADO (min_qty maior e
mais barato), e ignorava is_sellable e a janela de validade do listing.
"""

from decimal import Decimal

import pytest
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.shop.projections import cart_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def produto_com_tiers():
    p = Product.objects.create(
        sku="PAO-TIER",
        name="Pão com atacado",
        base_price_q=1000,
        unit="un",
        is_published=True,
        is_sellable=True,
    )
    listing = Listing.objects.create(ref="web", name="Web", is_active=True)
    # Varejo: 1+ un a R$10,00
    ListingItem.objects.create(
        listing=listing, product=p, price_q=1000, min_qty=Decimal("1"),
        is_published=True, is_sellable=True,
    )
    # Atacado: 10+ un a R$7,00 (mais barato)
    ListingItem.objects.create(
        listing=listing, product=p, price_q=700, min_qty=Decimal("10"),
        is_published=True, is_sellable=True,
    )
    return p


def test_add_uma_unidade_cobra_varejo_nao_atacado(produto_com_tiers):
    ctx = cart_context.product_context("PAO-TIER", channel_ref="web", qty=1)
    assert ctx is not None
    assert ctx.unit_price_q == 1000, "qty=1 deve cair no tier de varejo, não no atacado"


def test_add_dez_unidades_cobra_atacado(produto_com_tiers):
    ctx = cart_context.product_context("PAO-TIER", channel_ref="web", qty=10)
    assert ctx.unit_price_q == 700, "qty=10 deve cair no tier de atacado"


def test_tier_nao_vendavel_e_ignorado(produto_com_tiers):
    # Um tier de atacado NÃO-vendável não pode ser cobrado.
    ListingItem.objects.filter(product=produto_com_tiers, min_qty=Decimal("10")).update(
        is_sellable=False
    )
    ctx = cart_context.product_context("PAO-TIER", channel_ref="web", qty=10)
    assert ctx.unit_price_q == 1000, "tier não-vendável ignorado → cai no varejo"


def test_sem_listing_cai_para_base_price(produto_com_tiers):
    ctx = cart_context.product_context("PAO-TIER", channel_ref="inexistente", qty=1)
    assert ctx.unit_price_q == 1000  # base_price_q
