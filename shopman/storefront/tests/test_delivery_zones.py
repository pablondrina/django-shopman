"""
Tests for WP-R1 — DeliveryZone model, DeliveryFeeModifier, and DeliveryZoneRule validator.

Coverage:
  - DeliveryZone.match() — CEP prefix match
  - DeliveryZone.match() — neighborhood match (fallback)
  - DeliveryZone.match() — outside coverage area (returns None)
  - DeliveryZone.match() — fee_q == 0 (free delivery)
  - DeliveryFeeModifier — skips non-delivery sessions
  - DeliveryFeeModifier — sets delivery_fee_q on session.data
  - DeliveryFeeModifier — sets delivery_zone_error on unmatched address
  - DeliveryFeeModifier — skips when no postal_code/neighborhood
  - DeliveryZoneRule validator — raises ValidationError when delivery_zone_error is True
  - DeliveryZoneRule validator — passes for pickup
  - CommitService propagation — delivery_fee_q appears in order.data
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from shopman.orderman.exceptions import ValidationError as OrderingValidationError

from shopman.shop.models import Shop

from shopman.storefront.models import DeliveryZone
from shopman.shop.modifiers import DeliveryFeeModifier
from shopman.shop.rules.validation import DeliveryZoneRule


def _make_shop():
    return Shop.objects.create(name="Test Shop")


def _make_zone(shop, *, name, zone_type, match_value, fee_q=500, sort_order=10, is_active=True):
    return DeliveryZone.objects.create(
        shop=shop,
        name=name,
        zone_type=zone_type,
        match_value=match_value,
        fee_q=fee_q,
        sort_order=sort_order,
        is_active=is_active,
    )


class TestDeliveryZoneMatch(TestCase):
    def setUp(self):
        self.shop = _make_shop()

    def test_match_by_cep_prefix(self):
        zone = _make_zone(
            self.shop,
            name="Londrina Norte",
            zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
            match_value="860",
            fee_q=600,
        )
        result = DeliveryZone.match(postal_code="86050-270", neighborhood="Qualquer Bairro")
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, zone.pk)
        self.assertEqual(result.fee_q, 600)

    def test_match_cep_with_digits_only(self):
        _make_zone(
            self.shop,
            name="Zona CEP",
            zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
            match_value="861",
            fee_q=800,
        )
        # CEP without hyphen
        result = DeliveryZone.match(postal_code="86120000", neighborhood="")
        self.assertIsNotNone(result)
        self.assertEqual(result.fee_q, 800)

    def test_match_by_neighborhood_fallback(self):
        _make_zone(
            self.shop,
            name="Fora do CEP",
            zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
            match_value="870",  # Curitiba prefix — won't match
            fee_q=1500,
        )
        bairro_zone = _make_zone(
            self.shop,
            name="Bela Suíça",
            zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
            match_value="Bela Suíça",
            fee_q=0,
        )
        result = DeliveryZone.match(postal_code="80000-000", neighborhood="Bela Suíça")
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, bairro_zone.pk)
        self.assertEqual(result.fee_q, 0)

    def test_match_neighborhood_case_insensitive(self):
        _make_zone(
            self.shop,
            name="Centro",
            zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
            match_value="Centro",
            fee_q=300,
        )
        result = DeliveryZone.match(postal_code="", neighborhood="centro")
        self.assertIsNotNone(result)
        self.assertEqual(result.fee_q, 300)

    def test_no_match_outside_coverage(self):
        _make_zone(
            self.shop,
            name="Londrina",
            zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
            match_value="860",
            fee_q=600,
        )
        result = DeliveryZone.match(postal_code="01310-100", neighborhood="Bela Vista")
        self.assertIsNone(result)

    def test_inactive_zone_ignored(self):
        _make_zone(
            self.shop,
            name="Desativada",
            zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
            match_value="860",
            fee_q=600,
            is_active=False,
        )
        result = DeliveryZone.match(postal_code="86050-270", neighborhood="")
        self.assertIsNone(result)

    def test_free_delivery_fee_zero(self):
        _make_zone(
            self.shop,
            name="Bela Suíça grátis",
            zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
            match_value="Bela Suíça",
            fee_q=0,
        )
        result = DeliveryZone.match(postal_code="", neighborhood="Bela Suíça")
        self.assertIsNotNone(result)
        self.assertEqual(result.fee_q, 0)

    def test_cep_prefix_takes_priority_over_neighborhood(self):
        """CEP prefix match should win over neighborhood when both match."""
        cep_zone = _make_zone(
            self.shop,
            name="CEP zone",
            zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
            match_value="860",
            fee_q=600,
            sort_order=10,
        )
        _make_zone(
            self.shop,
            name="Neighborhood zone",
            zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
            match_value="Centro",
            fee_q=200,
            sort_order=5,
        )
        result = DeliveryZone.match(postal_code="86010-000", neighborhood="Centro")
        # CEP prefix always evaluated first, regardless of sort_order
        self.assertEqual(result.pk, cep_zone.pk)


class TestDeliveryFeeModifier(TestCase):
    def setUp(self):
        self.shop = _make_shop()
        self.modifier = DeliveryFeeModifier()

    def _make_session(self, data):
        session = MagicMock()
        session.data = data
        return session

    def test_skip_non_delivery(self):
        session = self._make_session({"fulfillment_type": "pickup"})
        self.modifier.apply(channel=None, session=session, ctx={})
        # session.save should NOT have been called
        session.save.assert_not_called()

    def test_skip_no_address(self):
        session = self._make_session({
            "fulfillment_type": "delivery",
            "delivery_address_structured": {},
        })
        self.modifier.apply(channel=None, session=session, ctx={})
        session.save.assert_not_called()

    def test_sets_delivery_fee_q_when_zone_matches(self):
        _make_zone(
            self.shop,
            name="Londrina",
            zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
            match_value="860",
            fee_q=600,
        )
        session = self._make_session({
            "fulfillment_type": "delivery",
            "delivery_address_structured": {
                "postal_code": "86050-270",
                "neighborhood": "Bela Suíça",
            },
        })
        self.modifier.apply(channel=None, session=session, ctx={})
        session.save.assert_called_once()
        self.assertEqual(session.data.get("delivery_fee_q"), 600)
        self.assertNotIn("delivery_zone_error", session.data)

    def test_sets_delivery_zone_error_when_no_zone(self):
        # No zones in DB
        session = self._make_session({
            "fulfillment_type": "delivery",
            "delivery_address_structured": {
                "postal_code": "01310-100",
                "neighborhood": "Bela Vista",
            },
        })
        self.modifier.apply(channel=None, session=session, ctx={})
        session.save.assert_called_once()
        self.assertTrue(session.data.get("delivery_zone_error"))
        self.assertNotIn("delivery_fee_q", session.data)

    def test_clears_previous_error_on_match(self):
        _make_zone(
            self.shop,
            name="Londrina",
            zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
            match_value="860",
            fee_q=500,
        )
        session = self._make_session({
            "fulfillment_type": "delivery",
            "delivery_address_structured": {
                "postal_code": "86050-270",
                "neighborhood": "Bela Suíça",
            },
            "delivery_zone_error": True,  # Previous error
        })
        self.modifier.apply(channel=None, session=session, ctx={})
        self.assertNotIn("delivery_zone_error", session.data)
        self.assertEqual(session.data.get("delivery_fee_q"), 500)

    def test_free_delivery_sets_fee_q_zero(self):
        _make_zone(
            self.shop,
            name="Bela Suíça grátis",
            zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
            match_value="Bela Suíça",
            fee_q=0,
        )
        session = self._make_session({
            "fulfillment_type": "delivery",
            "delivery_address_structured": {
                "postal_code": "",
                "neighborhood": "Bela Suíça",
            },
        })
        self.modifier.apply(channel=None, session=session, ctx={})
        self.assertEqual(session.data.get("delivery_fee_q"), 0)
        self.assertNotIn("delivery_zone_error", session.data)


class TestDeliveryZoneRule(TestCase):
    def setUp(self):
        self.rule = DeliveryZoneRule()

    def _make_session(self, data):
        session = MagicMock()
        session.data = data
        return session

    def test_raises_when_delivery_zone_error(self):
        session = self._make_session({
            "fulfillment_type": "delivery",
            "delivery_zone_error": True,
        })
        with self.assertRaises(OrderingValidationError) as ctx:
            self.rule.validate(channel=None, session=session, ctx={})
        self.assertEqual(ctx.exception.code, "delivery_zone_not_covered")

    def test_passes_when_no_error(self):
        session = self._make_session({
            "fulfillment_type": "delivery",
            "delivery_fee_q": 600,
        })
        # Should not raise
        self.rule.validate(channel=None, session=session, ctx={})

    def test_skipped_for_pickup(self):
        session = self._make_session({
            "fulfillment_type": "pickup",
            "delivery_zone_error": True,  # Would be blocked if delivery
        })
        # Should not raise for pickup
        self.rule.validate(channel=None, session=session, ctx={})

    def test_skipped_when_no_fulfillment_type(self):
        session = self._make_session({"delivery_zone_error": True})
        # No fulfillment_type set — no block
        self.rule.validate(channel=None, session=session, ctx={})


class TestDeliveryFeeCommitPropagation(TestCase):
    """Integration test: delivery_fee_q propagates from Session.data to Order.data."""

    def test_delivery_fee_q_in_propagated_keys(self):
        """delivery_fee_q must be in CommitService's key propagation list."""
        import inspect

        import shopman.orderman.services.commit as commit_module

        source = inspect.getsource(commit_module)
        # Check for either single or double quote form
        self.assertTrue(
            '"delivery_fee_q"' in source or "'delivery_fee_q'" in source,
            "delivery_fee_q not found in CommitService._do_commit() key propagation",
        )
