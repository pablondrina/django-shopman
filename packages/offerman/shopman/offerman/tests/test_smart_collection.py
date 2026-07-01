"""
Smart collections — membership computada por regra (offerman.smart_collection).

Coleção manual (rule vazia) = CollectionItems explícitos (comportamento atual).
Coleção smart (rule preenchida) = resolver sobre atributos do produto.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from shopman.offerman.models import Collection, CollectionItem, Product
from shopman.offerman.smart_collection import resolve_products, validate_rule


@pytest.fixture
def catalog(db):
    """Três produtos com tags/preços distintos para exercitar as condições."""
    vegan_bread = Product.objects.create(
        sku="PAO-VEGANO", name="Pão Vegano", unit="un", base_price_q=1500, is_published=True, is_sellable=True
    )
    vegan_bread.keywords.add("vegano", "pao")

    croissant = Product.objects.create(
        sku="CROISSANT", name="Croissant", unit="un", base_price_q=800, is_published=True, is_sellable=False
    )
    croissant.keywords.add("folhado")

    cake = Product.objects.create(
        sku="BOLO", name="Bolo de Cenoura", unit="un", base_price_q=4500, is_published=False, is_sellable=True
    )
    cake.keywords.add("vegano", "doce")

    return {"vegan_bread": vegan_bread, "croissant": croissant, "cake": cake}


def _skus(qs):
    return sorted(qs.values_list("sku", flat=True))


# ── resolver: campos e operadores ──────────────────────────────────────────────


def test_keyword_eq_matches_tagged_products(catalog):
    rule = {"match": "all", "conditions": [{"field": "keyword", "op": "eq", "value": "vegano"}]}
    assert _skus(resolve_products(rule)) == ["BOLO", "PAO-VEGANO"]


def test_match_all_is_and(catalog):
    rule = {
        "match": "all",
        "conditions": [
            {"field": "keyword", "op": "eq", "value": "vegano"},
            {"field": "base_price_q", "op": "lte", "value": 2000},
        ],
    }
    # vegano AND <= R$20 → só o pão (bolo custa R$45)
    assert _skus(resolve_products(rule)) == ["PAO-VEGANO"]


def test_match_any_is_or(catalog):
    rule = {
        "match": "any",
        "conditions": [
            {"field": "keyword", "op": "eq", "value": "folhado"},
            {"field": "base_price_q", "op": "gte", "value": 4000},
        ],
    }
    # folhado OR >= R$40 → croissant + bolo
    assert _skus(resolve_products(rule)) == ["BOLO", "CROISSANT"]


def test_ne_excludes(catalog):
    rule = {"match": "all", "conditions": [{"field": "is_sellable", "op": "ne", "value": True}]}
    assert _skus(resolve_products(rule)) == ["CROISSANT"]


def test_in_list(catalog):
    rule = {"match": "all", "conditions": [{"field": "sku", "op": "in", "value": ["BOLO", "CROISSANT"]}]}
    assert _skus(resolve_products(rule)) == ["BOLO", "CROISSANT"]


def test_contains_is_case_insensitive(catalog):
    rule = {"match": "all", "conditions": [{"field": "name", "op": "contains", "value": "cenoura"}]}
    assert _skus(resolve_products(rule)) == ["BOLO"]


def test_is_published_bool(catalog):
    rule = {"match": "all", "conditions": [{"field": "is_published", "op": "eq", "value": True}]}
    assert _skus(resolve_products(rule)) == ["CROISSANT", "PAO-VEGANO"]


def test_keyword_join_does_not_duplicate(catalog):
    """Produto com 2 tags que casam a regra aparece uma vez (distinct)."""
    rule = {"match": "any", "conditions": [
        {"field": "keyword", "op": "eq", "value": "vegano"},
        {"field": "keyword", "op": "eq", "value": "pao"},
    ]}
    result = list(resolve_products(rule).values_list("sku", flat=True))
    assert result.count("PAO-VEGANO") == 1


def test_collection_membership_field(db, catalog):
    """field=collection casa produtos com membership EXPLÍCITA em outra coleção."""
    manual = Collection.objects.create(ref="promo", name="Promoções")
    CollectionItem.objects.create(collection=manual, product=catalog["croissant"])
    rule = {"match": "all", "conditions": [{"field": "collection", "op": "eq", "value": "promo"}]}
    assert _skus(resolve_products(rule)) == ["CROISSANT"]


# ── validação de regra ─────────────────────────────────────────────────────────


def test_validate_rejects_unknown_field():
    with pytest.raises(ValidationError, match="field"):
        validate_rule({"conditions": [{"field": "color", "op": "eq", "value": "x"}]})


def test_validate_rejects_unknown_op():
    with pytest.raises(ValidationError, match="op"):
        validate_rule({"conditions": [{"field": "sku", "op": "like", "value": "x"}]})


def test_validate_rejects_bad_match():
    with pytest.raises(ValidationError, match="match"):
        validate_rule({"match": "some", "conditions": [{"field": "sku", "op": "eq", "value": "x"}]})


def test_validate_rejects_empty_conditions():
    with pytest.raises(ValidationError, match="conditions"):
        validate_rule({"match": "all", "conditions": []})


def test_validate_in_requires_list():
    with pytest.raises(ValidationError, match="lista"):
        validate_rule({"conditions": [{"field": "sku", "op": "in", "value": "not-a-list"}]})


# ── Collection model: is_smart + product_queryset ──────────────────────────────


def test_manual_collection_uses_explicit_items(db, catalog):
    coll = Collection.objects.create(ref="manual", name="Manual")
    CollectionItem.objects.create(collection=coll, product=catalog["cake"])
    assert coll.is_smart is False
    assert _skus(coll.product_queryset()) == ["BOLO"]


def test_smart_collection_uses_rule(db, catalog):
    coll = Collection.objects.create(
        ref="veganos",
        name="Veganos",
        rule={"match": "all", "conditions": [{"field": "keyword", "op": "eq", "value": "vegano"}]},
    )
    assert coll.is_smart is True
    assert _skus(coll.product_queryset()) == ["BOLO", "PAO-VEGANO"]


def test_smart_collection_ignores_explicit_items(db, catalog):
    """Coleção smart não usa CollectionItems — só a regra."""
    coll = Collection.objects.create(
        ref="doces",
        name="Doces",
        rule={"match": "all", "conditions": [{"field": "keyword", "op": "eq", "value": "doce"}]},
    )
    # membership explícita conflitante é ignorada
    CollectionItem.objects.create(collection=coll, product=catalog["croissant"])
    assert _skus(coll.product_queryset()) == ["BOLO"]


def test_clean_rejects_invalid_rule(db):
    coll = Collection(ref="bad", name="Bad", rule={"conditions": [{"field": "nope", "op": "eq", "value": 1}]})
    with pytest.raises(ValidationError):
        coll.full_clean()
