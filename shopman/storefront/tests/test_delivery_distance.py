"""
WP-11 — Taxa de entrega por faixa de DISTÂNCIA (motor) + zona como exceção.

Cobertura:
  - haversine_km — sanidade contra distância conhecida
  - store_distance_km — usa Shop.lat/lng; None sem coordenada
  - DeliveryDistanceBand.match — dentro da faixa, fronteira, além de todas
  - DeliveryFeeModifier — distância casa faixa → taxa da faixa + delivery_distance_km
  - DeliveryFeeModifier — distância além de todas as faixas → fora da área
  - DeliveryFeeModifier — zona override sobrepõe a faixa de distância
  - DeliveryFeeModifier — zona exclude bloqueia mesmo com faixa válida
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase

from shopman.shop.models import Shop
from shopman.shop.models.shop import SHOP_CACHE_KEY
from shopman.shop.modifiers import DeliveryFeeModifier
from shopman.shop.services import delivery_distance
from shopman.storefront.models import DeliveryDistanceBand, DeliveryZone

# Loja de referência (Londrina) — mesma origem do seed.
ORIGIN_LAT = -23.3045
ORIGIN_LNG = -51.1628
# ~1.11 km por 0.01° de latitude → destinos deterministas a partir da origem.
DEST_2KM = (ORIGIN_LAT + 0.018, ORIGIN_LNG)   # ≈ 2,0 km
DEST_8KM = (ORIGIN_LAT + 0.072, ORIGIN_LNG)   # ≈ 8,0 km
DEST_15KM = (ORIGIN_LAT + 0.135, ORIGIN_LNG)  # ≈ 15,0 km (além de todas as faixas)


def _make_shop(*, lat=ORIGIN_LAT, lng=ORIGIN_LNG):
    cache.delete(SHOP_CACHE_KEY)
    return Shop.objects.create(name="Test Shop", latitude=lat, longitude=lng)


def _seed_bands(shop):
    DeliveryDistanceBand.objects.create(shop=shop, max_distance_km="3.00", fee_q=500, sort_order=10)
    DeliveryDistanceBand.objects.create(shop=shop, max_distance_km="6.00", fee_q=800, sort_order=20)
    DeliveryDistanceBand.objects.create(shop=shop, max_distance_km="10.00", fee_q=1200, sort_order=30)


class TestHaversine(TestCase):
    def test_one_degree_latitude_is_about_111km(self):
        km = delivery_distance.haversine_km(0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(km, 111.19, delta=0.5)

    def test_same_point_is_zero(self):
        self.assertEqual(delivery_distance.haversine_km(-23.3, -51.1, -23.3, -51.1), 0.0)


class TestStoreDistance(TestCase):
    def test_distance_from_store(self):
        _make_shop()
        km = delivery_distance.store_distance_km(*DEST_2KM)
        self.assertIsNotNone(km)
        self.assertAlmostEqual(km, 2.0, delta=0.2)

    def test_none_without_dest_coords(self):
        _make_shop()
        self.assertIsNone(delivery_distance.store_distance_km(None, None))

    def test_none_without_store_coords(self):
        _make_shop(lat=None, lng=None)
        self.assertIsNone(delivery_distance.store_distance_km(*DEST_2KM))


class TestDistanceBandMatch(TestCase):
    def setUp(self):
        self.shop = _make_shop()
        _seed_bands(self.shop)

    def test_match_within_first_band(self):
        band = DeliveryDistanceBand.match(2.0)
        self.assertEqual(band.fee_q, 500)

    def test_match_on_boundary_is_inclusive(self):
        band = DeliveryDistanceBand.match(3.0)
        self.assertEqual(band.fee_q, 500)

    def test_match_middle_band(self):
        band = DeliveryDistanceBand.match(8.0)
        self.assertEqual(band.fee_q, 1200)

    def test_beyond_all_bands_returns_none(self):
        self.assertIsNone(DeliveryDistanceBand.match(50.0))

    def test_inactive_band_ignored(self):
        DeliveryDistanceBand.objects.update(is_active=False)
        self.assertIsNone(DeliveryDistanceBand.match(2.0))


class TestDeliveryFeeModifierByDistance(TestCase):
    def setUp(self):
        self.shop = _make_shop()
        _seed_bands(self.shop)
        self.modifier = DeliveryFeeModifier()

    def _delivery_session(self, dest):
        session = MagicMock()
        session.data = {
            "fulfillment_type": "delivery",
            "delivery_address_structured": {
                "postal_code": "86050-000",
                "neighborhood": "Centro",
                "latitude": dest[0],
                "longitude": dest[1],
            },
        }
        session.items = []
        return session

    def test_distance_sets_band_fee_and_distance(self):
        session = self._delivery_session(DEST_2KM)
        self.modifier.apply(channel=None, session=session, ctx={})
        self.assertEqual(session.data.get("delivery_fee_q"), 500)
        self.assertAlmostEqual(session.data.get("delivery_distance_km"), 2.0, delta=0.2)
        self.assertNotIn("delivery_zone_error", session.data)

    def test_middle_band_fee(self):
        session = self._delivery_session(DEST_8KM)
        self.modifier.apply(channel=None, session=session, ctx={})
        self.assertEqual(session.data.get("delivery_fee_q"), 1200)

    def test_beyond_bands_is_out_of_area(self):
        session = self._delivery_session(DEST_15KM)
        self.modifier.apply(channel=None, session=session, ctx={})
        self.assertTrue(session.data.get("delivery_zone_error"))
        self.assertNotIn("delivery_fee_q", session.data)
        # Distância ainda é exposta, mesmo bloqueado (transparência).
        self.assertAlmostEqual(session.data.get("delivery_distance_km"), 15.0, delta=0.5)

    @patch("shopman.shop.services.geocoding.forward_geocode")
    def test_geocodes_address_without_coords_then_prices_by_band(self, mock_geo):
        # Caminho feliz p/ ViaCEP/manual: endereço SEM coordenada → geocode resolve → faixa.
        mock_geo.return_value = DEST_2KM
        session = MagicMock()
        session.data = {
            "fulfillment_type": "delivery",
            "delivery_address_structured": {
                "route": "Rua Teste", "street_number": "10", "neighborhood": "Centro",
                "city": "Londrina", "state_code": "PR", "postal_code": "86050-000",
            },  # sem latitude/longitude
        }
        session.items = []
        self.modifier.apply(channel=None, session=session, ctx={})
        mock_geo.assert_called_once()
        self.assertEqual(session.data.get("delivery_fee_q"), 500)  # faixa de 2 km
        self.assertNotIn("delivery_zone_error", session.data)

    def test_override_zone_wins_over_distance(self):
        DeliveryZone.objects.create(
            shop=self.shop,
            name="Centro cortesia",
            mode=DeliveryZone.MODE_OVERRIDE,
            zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
            match_value="Centro",
            fee_q=0,  # grátis, sobrepõe a faixa de 2 km (R$ 5,00)
        )
        session = self._delivery_session(DEST_2KM)
        self.modifier.apply(channel=None, session=session, ctx={})
        self.assertEqual(session.data.get("delivery_fee_q"), 0)
        self.assertNotIn("delivery_zone_error", session.data)

    def test_exclude_zone_blocks_despite_valid_band(self):
        DeliveryZone.objects.create(
            shop=self.shop,
            name="Não entrego no Centro",
            mode=DeliveryZone.MODE_EXCLUDE,
            zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
            match_value="Centro",
            fee_q=0,
        )
        session = self._delivery_session(DEST_2KM)  # dentro da faixa de 2 km
        self.modifier.apply(channel=None, session=session, ctx={})
        self.assertTrue(session.data.get("delivery_zone_error"))
        self.assertNotIn("delivery_fee_q", session.data)


class TestDistanceDisplay(TestCase):
    """Formatação pt-BR da distância exibida no checkout/tracking (slice 2)."""

    def test_cart_presentation_display(self):
        from shopman.storefront.presentation.cart import _delivery_distance_display

        self.assertIsNone(_delivery_distance_display(_FakeKm(None)))
        self.assertEqual(_delivery_distance_display(_FakeKm(2.0)), "2 km")
        self.assertEqual(_delivery_distance_display(_FakeKm(2.5)), "2,5 km")

    def test_tracking_presentation_display(self):
        from shopman.storefront.presentation.order_tracking import _delivery_distance_display

        self.assertIsNone(_delivery_distance_display(None))
        self.assertEqual(_delivery_distance_display(10.0), "10 km")
        self.assertEqual(_delivery_distance_display(3.4), "3,4 km")


class _FakeKm:
    """Mínimo que `cart._delivery_distance_display` lê (`.delivery_distance_km`)."""

    def __init__(self, km):
        self.delivery_distance_km = km
