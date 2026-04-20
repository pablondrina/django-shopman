"""
Tests for orderman contrib/refs.

Tests the thin-wrapper API (attach_ref, resolve_ref, etc.) and orderman-specific
RefTypes, using shopman.refs as the underlying implementation.
"""

import uuid
from datetime import date

from django.test import TestCase
from shopman.refs.exceptions import RefConflict, RefScopeInvalid
from shopman.refs.models import Ref
from shopman.refs.registry import clear_ref_types, get_ref_type, register_ref_type
from shopman.orderman.contrib.refs.services import (
    attach_ref,
    deactivate_refs,
    get_refs_for_target,
    on_session_committed,
    resolve_ref,
)
from shopman.orderman.contrib.refs.types import (
    DEFAULT_REF_TYPES,
    EXTERNAL_ORDER,
    ORDER_REF,
    POS_TAB,
    POS_TABLE,
)


# ── Type definitions ──────────────────────────────────────────────────────────

class TypeDefinitionTests(TestCase):
    def test_pos_table_attributes(self):
        assert POS_TABLE.slug == "POS_TABLE"
        assert POS_TABLE.allowed_targets == ("orderman.Session",)
        assert POS_TABLE.scope_keys == ("store_id", "business_date")
        assert POS_TABLE.unique_scope == "active"

    def test_pos_tab_attributes(self):
        assert POS_TAB.slug == "POS_TAB"
        assert POS_TAB.allowed_targets == ("orderman.Session",)

    def test_order_ref_attributes(self):
        assert ORDER_REF.slug == "ORDER_REF"
        assert ORDER_REF.allowed_targets == ("orderman.Order",)
        assert ORDER_REF.unique_scope == "all"

    def test_external_order_attributes(self):
        assert EXTERNAL_ORDER.slug == "EXTERNAL_ORDER"
        assert EXTERNAL_ORDER.allowed_targets == ("orderman.Order",)

    def test_default_ref_types_list(self):
        assert len(DEFAULT_REF_TYPES) == 4
        slugs = {rt.slug for rt in DEFAULT_REF_TYPES}
        assert slugs == {"POS_TABLE", "POS_TAB", "ORDER_REF", "EXTERNAL_ORDER"}


# ── attach_ref ────────────────────────────────────────────────────────────────

class AttachRefTests(TestCase):
    def setUp(self):
        clear_ref_types()
        register_ref_type(POS_TABLE)
        register_ref_type(POS_TAB)
        Ref.objects.all().delete()

    def tearDown(self):
        clear_ref_types()

    def test_attach_creates_ref(self):
        session_id = 47
        scope = {"store_id": 1, "business_date": str(date.today())}

        ref = attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)

        assert ref.ref_type == "POS_TABLE"
        assert ref.target_type == "orderman.Session"
        assert ref.target_id == str(session_id)
        assert ref.value == "12"
        assert ref.is_active is True

    def test_attach_normalizes_value(self):
        scope = {"store_id": 1, "business_date": str(date.today())}
        ref = attach_ref("SESSION", 48, "POS_TABLE", "  mesa 12  ", scope)
        assert ref.value == "MESA 12"

    def test_attach_idempotent_same_target(self):
        session_id = 49
        scope = {"store_id": 1, "business_date": str(date.today())}

        ref1 = attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)
        ref2 = attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)

        assert ref1.id == ref2.id
        assert Ref.objects.count() == 1

    def test_attach_conflict_different_target(self):
        scope = {"store_id": 1, "business_date": str(date.today())}
        attach_ref("SESSION", 50, "POS_TABLE", "12", scope)

        with self.assertRaises(RefConflict):
            attach_ref("SESSION", 51, "POS_TABLE", "12", scope)

    def test_attach_invalid_scope_raises(self):
        with self.assertRaises(RefScopeInvalid):
            attach_ref("SESSION", 52, "POS_TABLE", "12", {"store_id": 1})  # missing business_date

    def test_attach_unknown_ref_type_raises(self):
        with self.assertRaises(KeyError):
            attach_ref("SESSION", 53, "UNKNOWN_TYPE", "12", {})

    def test_attach_with_uuid_target_id(self):
        uid = uuid.uuid4()
        scope = {"store_id": 1, "business_date": str(date.today())}
        ref = attach_ref("SESSION", uid, "POS_TABLE", "15", scope)
        assert ref.target_id == str(uid)


# ── resolve_ref ───────────────────────────────────────────────────────────────

