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

        from unittest.mock import MagicMock

        mock_planned = MagicMock()
        with patch.dict(
            production_lifecycle._PRODUCTION_PHASE_HANDLERS["standard"],
            {"on_planned": mock_planned},
        ):
            wo = craft.plan(recipe, Decimal("5"), date=today)
            mock_planned.assert_called_once()
            args, _ = mock_planned.call_args
            assert args[0].pk == wo.pk

    def test_start_triggers_on_started_only_once(self):
        recipe = Recipe.objects.create(
            ref="pf-adj",
            name="Adj",
            output_sku="SKU-A",
            batch_size=Decimal("1"),
        )
        today = timezone.localdate()
        wo = craft.plan(recipe, Decimal("5"), date=today)

        from unittest.mock import MagicMock

        mock_started = MagicMock()
        with patch.dict(
            production_lifecycle._PRODUCTION_PHASE_HANDLERS["standard"],
            {"on_started": mock_started},
        ):
            craft.start(wo, quantity=Decimal("4"), actor="test")
            mock_started.assert_called_once()

            craft.finish(wo, finished=Decimal("3"), actor="test2")
            assert mock_started.call_count == 1

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

    def test_action_to_phase_covers_all_lifecycle_actions(self):
        assert production_lifecycle._action_to_phase("planned") == "on_planned"
        assert production_lifecycle._action_to_phase("started") == "on_started"
        assert production_lifecycle._action_to_phase("finished") == "on_finished"
        assert production_lifecycle._action_to_phase("voided") == "on_voided"
        # adjusted não tem fase própria — ajuste de quantidade não re-coordena.
        assert production_lifecycle._action_to_phase("adjusted") is None
        assert production_lifecycle._action_to_phase("") is None

    def test_available_lifecycles_and_choices_are_consistent(self):
        names = production_lifecycle.available_lifecycles()
        assert names == ("standard", "forecast", "subcontract")
        choices = production_lifecycle.production_lifecycle_choices()
        assert [value for value, _ in choices] == list(names)
        assert all(label for _, label in choices)


class TestLifecycleVariants:
    def _make_wo(self, *, lifecycle: str, ref: str, sku: str):
        recipe = Recipe.objects.create(
            ref=ref,
            name=ref,
            output_sku=sku,
            batch_size=Decimal("1"),
            meta={"production_lifecycle": lifecycle} if lifecycle != "standard" else {},
        )
        return craft.plan(recipe, Decimal("5"), date=timezone.localdate())

    def test_standard_phases_call_services(self):
        with (
            patch("shopman.shop.services.production.reserve_materials") as reserve,
            patch("shopman.shop.services.production.notify") as notify,
            patch("shopman.shop.services.production.emit_goods") as emit,
        ):
            wo = self._make_wo(lifecycle="standard", ref="std-var", sku="SKU-STD")
            reserve.assert_called_once()
            notify.assert_called_with(wo, "planned")

            craft.start(wo, quantity=Decimal("5"), actor="t")
            notify.assert_called_with(wo, "started")

            craft.finish(wo, finished=Decimal("5"), actor="t")
            emit.assert_called_once()
            notify.assert_called_with(wo, "finished")

    def test_subcontract_phases_use_subcontract_events(self):
        with (
            patch("shopman.shop.services.production.reserve_materials") as reserve,
            patch("shopman.shop.services.production.notify") as notify,
            patch("shopman.shop.services.production.emit_goods") as emit,
        ):
            wo = self._make_wo(lifecycle="subcontract", ref="sub-var", sku="SKU-SUB")
            reserve.assert_called_once()
            notify.assert_called_with(wo, "subcontract_planned")

            craft.start(wo, quantity=Decimal("5"), actor="t")
            notify.assert_called_with(wo, "subcontract_in_progress")

            craft.finish(wo, finished=Decimal("5"), actor="t")
            emit.assert_called_once()
            notify.assert_called_with(wo, "subcontract_finished")

    def test_voided_dispatches_notify(self):
        wo = self._make_wo(lifecycle="standard", ref="void-var", sku="SKU-VD")
        with patch("shopman.shop.services.production.notify") as notify:
            craft.void(order=wo, reason="teste", actor="t")
            notify.assert_called_once_with(wo, "voided")

    def test_unknown_lifecycle_falls_back_to_standard(self):
        with patch("shopman.shop.services.production.notify") as notify:
            recipe = Recipe.objects.create(
                ref="mystery",
                name="Mystery",
                output_sku="SKU-MY",
                batch_size=Decimal("1"),
                meta={"production_lifecycle": "inexistente"},
            )
            wo = craft.plan(recipe, Decimal("2"), date=timezone.localdate())
            notify.assert_called_with(wo, "planned")  # handler standard
