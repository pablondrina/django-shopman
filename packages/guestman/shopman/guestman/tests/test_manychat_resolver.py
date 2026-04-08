"""
Tests for ManychatSubscriberResolver (customers/contrib/manychat/resolver).

Covers (SPEC-004 acceptance criteria):
- Resolução de subscriber por subscriber_id numérico direto
- Resolução por phone E.164 → CustomerIdentifier(PHONE) → MANYCHAT
- Resolução por customer code (MC-...) → Customer → MANYCHAT
- Resolução por email → CustomerIdentifier(EMAIL) → MANYCHAT
- Retorno None quando customer não encontrado
- Retorno None quando customer existe mas sem MANYCHAT identifier
- Retorno None quando customer inativo
"""

from __future__ import annotations

import pytest

from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.contrib.manychat.resolver import ManychatSubscriberResolver
from shopman.guestman.models import Customer


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _enable_db(db):
    """Enable DB access for all tests."""


@pytest.fixture
def customer_with_manychat():
    """Customer with MANYCHAT, PHONE and EMAIL identifiers."""
    customer = Customer.objects.create(
        ref="MC-ABCD1234",
        first_name="Maria",
        last_name="Silva",
        email="maria@example.com",
        phone="+5543999887766",
    )
    CustomerIdentifier.objects.create(
        customer=customer,
        identifier_type=IdentifierType.MANYCHAT,
        identifier_value="987654321",
        is_primary=True,
        source_system="manychat",
    )
    CustomerIdentifier.objects.create(
        customer=customer,
        identifier_type=IdentifierType.PHONE,
        identifier_value="+5543999887766",
        source_system="manychat",
    )
    CustomerIdentifier.objects.create(
        customer=customer,
        identifier_type=IdentifierType.EMAIL,
        identifier_value="maria@example.com",
        source_system="manychat",
    )
    return customer


@pytest.fixture
def customer_without_manychat():
    """Customer with PHONE identifier but no MANYCHAT."""
    customer = Customer.objects.create(
        ref="CUST-NO-MC",
        first_name="João",
        last_name="Oliveira",
        phone="+5543988776655",
    )
    CustomerIdentifier.objects.create(
        customer=customer,
        identifier_type=IdentifierType.PHONE,
        identifier_value="+5543988776655",
        source_system="manual",
    )
    return customer


@pytest.fixture
def inactive_customer():
    """Inactive customer with MANYCHAT identifier."""
    customer = Customer.objects.create(
        ref="MC-INACTIVE",
        first_name="Inactive",
        is_active=False,
    )
    CustomerIdentifier.objects.create(
        customer=customer,
        identifier_type=IdentifierType.MANYCHAT,
        identifier_value="111222333",
        source_system="manychat",
    )
    CustomerIdentifier.objects.create(
        customer=customer,
        identifier_type=IdentifierType.PHONE,
        identifier_value="+5543900000000",
        source_system="manychat",
    )
    return customer


# ═══════════════════════════════════════════════════════════════════
# Tests — Numeric subscriber_id
# ═══════════════════════════════════════════════════════════════════


class TestResolveNumeric:
    """Direct numeric subscriber_id resolution."""

    def test_numeric_string_returns_int(self):
        """Numeric string should be returned as int directly."""
        result = ManychatSubscriberResolver.resolve("123456789")
        assert result == 123456789

    def test_numeric_zero(self):
        """Zero should still resolve."""
        result = ManychatSubscriberResolver.resolve("0")
        assert result == 0


# ═══════════════════════════════════════════════════════════════════
# Tests — Phone resolution
# ═══════════════════════════════════════════════════════════════════


class TestResolveByPhone:
    """Phone E.164 → CustomerIdentifier(PHONE) → Customer → MANYCHAT."""

    def test_phone_resolves_to_manychat_id(self, customer_with_manychat):
        """Phone should resolve to Manychat subscriber_id."""
        result = ManychatSubscriberResolver.resolve("+5543999887766")
        assert result == 987654321

    def test_phone_not_found_returns_none(self):
        """Unknown phone should return None."""
        result = ManychatSubscriberResolver.resolve("+5543000000000")
        assert result is None

    def test_phone_without_manychat_id_returns_none(self, customer_without_manychat):
        """Customer with phone but no MANYCHAT identifier should return None."""
        result = ManychatSubscriberResolver.resolve("+5543988776655")
        assert result is None

    def test_inactive_customer_by_phone_returns_none(self, inactive_customer):
        """Inactive customer should not be resolved."""
        result = ManychatSubscriberResolver.resolve("+5543900000000")
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# Tests — Customer code resolution
# ═══════════════════════════════════════════════════════════════════


class TestResolveByCode:
    """Customer code (MC-...) → Customer → MANYCHAT."""

    def test_code_resolves_to_manychat_id(self, customer_with_manychat):
        """Customer code should resolve to Manychat subscriber_id."""
        result = ManychatSubscriberResolver.resolve("MC-ABCD1234")
        assert result == 987654321

    def test_code_not_found_returns_none(self):
        """Unknown code should return None."""
        result = ManychatSubscriberResolver.resolve("MC-NONEXIST")
        assert result is None

    def test_inactive_customer_by_code_returns_none(self, inactive_customer):
        """Inactive customer should not be resolved by code."""
        result = ManychatSubscriberResolver.resolve("MC-INACTIVE")
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# Tests — Email resolution
# ═══════════════════════════════════════════════════════════════════


class TestResolveByEmail:
    """Email → CustomerIdentifier(EMAIL) → Customer → MANYCHAT."""

    def test_email_resolves_to_manychat_id(self, customer_with_manychat):
        """Email should resolve to Manychat subscriber_id."""
        result = ManychatSubscriberResolver.resolve("maria@example.com")
        assert result == 987654321

    def test_email_case_insensitive(self, customer_with_manychat):
        """Email resolution should be case-insensitive."""
        result = ManychatSubscriberResolver.resolve("Maria@Example.COM")
        assert result == 987654321

    def test_email_not_found_returns_none(self):
        """Unknown email should return None."""
        result = ManychatSubscriberResolver.resolve("unknown@example.com")
        assert result is None

    def test_email_without_manychat_id_returns_none(self, customer_without_manychat):
        """Customer with email but no MANYCHAT identifier should return None."""
        # Add email identifier to customer without manychat
        CustomerIdentifier.objects.create(
            customer=customer_without_manychat,
            identifier_type=IdentifierType.EMAIL,
            identifier_value="joao@example.com",
            source_system="manual",
        )
        result = ManychatSubscriberResolver.resolve("joao@example.com")
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# Tests — Unrecognized recipients
# ═══════════════════════════════════════════════════════════════════


class TestResolveUnrecognized:
    """Unrecognized recipient formats."""

    def test_random_string_returns_none(self):
        """Random string should return None."""
        result = ManychatSubscriberResolver.resolve("some-random-string")
        assert result is None

    def test_empty_string_returns_none(self):
        """Empty string should return None."""
        result = ManychatSubscriberResolver.resolve("")
        assert result is None
