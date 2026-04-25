"""
Tests for shopman.refs.generators — all 5 generators + generate_value().
"""

import pytest

from shopman.refs.generators import (
    AlphaNumericGenerator,
    ChecksumGenerator,
    DateSequenceGenerator,
    SequenceGenerator,
    ShortUUIDGenerator,
    generate_value,
)
from shopman.refs.registry import clear_ref_types, register_ref_type
from shopman.refs.types import RefType

pytestmark = pytest.mark.django_db


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_ref_type(**kwargs) -> RefType:
    defaults = {
        "slug": "TEST_REF",
        "label": "Test",
        "generator": "sequence",
        "generator_format": "{value}",
    }
    defaults.update(kwargs)
    return RefType(**defaults)


SCOPE_A = {"store_id": 1, "business_date": "2026-04-20"}
SCOPE_B = {"store_id": 2, "business_date": "2026-04-20"}


# ── SequenceGenerator ─────────────────────────────────────────────────────────

class TestSequenceGenerator:
    def setup_method(self):
        self.gen = SequenceGenerator()

    def _rt(self, fmt="{value}"):
        return make_ref_type(slug="SEQ_TEST", generator="sequence", generator_format=fmt)

    def test_starts_at_one(self):
        rt = self._rt()
        assert self.gen.next(rt, SCOPE_A) == "1"

    def test_increments_per_call(self):
        rt = self._rt()
        vals = [self.gen.next(rt, SCOPE_A) for _ in range(3)]
        assert vals == ["1", "2", "3"]

    def test_separate_scopes_are_independent(self):
        rt = self._rt()
        assert self.gen.next(rt, SCOPE_A) == "1"
        assert self.gen.next(rt, SCOPE_B) == "1"

    def test_custom_format_with_zero_padding(self):
        rt = self._rt(fmt="T-{value:03d}")
        assert self.gen.next(rt, SCOPE_A) == "T-001"
        assert self.gen.next(rt, SCOPE_A) == "T-002"


# ── DateSequenceGenerator ─────────────────────────────────────────────────────

class TestDateSequenceGenerator:
    def setup_method(self):
        self.gen = DateSequenceGenerator()

    def _rt(self, fmt="{value}"):
        return make_ref_type(slug="DATE_SEQ_TEST", generator="date_sequence", generator_format=fmt)

    def test_starts_at_one(self):
        rt = self._rt()
        assert self.gen.next(rt, SCOPE_A) == "1"

    def test_different_dates_are_independent(self):
        rt = self._rt()
        scope_today = {"store_id": 1, "business_date": "2026-04-20"}
        scope_tomorrow = {"store_id": 1, "business_date": "2026-04-21"}
        assert self.gen.next(rt, scope_today) == "1"
        assert self.gen.next(rt, scope_tomorrow) == "1"

    def test_same_date_increments(self):
        rt = self._rt()
        assert self.gen.next(rt, SCOPE_A) == "1"
        assert self.gen.next(rt, SCOPE_A) == "2"

    def test_format_applied(self):
        rt = self._rt(fmt="T-{value:03d}")
        assert self.gen.next(rt, SCOPE_A) == "T-001"


# ── AlphaNumericGenerator ─────────────────────────────────────────────────────

class TestAlphaNumericGenerator:
    def setup_method(self):
        self.gen = AlphaNumericGenerator()

    def _rt(self, fmt="{code}"):
        return make_ref_type(slug="AN_TEST", generator="alpha_numeric", generator_format=fmt)

    def test_first_code_is_aa00(self):
        assert self.gen._encode(0) == "AA00"

    def test_second_code_is_aa01(self):
        assert self.gen._encode(1) == "AA01"

    def test_rollover_digits_before_letters(self):
        # 100 sequences fill 10×10 digit combos for one letter pair → next letter
        assert self.gen._encode(100) == "AB00"

    def test_no_i_or_o_in_letters(self):
        assert "I" not in self.gen.LETTERS
        assert "O" not in self.gen.LETTERS

    def test_alphabet_length(self):
        assert len(self.gen.LETTERS) == 24

    def test_total_combinations(self):
        L, D = len(self.gen.LETTERS), len(self.gen.DIGITS)
        assert L * L * D * D == 57600

    def test_next_returns_4_chars(self):
        rt = self._rt()
        code = self.gen.next(rt, SCOPE_A)
        assert len(code) == 4

    def test_next_increments(self):
        rt = self._rt()
        c1 = self.gen.next(rt, SCOPE_A)
        c2 = self.gen.next(rt, SCOPE_A)
        assert c1 != c2

    def test_independent_scopes(self):
        rt = self._rt()
        assert self.gen.next(rt, SCOPE_A) == "AA00"
        assert self.gen.next(rt, SCOPE_B) == "AA00"

    def test_format_string_with_date_and_prefix(self):
        rt = make_ref_type(
            slug="ORDER_REF",
            generator="alpha_numeric",
            generator_format="{channel_ref}-{date:%y%m%d}-{code}",
        )
        scope = {"channel_ref": "POS", "business_date": "2026-04-20"}
        val = self.gen.next(rt, scope)
        assert val == "POS-260420-AA00"


