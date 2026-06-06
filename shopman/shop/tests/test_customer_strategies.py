"""Tests for built-in customer resolution strategies.

Focus on the generic counter (balcão) strategy: phone-first → tax id →
anonymous, all through the customer adapter. The strategy is registered under
the configured POS channel ref.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from shopman.shop.services import customer as customer_service
from shopman.shop.services.customer import SkipAnonymous, _handle_counter


def _order(customer: dict) -> SimpleNamespace:
    return SimpleNamespace(snapshot={"data": {"customer": customer}}, data={"customer": customer})


@pytest.fixture
def adapter():
    a = MagicMock()
    a.get_customer_by_phone.return_value = None
    a.get_customer_by_identifier.return_value = None
    a.create_customer.return_value = {"ref": "CLI-NEW", "first_name": "", "last_name": ""}
    with patch("shopman.shop.services.customer.get_adapter", return_value=a):
        yield a


class TestCounterStrategy:
    def test_registered_under_pos_channel_ref(self):
        # The strategy registry resolves the configured POS channel (default "pdv").
        assert customer_service._STRATEGIES.get("pdv") is _handle_counter

    def test_phone_existing_customer_returned(self, adapter):
        adapter.get_customer_by_phone.return_value = {"ref": "CLI-1", "first_name": "Ana"}
        result = _handle_counter(_order({"phone": "43999990000", "name": "Ana"}))
        assert result["ref"] == "CLI-1"
        adapter.create_customer.assert_not_called()

    def test_phone_creates_when_absent(self, adapter):
        result = _handle_counter(_order({"phone": "43999990000", "name": "Ana Maria"}))
        assert result["ref"] == "CLI-NEW"
        kwargs = adapter.create_customer.call_args.kwargs
        assert kwargs["first_name"] == "Ana"
        assert kwargs["last_name"] == "Maria"
        assert kwargs["source_system"] == "pdv"

    def test_tax_id_creates_with_identifier(self, adapter):
        result = _handle_counter(_order({"tax_id": "111.444.777-35", "name": "João"}))
        assert result["ref"] == "CLI-NEW"
        # Document normalized to digits and stored as a cpf identifier.
        adapter.get_customer_by_identifier.assert_called_once_with("cpf", "11144477735")
        adapter.create_identifier.assert_called_once_with("CLI-NEW", "cpf", "11144477735", is_primary=True)

    def test_tax_id_existing_customer_returned(self, adapter):
        adapter.get_customer_by_identifier.return_value = {"ref": "CLI-9", "first_name": "João"}
        result = _handle_counter(_order({"document": "11144477735"}))
        assert result["ref"] == "CLI-9"
        adapter.create_customer.assert_not_called()

    def test_no_identifier_is_anonymous(self, adapter):
        with pytest.raises(SkipAnonymous):
            _handle_counter(_order({"name": "Walk-in"}))
        adapter.create_customer.assert_not_called()
