"""Tests for GET /api/availability/<sku>/ — WP-CL2-11."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.urls import reverse

from shopman.models import Shop
from shopman.offerman.models import Product


@pytest.fixture(autouse=True)
def _shop(db):
    return Shop.objects.create(
        name="Demo Bakery",
        brand_name="Demo Bakery",
        short_name="Demo",
        tagline="Padaria Artesanal",
        primary_color="#C5A55A",
        default_ddd="43",
        city="Londrina",
        state_code="PR",
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def product(db):
    return Product.objects.create(
        sku="PAO-001",
        name="Pão Francês",
        base_price_q=80,
        is_published=True,
        is_sellable=True,
    )


AVAILABLE_RESULT = {
    "ok": True,
    "available_qty": Decimal("100"),
    "is_paused": False,
    "is_planned": False,
    "breakdown": {"ready": Decimal("100"), "in_production": Decimal("0"), "d1": Decimal("0")},
    "error_code": None,
    "is_bundle": False,
    "failed_sku": None,
}

SOLD_OUT_RESULT = {
    "ok": False,
    "available_qty": Decimal("0"),
    "is_paused": False,
    "is_planned": False,
    "breakdown": {"ready": Decimal("0"), "in_production": Decimal("0"), "d1": Decimal("0")},
    "error_code": "insufficient_stock",
    "is_bundle": False,
    "failed_sku": None,
}

NOT_IN_LISTING_RESULT = {
    "ok": False,
    "available_qty": Decimal("0"),
    "is_paused": False,
    "is_planned": False,
    "breakdown": {"ready": Decimal("0"), "in_production": Decimal("0"), "d1": Decimal("0")},
    "error_code": "not_in_listing",
    "is_bundle": False,
    "failed_sku": None,
}


@pytest.mark.django_db
class TestAvailabilityView:
    def _url(self, sku: str) -> str:
        return reverse("api-availability", kwargs={"sku": sku})

    def test_404_nonexistent_sku(self, client):
        resp = client.get(self._url("DOES-NOT-EXIST"))
        assert resp.status_code == 404

    def test_available_sku(self, client, product):
        with patch("shopman.api.availability.avail_service.check", return_value=AVAILABLE_RESULT):
            resp = client.get(self._url(product.sku))
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["badge_class"] == "badge-available"
        assert data["badge_text"] == "Disponível"
        assert data["is_bundle"] is False

    def test_sold_out_sku(self, client, product):
        with patch("shopman.api.availability.avail_service.check", return_value=SOLD_OUT_RESULT):
            resp = client.get(self._url(product.sku))
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["badge_class"] == "badge-sold-out"
        assert data["badge_text"] == "Esgotado"

    def test_not_in_listing(self, client, product):
        with patch("shopman.api.availability.avail_service.check", return_value=NOT_IN_LISTING_RESULT):
            resp = client.get(self._url(product.sku))
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["badge_class"] == "badge-unavailable"
        assert data["badge_text"] == "Indisponível"

    def test_cache_prevents_double_call(self, client, product):
        with patch("shopman.api.availability.avail_service.check", return_value=AVAILABLE_RESULT) as mock_check:
            client.get(self._url(product.sku))
            client.get(self._url(product.sku))
        # check() should only be called once (second call hits cache)
        assert mock_check.call_count == 1

    def test_channel_param_passed_to_check(self, client, product):
        with patch("shopman.api.availability.avail_service.check", return_value=AVAILABLE_RESULT) as mock_check:
            client.get(self._url(product.sku) + "?channel=web")
        mock_check.assert_called_once_with(product.sku, Decimal("1"), channel_ref="web")

    def test_no_auth_required(self, client, product):
        """Endpoint is public — no credentials needed."""
        with patch("shopman.api.availability.avail_service.check", return_value=AVAILABLE_RESULT):
            resp = client.get(self._url(product.sku))
        assert resp.status_code == 200

    def test_url_resolves_correctly(self, db):
        url = reverse("api-availability", kwargs={"sku": "PAO-001"})
        assert url == "/api/availability/PAO-001/"