# ── ShortUUIDGenerator ────────────────────────────────────────────────────────

class TestShortUUIDGenerator:
    def setup_method(self):
        self.gen = ShortUUIDGenerator()

    def _rt(self, fmt="{code}"):
        return make_ref_type(slug="UUID_TEST", generator="short_uuid", generator_format=fmt)

    def test_default_length_is_8(self):
        rt = self._rt()
        code = self.gen.next(rt, SCOPE_A)
        assert len(code) == 8

    def test_custom_length_via_format(self):
        rt = self._rt(fmt="{code:6}")
        code = self.gen.next(rt, SCOPE_A)
        assert len(code) == 6

    def test_alphabet_is_uppercase_alphanumeric_no_io(self):
        rt = self._rt()
        for _ in range(20):
            code = self.gen.next(rt, SCOPE_A)
            assert code.isalnum()
            assert code == code.upper()
            assert "I" not in code
            assert "O" not in code

    def test_two_calls_are_unique(self):
        rt = self._rt()
        codes = {self.gen.next(rt, SCOPE_A) for _ in range(50)}
        assert len(codes) > 40  # practically always unique


# ── ChecksumGenerator ─────────────────────────────────────────────────────────

class TestChecksumGenerator:
    def setup_method(self):
        self.gen = ChecksumGenerator()

    def _rt(self, fmt="{code}"):
        return make_ref_type(slug="CK_TEST", generator="checksum", generator_format=fmt)

    def test_first_value_has_check_digit(self):
        rt = self._rt()
        val = self.gen.next(rt, SCOPE_A)
        assert len(val) >= 2
        assert val[:-1].isdigit()
        assert val[-1].isdigit()

    def test_check_digit_varies_with_input(self):
        digits = [self.gen._luhn_check_digit(n) for n in range(1, 11)]
        assert len(set(digits)) > 1

    def test_increments_per_call(self):
        rt = self._rt()
        v1 = self.gen.next(rt, SCOPE_A)
        v2 = self.gen.next(rt, SCOPE_A)
        assert v1 != v2


# ── generate_value() ──────────────────────────────────────────────────────────

class TestGenerateValue:
    def setup_method(self):
        clear_ref_types()

    def teardown_method(self):
        clear_ref_types()

    def test_generate_value_sequence(self):
        rt = RefType(slug="TICKET", label="Ticket", generator="sequence", generator_format="T-{value:03d}")
        register_ref_type(rt)
        val = generate_value("TICKET", scope=SCOPE_A)
        assert val == "T-001"

    def test_generate_value_alpha_numeric(self):
        rt = RefType(slug="ORDER_CODE", label="Order Code", generator="alpha_numeric", generator_format="{code}")
        register_ref_type(rt)
        val = generate_value("ORDER_CODE", scope=SCOPE_A)
        assert val == "AA00"

    def test_generate_value_unknown_type_raises(self):
        with pytest.raises(LookupError, match="not registered"):
            generate_value("NONEXISTENT", scope={})

    def test_generate_value_no_generator_raises(self):
        rt = RefType(slug="PLAIN", label="Plain", generator=None)
        register_ref_type(rt)
        with pytest.raises(LookupError, match="no generator"):
            generate_value("PLAIN", scope={})

    def test_generate_value_scope_none_defaults_to_empty(self):
        rt = RefType(slug="GLOBAL_SEQ", label="Global", generator="sequence", generator_format="{value}")
        register_ref_type(rt)
        v1 = generate_value("GLOBAL_SEQ")
        v2 = generate_value("GLOBAL_SEQ")
        assert v1 == "1"
        assert v2 == "2"
