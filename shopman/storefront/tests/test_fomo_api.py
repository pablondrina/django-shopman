"""FOMO API + serviço de contexto — badges derivados de dados reais.

Cobre: endpoint público, 404 de SKU inexistente, cache, gate de D-1 por canal,
janela de frescor da fornada e a invalidação de cache pelo emissor SSE.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.shop.services import fomo as fomo_context
from shopman.shop.services.fomo import cache_key
from shopman.storefront.services import fomo as fomo_service

pytestmark = pytest.mark.django_db

SKU = "croissant-trad"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _product(sku: str = SKU) -> Product:
    return Product.objects.create(sku=sku, name="Croissant Tradicional", is_sellable=True)


# ── Endpoint ─────────────────────────────────────────────────────────


class TestFomoEndpoint:
    def test_unknown_sku_is_404(self, client):
        assert client.get("/api/v1/fomo/nao-existe/").status_code == 404

    def test_product_without_urgency_returns_empty_list(self, client):
        _product()
        response = client.get(f"/api/v1/fomo/{SKU}/")
        assert response.status_code == 200
        assert response.json() == {"sku": SKU, "badges": []}

    def test_low_stock_surfaces_a_badge(self, client):
        _product()
        with patch(
            "shopman.shop.services.fomo._availability",
            return_value={"available_qty": 2, "d1_qty": 0},
        ):
            response = client.get(f"/api/v1/fomo/{SKU}/")
        badges = response.json()["badges"]
        assert [b["type"] for b in badges] == ["low_stock"]
        assert badges[0]["label"] == "Últimas 2 unidades"

    def test_badge_shape_is_stable(self, client):
        _product()
        with patch(
            "shopman.shop.services.fomo._availability",
            return_value={"available_qty": 1, "d1_qty": 0},
        ):
            badge = client.get(f"/api/v1/fomo/{SKU}/").json()["badges"][0]
        assert set(badge) == {"type", "label", "priority", "expires_at", "meta"}

    def test_response_is_cached(self, client):
        _product()
        with patch(
            "shopman.shop.services.fomo._availability",
            return_value={"available_qty": 3, "d1_qty": 0},
        ) as availability:
            client.get(f"/api/v1/fomo/{SKU}/")
            client.get(f"/api/v1/fomo/{SKU}/")
        assert availability.call_count == 1

    def test_channel_scopes_the_cache(self, client):
        _product()
        client.get(f"/api/v1/fomo/{SKU}/")
        assert cache.get(cache_key(SKU, None)) is not None
        assert cache.get(cache_key(SKU, "pos")) is None


# ── Contexto (serviço) ───────────────────────────────────────────────


class TestFomoContext:
    def test_d1_is_silent_when_the_channel_excludes_yesterday(self):
        """Canal que não vende D-1 não pode anunciar D-1."""
        from shopman.shop.config import ChannelConfig

        config = ChannelConfig.from_dict({"stock": {"excluded_positions": ["ontem"]}})
        assert fomo_context.d1_qty(SKU, config=config) == 0

    def test_recent_bake_enters_the_context(self):
        finished = timezone.now() - timedelta(minutes=5)
        with patch("shopman.craftsman.models.WorkOrder.objects") as manager:
            manager.filter.return_value.order_by.return_value.first.return_value = _FakeWorkOrder(
                finished
            )
            production = fomo_context.last_finished_bake(SKU)
        assert production["finished_at"] == finished
        assert production["quality"] == "excelente"

    def test_no_bake_yields_no_production(self):
        assert fomo_context.last_finished_bake(SKU) is None

    def test_lookup_failure_degrades_quietly(self):
        """FOMO é enfeite: quebrar a leitura não pode derrubar o card."""
        with patch("shopman.craftsman.models.WorkOrder.objects") as manager:
            manager.filter.side_effect = RuntimeError("boom")
            assert fomo_context.last_finished_bake(SKU) is None

    def test_badges_for_sku_composes_the_whole_chain(self):
        _product()
        with patch(
            "shopman.shop.services.fomo._availability",
            return_value={"available_qty": 1, "d1_qty": 0},
        ):
            badges = fomo_service.badges_for_sku(SKU)
        assert badges[0].label == "Última unidade"


class _FakeWorkOrder:
    ref = "WO-2026-00001"

    def __init__(self, finished_at):
        self.finished_at = finished_at
        self.meta = {"quality": "excelente"}


# ── Push SSE ─────────────────────────────────────────────────────────


class TestFomoPush:
    @patch("django_eventstream.send_event")
    def test_finished_bake_publishes_on_the_sku_channel(self, send_event):
        from shopman.shop.handlers._sse_emitters import _publish_fomo

        _publish_fomo(SKU, reason="production_finished")
        channels = [call.args[0] for call in send_event.call_args_list]
        assert f"fomo-{SKU}" in channels
        assert "fomo-catalog" in channels

    @patch("django_eventstream.send_event")
    def test_publish_invalidates_the_canonical_cache(self, send_event, client):
        from shopman.shop.handlers._sse_emitters import _publish_fomo

        _product()
        client.get(f"/api/v1/fomo/{SKU}/")
        assert cache.get(cache_key(SKU, None)) is not None

        _publish_fomo(SKU, reason="stock-update")
        assert cache.get(cache_key(SKU, None)) is None

    def test_fomo_channels_are_ephemeral(self):
        from shopman.shop.eventstream import ShopmanChannelManager

        assert ShopmanChannelManager().is_channel_reliable(f"fomo-{SKU}") is False

    def test_fomo_channels_are_public(self):
        from django.contrib.auth.models import AnonymousUser

        from shopman.shop.eventstream import ShopmanChannelManager

        assert ShopmanChannelManager().can_read_channel(AnonymousUser(), f"fomo-{SKU}")
