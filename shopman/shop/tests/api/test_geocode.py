"""Tests for POST /api/v1/geocode/reverse — WP-ADDR-1."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.urls import reverse

from shopman.shop.models import Shop
from shopman.shop.services.geocoding import GeocodingError, ReverseGeocodeResult


@pytest.fixture(autouse=True)
def _shop(db):
    return Shop.objects.create(
        name="Demo Bakery",
        brand_name="Demo Bakery",
        short_name="Demo",
        tagline="Padaria",
        primary_color="#C5A55A",
        default_ddd="43",
        city="Londrina",
        state_code="PR",
    )


@pytest.fixture(autouse=True)
def _cache_clear():
    cache.clear()
    yield
    cache.clear()


def _stub_result() -> ReverseGeocodeResult:
    return ReverseGeocodeResult(
        formatted_address="R. das Flores, 123 - Centro, Londrina - PR",
        route="R. das Flores",
        street_number="123",
        neighborhood="Centro",
        city="Londrina",
        state="Paraná",
        state_code="PR",
        postal_code="86020-000",
        country="Brasil",
        country_code="BR",
        latitude=-23.31,
        longitude=-51.16,
        place_id="ChIJ-stub",
    )


@pytest.mark.django_db
class TestReverseGeocodeEndpoint:
    def test_requires_valid_coords(self, client):
        url = reverse("api-geocode-reverse")
        resp = client.post(url, data={}, content_type="application/json")
        assert resp.status_code == 400

    def test_rejects_out_of_range(self, client):
        url = reverse("api-geocode-reverse")
        resp = client.post(
            url,
            data={"lat": 999, "lng": 0},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_returns_canonical_result(self, client):
        """On success the view returns the service result verbatim."""
        url = reverse("api-geocode-reverse")
        with patch(
            "shopman.shop.api.geocode.reverse_geocode",
            return_value=_stub_result(),
        ):
            resp = client.post(
                url,
                data={"lat": -23.31, "lng": -51.16},
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["route"] == "R. das Flores"
        assert data["postal_code"] == "86020-000"
        assert data["place_id"] == "ChIJ-stub"
        assert data["latitude"] == pytest.approx(-23.31)

    def test_never_leaks_api_key(self, client, settings):
        """The endpoint must never echo GOOGLE_MAPS_API_KEY in its response."""
        settings.GOOGLE_MAPS_API_KEY = "AIzaSecretShouldStaySecret"
        url = reverse("api-geocode-reverse")
        with patch(
            "shopman.shop.api.geocode.reverse_geocode",
            return_value=_stub_result(),
        ):
            resp = client.post(
                url,
                data={"lat": -23.31, "lng": -51.16},
                content_type="application/json",
            )
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert settings.GOOGLE_MAPS_API_KEY not in body

    def test_propagates_service_failure_as_502(self, client):
        url = reverse("api-geocode-reverse")
        with patch(
            "shopman.shop.api.geocode.reverse_geocode",
            side_effect=GeocodingError("upstream down"),
        ):
            resp = client.post(
                url,
                data={"lat": -23.31, "lng": -51.16},
                content_type="application/json",
            )
        assert resp.status_code == 502
