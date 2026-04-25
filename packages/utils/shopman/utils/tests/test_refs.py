"""Tests for optional ref field helpers."""

from django.db import models

from shopman.utils.refs import FallbackRefField, RefField


def test_ref_field_accepts_ref_type_and_deconstructs_as_charfield():
    field = RefField(ref_type="SKU")

    assert getattr(field, "ref_type", None) == "SKU"
    assert field.max_length == 64
    assert field.db_index is True
    assert field.deconstruct()[1] == "django.db.models.CharField"


def test_fallback_ref_field_is_plain_charfield_compatible():
    field = FallbackRefField(ref_type="ORDER_REF", max_length=50, db_index=False)

    assert isinstance(field, models.CharField)
    assert field.ref_type == "ORDER_REF"
    assert field.max_length == 50
    assert field.db_index is False
    assert field.deconstruct()[1] == "django.db.models.CharField"
