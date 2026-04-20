"""
Substitute product scoring — find replacement SKUs for an unavailable one.

The name is deliberate: this is a substitution system (produto X faltou,
aqui está o mais próximo), not a recommendation or cross-sell system.
"""

from decimal import Decimal

from shopman.offerman.models import Product
from shopman.offerman.service import CatalogService


def _get_primary_collection(product: Product):
    """Get the primary collection for a product."""
    primary_item = product.collection_items.filter(is_primary=True).first()
    return primary_item.collection if primary_item else None


def _score_candidates(
    candidates: list[Product],
    product: Product,
    product_keywords: list[str],
    primary_collection,
) -> list[Product]:
    """
    Score and sort candidate products.

    Scoring (keywords domina; coleção reforça; preço finaliza):
        - Keywords em comum:            3 pontos cada (até ~12 com 4 comuns)
        - Mesma coleção que referência: 2 pontos
        - Preço ±30% da referência:     1 ponto

    Sem similaridade de nome: em catálogos com nomes muito prefixados
    ("Pão X", "Pão Y"), ``SequenceMatcher`` infla score de produtos não
    relacionados e penaliza substitutos legítimos com nomes distintos.
    Keywords + coleção são o sinal correto.
    """
    price_low = int(product.base_price_q * Decimal("0.7"))
    price_high = int(product.base_price_q * Decimal("1.3"))

    collection_product_ids = set()
    if primary_collection:
        collection_product_ids = set(
            primary_collection.items.values_list("product_id", flat=True)
        )

    scored = []
    for candidate in candidates:
        score = 0

        candidate_keywords = set(candidate.keywords.names())
        common = len(set(product_keywords) & candidate_keywords)
        score += common * 3

        if primary_collection and candidate.pk in collection_product_ids:
            score += 2

        if price_low <= candidate.base_price_q <= price_high:
            score += 1

        scored.append((score, candidate))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [candidate for _, candidate in scored]


def find_substitutes(
    sku: str,
    limit: int = 5,
    same_collection: bool = True,
) -> list[Product]:
    """Find substitute products for a given SKU."""
    product = CatalogService.get(sku)
    if not product:
        return []

    product_keywords = list(product.keywords.names())
    if not product_keywords:
        return []

    qs = (
        Product.objects.filter(
            is_published=True,
            is_sellable=True,
            keywords__name__in=product_keywords,
        )
        .exclude(sku=sku)
        .distinct()
    )

    primary_collection = _get_primary_collection(product)

    if same_collection and primary_collection:
        qs = qs.filter(collection_items__collection=primary_collection)

    candidates = list(qs[: limit * 3])
    scored = _score_candidates(candidates, product, product_keywords, primary_collection)
    return scored[:limit]


