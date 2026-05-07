"""Tests for server-side slot validation (_validate_slot).

Covers:
- Slot inexistente → erro
- Slot passado hoje → erro
- Slot futuro hoje → OK
- Data futura → qualquer slot válido → OK
- Slot vazio + pickup → erro
- Slot vazio + delivery → OK
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase

from shopman.storefront.intents.checkout import _validate_slot

FAKE_SLOTS = [
    {"ref": "slot-09", "label": "A partir das 09h", "starts_at": "09:00"},
    {"ref": "slot-12", "label": "A partir das 12h", "starts_at": "12:00"},
    {"ref": "slot-15", "label": "A partir das 15h", "starts_at": "15:00"},
]


def _today_str() -> str:
    return date.today().isoformat()


def _future_date_str() -> str:
    return (date.today() + timedelta(days=2)).isoformat()


def _fake_now(hour: int, minute: int = 0) -> object:
    """Return a mock for timezone.localtime() at the given time of day."""

    from django.utils import timezone as tz

    now = tz.localtime()
    fake = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return fake


class TestValidateSlot(TestCase):
    def _call(self, slot_ref: str, fulfillment: str, delivery_date: str = "") -> dict:
        with patch("shopman.storefront.services.pickup_slots.get_slots", return_value=FAKE_SLOTS):
            return _validate_slot(slot_ref, fulfillment, delivery_date)

    def _call_at_hour(
        self, slot_ref: str, fulfillment: str, delivery_date: str, hour: int
    ) -> dict:
        fake = _fake_now(hour)
        with (
            patch("shopman.storefront.services.pickup_slots.get_slots", return_value=FAKE_SLOTS),
            patch("shopman.storefront.intents.checkout.timezone.localtime", return_value=fake),
        ):
            return _validate_slot(slot_ref, fulfillment, delivery_date)

    # ── Slot inexistente ──────────────────────────────────────────────────

    def test_slot_inexistente(self):
        errors = self._call("slot-99", "pickup", _today_str())
        assert "delivery_time_slot" in errors
        assert "inválido" in errors["delivery_time_slot"].lower()

    # ── Slot passado (hoje às 15h → slot-09 e slot-12 já foram superados) ─

    def test_slot_09_passado_as_15h(self):
        errors = self._call_at_hour("slot-09", "pickup", _today_str(), hour=15)
        assert "delivery_time_slot" in errors
        assert "passou" in errors["delivery_time_slot"].lower()

    def test_slot_12_passado_as_15h(self):
        errors = self._call_at_hour("slot-12", "pickup", _today_str(), hour=15)
        assert "delivery_time_slot" in errors

    # ── Slot atual/futuro hoje ───────────────────────────────────────────

    def test_slot_09_atual_as_10h(self):
        errors = self._call_at_hour("slot-09", "pickup", _today_str(), hour=10)
        assert errors == {}

    def test_slot_15_atual_as_15h(self):
        errors = self._call_at_hour("slot-15", "pickup", _today_str(), hour=15)
        assert errors == {}

    def test_slot_15_atual_depois_das_15h(self):
        errors = self._call_at_hour("slot-15", "pickup", _today_str(), hour=16)
        assert errors == {}

    def test_slot_12_futuro_as_10h(self):
        errors = self._call_at_hour("slot-12", "pickup", _today_str(), hour=10)
        assert errors == {}

    def test_slot_15_futuro_as_10h(self):
        errors = self._call_at_hour("slot-15", "pickup", _today_str(), hour=10)
        assert errors == {}

    # ── Data futura: qualquer slot válido é aceito ────────────────────────

    def test_slot_09_data_futura(self):
        # Even "past" slots are valid for a future date
        errors = self._call_at_hour("slot-09", "pickup", _future_date_str(), hour=22)
        assert errors == {}

    def test_slot_12_data_futura(self):
        errors = self._call_at_hour("slot-12", "pickup", _future_date_str(), hour=22)
        assert errors == {}

    # ── Slot vazio + pickup → exige seleção ──────────────────────────────

    def test_slot_vazio_pickup(self):
        errors = self._call("", "pickup", _today_str())
        assert "delivery_time_slot" in errors
        assert "horário" in errors["delivery_time_slot"].lower()

    def test_slot_vazio_pickup_sem_data(self):
        errors = self._call("", "pickup", "")
        assert "delivery_time_slot" in errors

    # ── Slot vazio + delivery → OK ────────────────────────────────────────

    def test_slot_vazio_delivery(self):
        errors = self._call("", "delivery", _today_str())
        assert errors == {}

    def test_slot_vazio_delivery_sem_data(self):
        errors = self._call("", "delivery", "")
        assert errors == {}