class ResolveRefTests(TestCase):
    def setUp(self):
        clear_ref_types()
        register_ref_type(POS_TABLE)
        Ref.objects.all().delete()

    def tearDown(self):
        clear_ref_types()

    def test_resolve_finds_active_ref(self):
        session_id = 100
        scope = {"store_id": 1, "business_date": str(date.today())}

        attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)
        result = resolve_ref("POS_TABLE", "12", scope)

        assert result is not None
        kind, target_id = result
        assert kind == "SESSION"
        assert target_id == str(session_id)

    def test_resolve_returns_none_for_inactive(self):
        session_id = 101
        scope = {"store_id": 1, "business_date": str(date.today())}

        ref = attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)
        Ref.objects.filter(pk=ref.pk).update(is_active=False)

        assert resolve_ref("POS_TABLE", "12", scope) is None

    def test_resolve_returns_none_for_different_scope(self):
        scope1 = {"store_id": 1, "business_date": str(date.today())}
        scope2 = {"store_id": 2, "business_date": str(date.today())}

        attach_ref("SESSION", 102, "POS_TABLE", "12", scope1)
        assert resolve_ref("POS_TABLE", "12", scope2) is None

    def test_resolve_normalizes_value(self):
        session_id = 103
        scope = {"store_id": 1, "business_date": str(date.today())}

        attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)
        result = resolve_ref("POS_TABLE", "  12  ", scope)
        assert result is not None


# ── deactivate_refs ───────────────────────────────────────────────────────────

class DeactivateRefsTests(TestCase):
    def setUp(self):
        clear_ref_types()
        register_ref_type(POS_TABLE)
        register_ref_type(POS_TAB)
        Ref.objects.all().delete()

    def tearDown(self):
        clear_ref_types()

    def test_deactivate_all(self):
        session_id = 200
        scope = {"store_id": 1, "business_date": str(date.today())}

        attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)
        attach_ref("SESSION", session_id, "POS_TAB", "A1", scope)

        count = deactivate_refs("SESSION", session_id)

        assert count == 2
        assert Ref.objects.filter(target_id=str(session_id), is_active=True).count() == 0

    def test_deactivate_specific_types(self):
        session_id = 201
        scope = {"store_id": 1, "business_date": str(date.today())}

        attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)
        attach_ref("SESSION", session_id, "POS_TAB", "A1", scope)

        count = deactivate_refs("SESSION", session_id, ref_type_slugs=["POS_TABLE"])

        assert count == 1
        assert Ref.objects.filter(target_id=str(session_id), ref_type="POS_TABLE", is_active=True).count() == 0
        assert Ref.objects.filter(target_id=str(session_id), ref_type="POS_TAB", is_active=True).count() == 1


# ── get_refs_for_target ───────────────────────────────────────────────────────

class GetRefsForTargetTests(TestCase):
    def setUp(self):
        clear_ref_types()
        register_ref_type(POS_TABLE)
        register_ref_type(POS_TAB)
        Ref.objects.all().delete()

    def tearDown(self):
        clear_ref_types()

    def test_returns_active_refs(self):
        session_id = 300
        scope = {"store_id": 1, "business_date": str(date.today())}

        attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)
        attach_ref("SESSION", session_id, "POS_TAB", "A1", scope)

        refs = get_refs_for_target("SESSION", session_id)
        assert len(refs) == 2

    def test_excludes_inactive_by_default(self):
        session_id = 301
        scope = {"store_id": 1, "business_date": str(date.today())}

        ref = attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)
        Ref.objects.filter(pk=ref.pk).update(is_active=False)

        assert len(get_refs_for_target("SESSION", session_id, active_only=True)) == 0
        assert len(get_refs_for_target("SESSION", session_id, active_only=False)) == 1


# ── on_session_committed ──────────────────────────────────────────────────────

class OnSessionCommittedTests(TestCase):
    def setUp(self):
        clear_ref_types()
        register_ref_type(POS_TABLE)
        register_ref_type(POS_TAB)
        Ref.objects.all().delete()

    def tearDown(self):
        clear_ref_types()

    def test_session_refs_transfer_to_order(self):
        session_id = 400
        order_id = 1000
        scope = {"store_id": 1, "business_date": str(date.today())}

        attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)
        on_session_committed(session_id, order_id)

        # Ref is now on the Order (transfer changes target, does not duplicate)
        order_ref = Ref.objects.filter(
            ref_type="POS_TABLE",
            target_type="orderman.Order",
            target_id=str(order_id),
            is_active=True,
        ).first()
        assert order_ref is not None
        assert order_ref.value == "12"

        # Session no longer has this ref
        assert Ref.objects.filter(
            target_type="orderman.Session",
            target_id=str(session_id),
        ).count() == 0

    def test_multiple_refs_all_transfer(self):
        session_id = 401
        order_id = 1001
        scope = {"store_id": 1, "business_date": str(date.today())}

        attach_ref("SESSION", session_id, "POS_TABLE", "5", scope)
        attach_ref("SESSION", session_id, "POS_TAB", "B2", scope)

        on_session_committed(session_id, order_id)

        assert Ref.objects.filter(
            target_type="orderman.Order",
            target_id=str(order_id),
            is_active=True,
        ).count() == 2

    def test_session_without_refs_is_noop(self):
        on_session_committed(999, 9999)  # no refs — should not raise
