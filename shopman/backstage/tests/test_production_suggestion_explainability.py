"""Sugestão explicável (WP-PE4) — o número explica a si mesmo.

O basis que o Core já entrega (média, amostra, committed, margem, estação,
reforço, perda) vira frases de gente na projection — a superfície só renderiza.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.models import Recipe
from shopman.craftsman.services.queries import Suggestion

from shopman.backstage.projections.production import _build_suggestion

pytestmark = pytest.mark.django_db


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="baguete", name="Baguete", output_sku="BAGUETE", batch_size=1
    )


def _suggestion(recipe, **basis_overrides):
    basis = {
        "avg_demand": Decimal("28.5"),
        "committed": Decimal("12"),
        "safety_pct": Decimal("0.20"),
        "historical_days": 28,
        "same_weekday": True,
        "sample_size": 4,
        "confidence": "medium",
        "season": None,
        "waste_rate": None,
        "high_demand_applied": False,
    }
    basis.update(basis_overrides)
    return Suggestion(recipe=recipe, quantity=Decimal("49"), basis=basis)


class TestSuggestionExplainability:
    def test_baseline_parts(self, recipe):
        projection = _build_suggestion(_suggestion(recipe))
        assert projection.sample_size == 4
        assert projection.explanation_parts == (
            "Média de venda: 28,5/dia (4 dias de histórico, mesmo dia da semana)",
            "Encomendas já confirmadas: 12",
            "Margem de segurança: 20%",
        )

    def test_all_factors_present(self, recipe):
        projection = _build_suggestion(
            _suggestion(
                recipe,
                season="hot",
                waste_rate=Decimal("0.18"),
                high_demand_applied=True,
                same_weekday=False,
            )
        )
        assert projection.explanation_parts == (
            "Média de venda: 28,5/dia (4 dias de histórico)",
            "Encomendas já confirmadas: 12",
            "Margem de segurança: 20%",
            "Desconto por perda histórica: 18%",
            "Reforço de sexta/sábado aplicado",
            "Histórico filtrado pela estação: hot",
        )
        assert projection.high_demand_applied

    def test_zero_committed_is_omitted(self, recipe):
        projection = _build_suggestion(_suggestion(recipe, committed=Decimal("0")))
        assert not any("Encomendas" in part for part in projection.explanation_parts)

    def test_missing_basis_degrades_quietly(self, recipe):
        projection = _build_suggestion(Suggestion(recipe=recipe, quantity=Decimal("10"), basis={}))
        assert projection.explanation_parts == ()
        assert projection.sample_size == 0
