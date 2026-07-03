"""
ProductionConfig — contrato, cascata Shop.defaults["production"] e validação.

Espelha o padrão de conformance do ChannelConfig: defaults sensatos, overrides
via Shop.defaults, validação que acusa cedo com mensagens específicas.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from shopman.shop.models import Shop
from shopman.shop.production_config import ProductionConfig

pytestmark = pytest.mark.django_db


# ── Defaults ──


class TestDefaults:
    def test_defaults_are_sane(self):
        config = ProductionConfig()
        assert config.suggestion.seasons == {}
        assert config.suggestion.high_demand_multiplier is None
        assert config.suggestion.safety_stock_percent is None
        assert config.suggestion.horizon_days == 1
        assert config.alerts.low_yield_threshold == "0.80"
        assert config.alerts.default_max_started_minutes == 240
        assert config.alerts.late_check_cadence_minutes == 15
        assert config.order_match == "first_planned"

    def test_defaults_validate(self):
        ProductionConfig().validate()

    def test_load_without_shop_returns_defaults(self):
        config = ProductionConfig.load()
        assert config.to_dict() == ProductionConfig.defaults()


# ── Cascata ──


class TestCascade:
    def test_shop_defaults_override(self):
        Shop.objects.create(
            name="Nelson",
            defaults={
                "production": {
                    "suggestion": {
                        "seasons": {"hot": [12, 1, 2]},
                        "high_demand_multiplier": "1.2",
                        "safety_stock_percent": "0.30",
                    },
                    "alerts": {"low_yield_threshold": "0.70"},
                    "order_match": "earliest_target",
                }
            },
        )
        config = ProductionConfig.load()
        assert config.suggestion.seasons == {"hot": [12, 1, 2]}
        assert config.suggestion.high_demand_multiplier_decimal == Decimal("1.2")
        assert config.suggestion.safety_stock_percent_decimal == Decimal("0.30")
        assert config.alerts.low_yield_threshold_decimal == Decimal("0.70")
        # Chave ausente herda o default.
        assert config.alerts.default_max_started_minutes == 240
        assert config.order_match == "earliest_target"

    def test_unknown_keys_are_ignored(self):
        Shop.objects.create(
            name="Nelson",
            defaults={"production": {"suggestion": {"typo_key": 1}, "another": True}},
        )
        config = ProductionConfig.load()
        assert config.to_dict() == ProductionConfig.defaults()

    def test_invalid_override_raises_on_load(self):
        Shop.objects.create(
            name="Nelson",
            defaults={"production": {"order_match": "bogus"}},
        )
        with pytest.raises(ValueError, match="order_match"):
            ProductionConfig.load()


# ── Sugestão ──


class TestSuggestion:
    def test_season_months_for_resolves_containing_season(self):
        config = ProductionConfig.from_dict(
            {"suggestion": {"seasons": {"hot": [12, 1, 2], "cold": [6, 7, 8]}}}
        )
        assert config.suggestion.season_months_for(1) == [12, 1, 2]
        assert config.suggestion.season_months_for(7) == [6, 7, 8]

    def test_season_months_for_returns_none_outside_seasons(self):
        config = ProductionConfig.from_dict({"suggestion": {"seasons": {"hot": [12, 1]}}})
        assert config.suggestion.season_months_for(5) is None

    def test_season_months_for_without_seasons(self):
        assert ProductionConfig().suggestion.season_months_for(3) is None

    def test_decimal_properties_none_when_unset(self):
        config = ProductionConfig()
        assert config.suggestion.high_demand_multiplier_decimal is None
        assert config.suggestion.safety_stock_percent_decimal is None


# ── Validação ──


class TestValidation:
    @pytest.mark.parametrize(
        ("overrides", "match"),
        [
            ({"suggestion": {"seasons": "not-a-dict"}}, "seasons"),
            ({"suggestion": {"seasons": {"hot": [13]}}}, "meses 1-12"),
            ({"suggestion": {"seasons": {"hot": "jan"}}}, "meses 1-12"),
            ({"suggestion": {"high_demand_multiplier": "abc"}}, "high_demand_multiplier"),
            ({"suggestion": {"high_demand_multiplier": "-1"}}, "high_demand_multiplier"),
            ({"suggestion": {"safety_stock_percent": "x"}}, "safety_stock_percent"),
            ({"suggestion": {"horizon_days": -1}}, "horizon_days"),
            ({"alerts": {"low_yield_threshold": "1.5"}}, "low_yield_threshold"),
            ({"alerts": {"low_yield_threshold": "nope"}}, "low_yield_threshold"),
            ({"alerts": {"default_max_started_minutes": 0}}, "default_max_started_minutes"),
            ({"alerts": {"late_check_cadence_minutes": -5}}, "late_check_cadence_minutes"),
            ({"order_match": "wrong"}, "order_match"),
        ],
    )
    def test_invalid_values_raise(self, overrides, match):
        config = ProductionConfig.from_dict(overrides)
        with pytest.raises(ValueError, match=match):
            config.validate()

    def test_cadence_zero_is_valid_meaning_disabled(self):
        ProductionConfig.from_dict({"alerts": {"late_check_cadence_minutes": 0}}).validate()
