"""Tests for production lifecycle dispatch."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe
from shopman.craftsman.service import craft

from shopman.shop import production_lifecycle

pytestmark = pytest.mark.django_db


class TestProductionLifecycleName:
    def test_default_is_standard(self):
        recipe = Recipe.objects.create(
            ref="pf-test",
            name="PF Test",
            output_sku="SKU-PF",
            batch_size=Decimal("1"),
        )
        assert production_lifecycle.production_lifecycle_name_for(recipe) == "standard"

    def test_meta_overrides(self):
        recipe = Recipe.objects.create(
            ref="pf-forecast",
            name="Forecast",
            output_sku="SKU-F",
            batch_size=Decimal("1"),
            meta={"production_lifecycle": "forecast"},
        )
        assert production_lifecycle.production_lifecycle_name_for(recipe) == "forecast"


class TestDispatchMapping:
    def test_planned_triggers_on_planned(self):
        recipe = Recipe.objects.create(
            ref="pf-plan",
            name="Plan",
            output_sku="SKU-P",
            batch_size=Decimal("1"),
        )
        today = timezone.localdate()

        with patch("shopman.shop.production_lifecycle._standard_on_planned") as mock_planned:
            production_lifecycle._PRODUCTION_PHASE_HANDLERS["standard"]["on_planned"] = mock_planned
            wo = craft.plan(recipe, Decimal("5"), date=today)
            mock_planned.assert_called_once()
            args, _ = mock_planned.call_args
            assert args[0].pk == wo.pk
            production_lifecycle._PRODUCTION_PHASE_HANDLERS["standard"]["on_planned"] = (
                production_lifecycle._standard_on_planned
            )

    def test_start_triggers_on_started_only_once(self):
        recipe = Recipe.objects.create(
            ref="pf-adj",
            name="Adj",
            output_sku="SKU-A",
            batch_size=Decimal("1"),
        )
        today = timezone.localdate()
        wo = craft.plan(recipe, Decimal("5"), date=today)

        with patch("shopman.shop.production_lifecycle._standard_on_started") as mock_started:
            production_lifecycle._PRODUCTION_PHASE_HANDLERS["standard"]["on_started"] = mock_started
            craft.start(wo, quantity=Decimal("4"), actor="test")
            mock_started.assert_called_once()

            craft.finish(wo, finished=Decimal("3"), actor="test2")
            assert mock_started.call_count == 1
            production_lifecycle._PRODUCTION_PHASE_HANDLERS["standard"]["on_started"] = (
                production_lifecycle._standard_on_started
            )

    def test_forecast_lifecycle_logs_on_finish(self):
        recipe = Recipe.objects.create(
            ref="pf-fc",
            name="Fc",
            output_sku="SKU-FC",
            batch_size=Decimal("1"),
            meta={"production_lifecycle": "forecast"},
        )
        today = timezone.localdate()
        wo = craft.plan(recipe, Decimal("5"), date=today)

        with patch("shopman.shop.production_lifecycle.logger.info") as log_info:
            craft.finish(wo, finished=5, actor="t")
            texts = " ".join(str(c) for c in log_info.call_args_list)
            assert "production_lifecycle.forecast" in texts
