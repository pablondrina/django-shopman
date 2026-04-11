"""Tests for WP-S5 — ProductionFlow (production_changed → dispatch_production)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from shopman.craftsman.models import Recipe
from shopman.craftsman.service import craft
from shopman.production_lifecycle import StandardFlow, production_flow_name_for

pytestmark = pytest.mark.django_db


class TestProductionFlowName:
    def test_default_is_standard(self):
        recipe = Recipe.objects.create(
            code="pf-test",
            name="PF Test",
            output_ref="SKU-PF",
            batch_size=Decimal("1"),
        )
        assert production_flow_name_for(recipe) == "standard"

    def test_meta_overrides(self):
        recipe = Recipe.objects.create(
            code="pf-forecast",
            name="Forecast",
            output_ref="SKU-F",
            batch_size=Decimal("1"),
            meta={"production_flow": "forecast"},
        )
        assert production_flow_name_for(recipe) == "forecast"


class TestDispatchMapping:
    def test_planned_triggers_on_planned(self):
        recipe = Recipe.objects.create(
            code="pf-plan",
            name="Plan",
            output_ref="SKU-P",
            batch_size=Decimal("1"),
        )
        today = timezone.localdate()

        with patch.object(StandardFlow, "on_planned", autospec=True) as mock_planned:
            wo = craft.plan(recipe, Decimal("5"), date=today)
            mock_planned.assert_called_once()
            args, _ = mock_planned.call_args
            assert args[1].pk == wo.pk

    def test_first_adjust_triggers_on_started_only_once(self):
        recipe = Recipe.objects.create(
            code="pf-adj",
            name="Adj",
            output_ref="SKU-A",
            batch_size=Decimal("1"),
        )
        today = timezone.localdate()
        wo = craft.plan(recipe, Decimal("5"), date=today)

        with patch.object(StandardFlow, "on_started", autospec=True) as mock_started:
            craft.adjust(wo, quantity=Decimal("4"), reason="test")
            mock_started.assert_called_once()

            craft.adjust(wo, quantity=Decimal("3"), reason="test2")
            assert mock_started.call_count == 1

    def test_forecast_flow_logs_on_close(self):
        recipe = Recipe.objects.create(
            code="pf-fc",
            name="Fc",
            output_ref="SKU-FC",
            batch_size=Decimal("1"),
            meta={"production_flow": "forecast"},
        )
        today = timezone.localdate()
        wo = craft.plan(recipe, Decimal("5"), date=today)

        with patch("shopman.production_lifecycle.logger.info") as log_info:
            craft.close(wo, produced=5, actor="t")
            texts = " ".join(str(c) for c in log_info.call_args_list)
            assert "ForecastFlow" in texts
