"""
Tests for RefType dataclass and RefTypeRegistry.
"""

import pytest

from shopman.refs.exceptions import RefError
from shopman.refs.registry import RefTypeRegistry, clear_ref_types, get_ref_type, register_ref_type
from shopman.refs.types import RefType


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_registry():
    """Isolate each test from global registry state."""
    clear_ref_types()
    yield
    clear_ref_types()


MESA = RefType(slug="POS_TABLE", label="Mesa", scope_keys=("store_id", "business_date"))
TICKET = RefType(
    slug="PICKUP_TICKET",
    label="Senha de Retirada",
    allowed_targets=("orderman.Order",),
    scope_keys=("store_id", "business_date"),
    unique_scope="all",
    normalizer="upper_strip",
    generator="date_sequence",
    generator_format="T-{value:03d}",
)


# ── RefType validation ────────────────────────────────────────────────────────

class TestRefTypeValidation:
    def test_empty_slug_raises(self):
        with pytest.raises(ValueError, match="slug cannot be empty"):
            RefType(slug="", label="X")

    def test_slug_with_spaces_raises(self):
        with pytest.raises(ValueError, match="alphanumeric with underscores"):
            RefType(slug="POS TABLE", label="X")

    def test_slug_with_hyphens_raises(self):
        with pytest.raises(ValueError, match="alphanumeric with underscores"):
            RefType(slug="POS-TABLE", label="X")

    def test_valid_slug_accepted(self):
        rt = RefType(slug="POS_TABLE", label="Mesa")
        assert rt.slug == "POS_TABLE"

    def test_frozen_prevents_mutation(self):
        rt = RefType(slug="POS_TABLE", label="Mesa")
        with pytest.raises((AttributeError, TypeError)):
            rt.slug = "OTHER"

    def test_defaults(self):
        rt = RefType(slug="SIMPLE", label="Simple")
        assert rt.allowed_targets == ("*",)
        assert rt.scope_keys == ()
        assert rt.unique_scope == "active"
        assert rt.normalizer == "upper_strip"
        assert rt.validator is None
        assert rt.generator is None
        assert rt.on_deactivate == "nothing"

    def test_invalid_unique_scope_raises(self):
        with pytest.raises(ValueError, match="unique_scope"):
            RefType(slug="BAD", label="Bad", unique_scope="invalid")


# ── RefTypeRegistry ───────────────────────────────────────────────────────────

class TestRefTypeRegistry:
    def test_register_and_get(self):
        register_ref_type(MESA)
        result = get_ref_type("POS_TABLE")
        assert result == MESA

    def test_get_unknown_returns_none(self):
        assert get_ref_type("DOES_NOT_EXIST") is None

    def test_duplicate_slug_raises(self):
        register_ref_type(MESA)
        with pytest.raises(ValueError, match="already registered"):
            register_ref_type(MESA)

    def test_get_all_returns_registered(self):
        from shopman.refs.registry import get_all_ref_types
        register_ref_type(MESA)
        register_ref_type(TICKET)
        all_types = get_all_ref_types()
        slugs = {rt.slug for rt in all_types}
        assert "POS_TABLE" in slugs
        assert "PICKUP_TICKET" in slugs

    def test_get_all_empty_after_clear(self):
        from shopman.refs.registry import get_all_ref_types
        register_ref_type(MESA)
        clear_ref_types()
        assert get_all_ref_types() == []

    def test_registry_instance_is_independent(self):
        """Two RefTypeRegistry instances don't share state."""
        r1 = RefTypeRegistry()
        r2 = RefTypeRegistry()
        r1.register(MESA)
        assert r2.get("POS_TABLE") is None

    def test_clear_resets_state(self):
        register_ref_type(MESA)
        clear_ref_types()
        assert get_ref_type("POS_TABLE") is None
