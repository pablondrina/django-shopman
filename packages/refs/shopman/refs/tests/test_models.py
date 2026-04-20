"""
Tests for Ref and RefSequence models.
"""

import uuid

import pytest

from shopman.refs.models import Ref, RefSequence

pytestmark = pytest.mark.django_db


# ── Ref model ─────────────────────────────────────────────────────────────────

class TestRefModel:
    def test_create_basic_ref(self):
        ref = Ref.objects.create(
            ref_type="POS_TABLE",
            value="12",
            target_type="orderman.Session",
            target_id="47",
            scope={"store_id": 1, "business_date": "2026-04-20"},
            actor="system",
        )
        assert ref.pk is not None
        assert isinstance(ref.pk, uuid.UUID)
        assert ref.is_active is True
        assert ref.deactivated_at is None
        assert ref.deactivated_by == ""
        assert ref.metadata == {}

    def test_ref_str(self):
        ref = Ref(
            ref_type="POS_TABLE",
            value="12",
            target_type="orderman.Session",
            target_id="47",
        )
        assert "POS_TABLE:12" in str(ref)
        assert "active" in str(ref)

    def test_inactive_ref_str(self):
        ref = Ref(
            ref_type="POS_TABLE",
            value="12",
            target_type="orderman.Session",
            target_id="47",
            is_active=False,
        )
        assert "inactive" in str(ref)

    def test_scope_defaults_to_empty_dict(self):
        ref = Ref.objects.create(
            ref_type="SKU",
            value="CROISSANT",
            target_type="offerman.Product",
            target_id="5",
        )
        assert ref.scope == {}

    def test_multiple_refs_same_type_different_values(self):
        Ref.objects.create(ref_type="POS_TABLE", value="1", target_type="orderman.Session", target_id="10")
        Ref.objects.create(ref_type="POS_TABLE", value="2", target_type="orderman.Session", target_id="11")
        assert Ref.objects.filter(ref_type="POS_TABLE").count() == 2

    def test_filter_active(self):
        Ref.objects.create(ref_type="POS_TABLE", value="1", target_type="orderman.Session", target_id="10", is_active=True)
        Ref.objects.create(ref_type="POS_TABLE", value="2", target_type="orderman.Session", target_id="11", is_active=False)
        active = Ref.objects.filter(ref_type="POS_TABLE", is_active=True)
        assert active.count() == 1
        assert active.first().value == "1"

    def test_metadata_stores_arbitrary_data(self):
        ref = Ref.objects.create(
            ref_type="EXTERNAL_ORDER",
            value="iF-abc123",
            target_type="orderman.Order",
            target_id="99",
            metadata={"platform": "ifood", "merchant_id": "M42"},
        )
        saved = Ref.objects.get(pk=ref.pk)
        assert saved.metadata["platform"] == "ifood"

    def test_uuid_primary_key_generated(self):
        r1 = Ref.objects.create(ref_type="X", value="a", target_type="t", target_id="1")
        r2 = Ref.objects.create(ref_type="X", value="b", target_type="t", target_id="2")
        assert r1.pk != r2.pk


# ── RefSequence model ─────────────────────────────────────────────────────────

class TestRefSequenceModel:
    def test_create_sequence(self):
        seq = RefSequence.objects.create(
            sequence_name="PICKUP_TICKET",
            scope_hash="abc123",
            scope={"store_id": 1, "business_date": "2026-04-20"},
            last_value=0,
        )
        assert seq.pk is not None
        assert seq.last_value == 0

    def test_unique_constraint_on_name_and_hash(self):
        from django.db import IntegrityError
        RefSequence.objects.create(sequence_name="SEQ", scope_hash="h1", scope={})
        with pytest.raises(IntegrityError):
            RefSequence.objects.create(sequence_name="SEQ", scope_hash="h1", scope={})

    def test_same_name_different_hash_allowed(self):
        RefSequence.objects.create(sequence_name="SEQ", scope_hash="h1", scope={"d": "2026-04-20"})
        RefSequence.objects.create(sequence_name="SEQ", scope_hash="h2", scope={"d": "2026-04-21"})
        assert RefSequence.objects.filter(sequence_name="SEQ").count() == 2

    def test_last_value_can_be_incremented(self):
        seq = RefSequence.objects.create(sequence_name="S", scope_hash="x", scope={}, last_value=5)
        seq.last_value = 6
        seq.save(update_fields=["last_value"])
        reloaded = RefSequence.objects.get(pk=seq.pk)
        assert reloaded.last_value == 6

    def test_str(self):
        seq = RefSequence(sequence_name="SEQ", scope_hash="abc", last_value=42)
        assert "SEQ" in str(seq)
        assert "42" in str(seq)
