"""
Smart collection resolver — computa a membership de uma coleção por REGRA.

Estilo Shopify (verificado na pesquisa): condições sobre atributos do produto com
lógica ``all`` (AND) ou ``any`` (OR), auto-populadas, sem atribuição manual. Serve
de alça viva para bulk ops e saved views: "todos os pães", "em promoção", etc.

Schema da regra (``Collection.rule``):

    {
        "match": "all" | "any",              # AND | OR (default: "all")
        "conditions": [
            {"field": <str>, "op": <str>, "value": <any>},
            ...
        ],
    }

Campos suportados (``field``) → mapeamento no Product:

    keyword            keywords__name          (taggit)
    sku                sku
    name               name
    unit               unit
    base_price_q       base_price_q            (centavos)
    is_published       is_published
    is_sellable        is_sellable
    collection         collection_items__collection__ref
                       (membership EXPLÍCITA em outra coleção; não segue smart)

Operadores (``op``):

    eq, ne             igualdade / diferença
    lt, lte, gt, gte   comparação (numérico)
    in                 pertence a lista (value deve ser lista)
    contains           substring case-insensitive (texto)
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Q

# field lógico → lookup base no Product
_FIELD_LOOKUPS = {
    "keyword": "keywords__name",
    "sku": "sku",
    "name": "name",
    "unit": "unit",
    "base_price_q": "base_price_q",
    "is_published": "is_published",
    "is_sellable": "is_sellable",
    "collection": "collection_items__collection__ref",
}

_OPS = {"eq", "ne", "lt", "lte", "gt", "gte", "in", "contains"}

# Joins que podem multiplicar linhas → exigem .distinct()
_MULTI_JOIN_FIELDS = {"keyword", "collection"}


def validate_rule(rule: dict) -> None:
    """Valida a estrutura da regra. Levanta ``ValidationError`` em regra inválida."""
    if not isinstance(rule, dict):
        raise ValidationError("rule deve ser um objeto")

    match = rule.get("match", "all")
    if match not in ("all", "any"):
        raise ValidationError(f"rule.match inválido: {match!r} (use 'all' ou 'any')")

    conditions = rule.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise ValidationError("rule.conditions deve ser uma lista não-vazia")

    for i, cond in enumerate(conditions):
        if not isinstance(cond, dict):
            raise ValidationError(f"condição {i} deve ser um objeto")
        field = cond.get("field")
        op = cond.get("op")
        if field not in _FIELD_LOOKUPS:
            raise ValidationError(f"condição {i}: field inválido: {field!r}")
        if op not in _OPS:
            raise ValidationError(f"condição {i}: op inválido: {op!r}")
        if "value" not in cond:
            raise ValidationError(f"condição {i}: 'value' é obrigatório")
        if op == "in" and not isinstance(cond["value"], list):
            raise ValidationError(f"condição {i}: op 'in' exige value como lista")


def _condition_to_q(cond: dict) -> Q:
    lookup = _FIELD_LOOKUPS[cond["field"]]
    op = cond["op"]
    value = cond["value"]
    if op == "eq":
        return Q(**{lookup: value})
    if op == "ne":
        return ~Q(**{lookup: value})
    if op in ("lt", "lte", "gt", "gte"):
        return Q(**{f"{lookup}__{op}": value})
    if op == "in":
        return Q(**{f"{lookup}__in": value})
    if op == "contains":
        return Q(**{f"{lookup}__icontains": value})
    raise ValidationError(f"op inválido: {op!r}")  # unreachable após validate_rule


def resolve_products(rule: dict):
    """
    Retorna o ``QuerySet`` de Products que satisfazem a regra.

    Puro: aplica só a regra (não filtra published/sellable — quem consome decide).
    ``.distinct()`` quando há joins multiplicadores (keyword/collection).
    """
    from shopman.offerman.models import Product

    validate_rule(rule)

    match = rule.get("match", "all")
    conditions = rule["conditions"]

    combined: Q | None = None
    for cond in conditions:
        q = _condition_to_q(cond)
        if combined is None:
            combined = q
        elif match == "any":
            combined |= q
        else:
            combined &= q

    qs = Product.objects.filter(combined)
    if any(cond["field"] in _MULTI_JOIN_FIELDS for cond in conditions):
        qs = qs.distinct()
    return qs
