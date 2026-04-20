"""
Tests for shopman.refs.fields.RefField.
"""

from unittest.mock import MagicMock, patch

import pytest

from shopman.refs.fields import RefField
from shopman.refs.registry import _ref_source_registry


# ── Basic CharField compatibility ─────────────────────────────────────────────

class TestRefFieldDefaults:
    def test_is_charfield_subclass(self):
        from django.db.models import CharField
        assert issubclass(RefField, CharField)

    def test_default_max_length(self):
        field = RefField()
        assert field.max_length == 64

    def test_default_db_index(self):
        field = RefField()
        assert field.db_index is True

    def test_ref_type_none_by_default(self):
        field = RefField()
        assert field.ref_type is None

    def test_custom_max_length(self):
        field = RefField(max_length=128)
        assert field.max_length == 128

    def test_custom_db_index_false(self):
        field = RefField(db_index=False)
        assert field.db_index is False

    def test_ref_type_stored(self):
        field = RefField(ref_type="SKU")
        assert field.ref_type == "SKU"


# ── deconstruct ───────────────────────────────────────────────────────────────

class TestRefFieldDeconstruct:
    def test_without_ref_type_deconstructs_as_charfield(self):
        field = RefField()
        field.set_attributes_from_name("ref")
        _, path, _, _ = field.deconstruct()
        assert path == "django.db.models.CharField"

    def test_with_ref_type_deconstructs_as_reffield(self):
        field = RefField(ref_type="SKU")
        field.set_attributes_from_name("sku")
        _, path, _, kwargs = field.deconstruct()
        assert path == "shopman.refs.fields.RefField"
        assert kwargs["ref_type"] == "SKU"

    def test_without_ref_type_no_ref_type_in_kwargs(self):
        field = RefField()
        field.set_attributes_from_name("ref")
        _, _, _, kwargs = field.deconstruct()
        assert "ref_type" not in kwargs

    def test_defaults_appear_in_kwargs(self):
        field = RefField()
        field.set_attributes_from_name("ref")
        _, _, _, kwargs = field.deconstruct()
        assert kwargs["max_length"] == 64
        assert kwargs["db_index"] is True

    def test_custom_max_length_in_kwargs(self):
        field = RefField(max_length=128)
        field.set_attributes_from_name("ref")
        _, _, _, kwargs = field.deconstruct()
        assert kwargs["max_length"] == 128

    def test_zero_migration_churn(self):
        """RefField() and CharField(max_length=64, db_index=True) produce identical deconstruct."""
        from django.db.models import CharField
        ref_field = RefField()
        ref_field.set_attributes_from_name("slug")
        plain = CharField(max_length=64, db_index=True)
        plain.set_attributes_from_name("slug")
        assert ref_field.deconstruct() == plain.deconstruct()


# ── contribute_to_class ───────────────────────────────────────────────────────

class TestRefFieldContributeToClass:
    def _make_mock_cls(self, app_label="myapp", model_name="MyModel"):
        cls = MagicMock()
        cls._meta.app_label = app_label
        cls.__name__ = model_name
        return cls

    def test_with_ref_type_registers_in_source_registry(self):
        field = RefField(ref_type="SKU")
        cls = self._make_mock_cls()
        with patch("shopman.refs.registry._ref_source_registry") as mock_reg:
            field.contribute_to_class(cls, "sku")
        mock_reg.register_lazy.assert_called_once_with(
            app_label_model="myapp.MyModel",
            field_name="sku",
            ref_type="SKU",
        )

    def test_without_ref_type_calls_register_lazy_with_none(self):
        field = RefField()
        cls = self._make_mock_cls()
        with patch("shopman.refs.registry._ref_source_registry") as mock_reg:
            field.contribute_to_class(cls, "ref")
        mock_reg.register_lazy.assert_called_once_with(
            app_label_model="myapp.MyModel",
            field_name="ref",
            ref_type=None,
        )

    def test_without_ref_type_does_not_register_source(self):
        """register_lazy(ref_type=None) is a noop in RefSourceRegistry."""
        field = RefField()
        cls = self._make_mock_cls(app_label="testapp", model_name="Foo")
        _ref_source_registry.clear()
        field.contribute_to_class(cls, "identity_ref")
        assert _ref_source_registry.get_sources_for_type("anything") == []

    def test_with_ref_type_actually_registers(self):
        field = RefField(ref_type="CHANNEL")
        cls = self._make_mock_cls(app_label="orderman", model_name="Session")
        _ref_source_registry.clear()
        field.contribute_to_class(cls, "channel_ref")
        sources = _ref_source_registry.get_sources_for_type("CHANNEL")
        assert ("orderman.Session", "channel_ref") in sources

    def test_multiple_fields_same_ref_type_all_registered(self):
        f1 = RefField(ref_type="SKU")
        f2 = RefField(ref_type="SKU")
        cls1 = self._make_mock_cls("offerman", "Product")
        cls2 = self._make_mock_cls("craftsman", "Ingredient")
        _ref_source_registry.clear()
        f1.contribute_to_class(cls1, "sku")
        f2.contribute_to_class(cls2, "sku")
        sources = _ref_source_registry.get_sources_for_type("SKU")
        assert ("offerman.Product", "sku") in sources
        assert ("craftsman.Ingredient", "sku") in sources

    def teardown_method(self):
        _ref_source_registry.clear()
