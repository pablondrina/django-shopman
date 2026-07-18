"""Arc C: CatalogSyncState model/service + handler recording."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from shopman.offerman.protocols.projection import ProjectedItem, ProjectionResult

from shopman.shop.models import CatalogSyncState
from shopman.shop.services import catalog_sync

pytestmark = pytest.mark.django_db


class TestRecordSync:
    def test_creates_state(self):
        state = catalog_sync.record_sync("PAO", "meta", status="synced", external_id="PAO")
        assert state.status == "synced"
        assert state.external_id == "PAO"
        assert state.last_synced_at is not None

    def test_synced_stamps_timestamp_error_does_not(self):
        catalog_sync.record_sync("PAO", "meta", status="error", error="boom")
        state = CatalogSyncState.objects.get(sku="PAO", platform="meta")
        assert state.status == "error"
        assert state.last_error == "boom"
        assert state.last_synced_at is None

    def test_upsert_updates_in_place(self):
        catalog_sync.record_sync("PAO", "meta", status="error", error="x")
        catalog_sync.record_sync("PAO", "meta", status="synced")
        assert CatalogSyncState.objects.filter(sku="PAO", platform="meta").count() == 1
        state = CatalogSyncState.objects.get(sku="PAO", platform="meta")
        assert state.status == "synced"
        assert state.last_error == ""  # cleared on success

    def test_pending_clears_error(self):
        catalog_sync.record_sync("PAO", "meta", status="error", error="x")
        catalog_sync.record_sync("PAO", "meta", status="pending")
        assert CatalogSyncState.objects.get(sku="PAO", platform="meta").last_error == ""

    def test_external_id_only_overwritten_when_provided(self):
        catalog_sync.record_sync("PAO", "meta", status="synced", external_id="EXT-1")
        catalog_sync.record_sync("PAO", "meta", status="synced")  # no external_id
        assert CatalogSyncState.objects.get(sku="PAO", platform="meta").external_id == "EXT-1"

    def test_retracted_stamps_timestamp(self):
        state = catalog_sync.record_sync("PAO", "meta", status="retracted")
        assert state.last_synced_at is not None


class TestSyncStatusMap:
    def test_map_shape_and_filters(self):
        catalog_sync.record_sync("PAO", "meta", status="synced")
        catalog_sync.record_sync("PAO", "google", status="error", error="e")
        catalog_sync.record_sync("BOLO", "meta", status="synced")

        full = catalog_sync.sync_status_map()
        assert full["PAO"]["meta"]["status"] == "synced"
        assert full["PAO"]["google"]["status"] == "error"
        assert full["BOLO"]["meta"]["status"] == "synced"

        by_platform = catalog_sync.sync_status_map(platform="meta")
        assert "google" not in by_platform["PAO"]

        by_sku = catalog_sync.sync_status_map(["PAO"])
        assert set(by_sku) == {"PAO"}


class TestHandlerRecordsState:
    @pytest.fixture
    def ifood_channel(self):
        from shopman.shop.models import Channel
        return Channel.objects.create(ref="ifood", name="iFood", is_active=True)

    @pytest.fixture
    def directive(self):
        from shopman.orderman.models import Directive

        from shopman.shop.directives import CATALOG_PROJECT_SKU
        return Directive.objects.create(
            topic=CATALOG_PROJECT_SKU, payload={"sku": "PAO", "listing_ref": "ifood"},
        )

    def _item(self, *, sellable=True):
        return ProjectedItem(
            sku="PAO", name="Pão", description="", unit="un",
            price_q=500, is_published=True, is_sellable=sellable,
        )

    def test_project_success_records_synced(self, ifood_channel, directive):
        from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

        backend = MagicMock()
        backend.project.return_value = ProjectionResult(success=True, projected=1, channel="ifood")
        handler = CatalogProjectHandler(backend=backend)
        with patch(
            "shopman.shop.handlers.catalog_projection._get_projected_item",
            return_value=self._item(),
        ):
            handler.handle(message=directive, ctx={})

        assert CatalogSyncState.objects.get(sku="PAO", platform="ifood").status == "synced"

    def test_retract_records_retracted(self, ifood_channel, directive):
        from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

        backend = MagicMock()
        backend.retract.return_value = ProjectionResult(success=True, projected=1, channel="ifood")
        handler = CatalogProjectHandler(backend=backend)
        with patch(
            "shopman.shop.handlers.catalog_projection._get_projected_item",
            return_value=self._item(sellable=False),
        ):
            handler.handle(message=directive, ctx={})

        assert CatalogSyncState.objects.get(sku="PAO", platform="ifood").status == "retracted"

    def test_failure_records_error(self, ifood_channel, directive):
        from shopman.orderman.exceptions import DirectiveTransientError

        from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

        backend = MagicMock()
        backend.project.return_value = ProjectionResult(success=False, errors=["boom"], channel="ifood")
        handler = CatalogProjectHandler(backend=backend)
        with patch(
            "shopman.shop.handlers.catalog_projection._get_projected_item",
            return_value=self._item(),
        ):
            with pytest.raises(DirectiveTransientError):
                handler.handle(message=directive, ctx={})

        state = CatalogSyncState.objects.get(sku="PAO", platform="ifood")
        assert state.status == "error"
        assert "boom" in state.last_error
