"""
Tests for RefBulk — rename, cascade_rename, migrate_target, deactivate_scope, find_orphaned.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from shopman.refs.bulk import RefBulk
from shopman.refs.models import Ref
from shopman.refs.registry import (
    _ref_source_registry,
    clear_ref_types,
    register_ref_type,
)
from shopman.refs.signals import ref_deactivated, ref_renamed
from shopman.refs.types import RefType

pytestmark = pytest.mark.django_db

User = get_user_model()

# ── Test RefTypes ─────────────────────────────────────────────────────────────

SKU = RefType(
    slug="SKU",
    label="SKU",
    scope_keys=(),
    unique_scope="none",
    normalizer="upper_strip",
)

TABLE = RefType(
    slug="TABLE",
    label="Mesa",
    scope_keys=("store_id", "business_date"),
    unique_scope="active",
    normalizer="upper_strip",
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def registry(db):
    clear_ref_types()
    _ref_source_registry.clear()
    register_ref_type(SKU)
    register_ref_type(TABLE)
    yield
    clear_ref_types()
    _ref_source_registry.clear()


@pytest.fixture
def day_scope():
    return {"store_id": 1, "business_date": "2026-04-20"}


def _make_ref(**kwargs) -> Ref:
    defaults = dict(
        ref_type="SKU",
        value="CROISSANT",
        target_type="offerman.Product",
        target_id="1",
        scope={},
    )
    defaults.update(kwargs)
    return Ref.objects.create(**defaults)


# ── RefBulk.rename() ──────────────────────────────────────────────────────────

class TestRename:
    def test_renames_matching_refs(self):
        _make_ref(value="CROISSANT", target_id="1")
        _make_ref(value="CROISSANT", target_id="2")
        count = RefBulk.rename("SKU", "CROISSANT", "CROISSANT-FR", actor="admin")
        assert count == 2
        assert Ref.objects.filter(value="CROISSANT-FR").count() == 2
        assert Ref.objects.filter(value="CROISSANT").count() == 0

    def test_normalizes_old_and_new_value(self):
        _make_ref(value="CROISSANT")
        count = RefBulk.rename("SKU", "  croissant  ", "  croissant-fr  ")
        assert count == 1
        assert Ref.objects.filter(value="CROISSANT-FR").count() == 1

    def test_only_touches_matching_type(self):
        _make_ref(ref_type="SKU", value="ITEM")
        _make_ref(ref_type="TABLE", value="ITEM")
        RefBulk.rename("SKU", "ITEM", "ITEM-NEW")
        assert Ref.objects.filter(ref_type="TABLE", value="ITEM").count() == 1

    def test_scope_filter_limits_rename(self):
        scope_a = {"store_id": 1, "business_date": "2026-04-20"}
        scope_b = {"store_id": 2, "business_date": "2026-04-20"}
        _make_ref(ref_type="TABLE", value="12", scope=scope_a, target_id="1")
        _make_ref(ref_type="TABLE", value="12", scope=scope_b, target_id="2")

        RefBulk.rename("TABLE", "12", "TWELVE", scope=scope_a)

        assert Ref.objects.filter(value="TWELVE", scope__store_id=1).count() == 1
        assert Ref.objects.filter(value="12", scope__store_id=2).count() == 1

    def test_returns_zero_if_no_match(self):
        count = RefBulk.rename("SKU", "GHOST", "GHOST-NEW")
        assert count == 0

    def test_emits_ref_renamed_signal(self):
        _make_ref(value="OLD")
        received = []

        def handler(sender, **kw):
            received.append(kw)

        ref_renamed.connect(handler, weak=False)
        try:
            RefBulk.rename("SKU", "OLD", "NEW", actor="test")
        finally:
            ref_renamed.disconnect(handler)

        assert len(received) == 1
        assert received[0]["ref"].value == "NEW"
        assert received[0]["old_value"] == "OLD"
        assert received[0]["actor"] == "test"

    def test_emits_signal_per_ref(self):
        _make_ref(value="OLD", target_id="1")
        _make_ref(value="OLD", target_id="2")
        received = []

        def handler(sender, **kw):
            received.append(kw)

        ref_renamed.connect(handler, weak=False)
        try:
            RefBulk.rename("SKU", "OLD", "NEW")
        finally:
            ref_renamed.disconnect(handler)
        assert len(received) == 2


# ── RefBulk.cascade_rename() ─────────────────────────────────────────────────

class TestCascadeRename:
    @pytest.fixture(autouse=True)
    def register_user_source(self):
        """Register auth.User.username as a RefField source for SKU type."""
        _ref_source_registry.register("auth.User", "username", "SKU")

    def test_updates_ref_table_and_model_field(self):
        _make_ref(value="OLD-SKU", target_id="10")
        User.objects.create_user(username="OLD-SKU", password="x")

        total = RefBulk.cascade_rename("SKU", "OLD-SKU", "NEW-SKU", actor="admin")

        assert Ref.objects.filter(value="NEW-SKU").count() == 1
        assert Ref.objects.filter(value="OLD-SKU").count() == 0
        assert User.objects.filter(username="NEW-SKU").count() == 1
        assert User.objects.filter(username="OLD-SKU").count() == 0
        assert total == 2  # 1 ref + 1 user

    def test_returns_total_count(self):
        _make_ref(value="X", target_id="1")
        _make_ref(value="X", target_id="2")
        User.objects.create_user(username="X", password="x")

        total = RefBulk.cascade_rename("SKU", "X", "Y")
        assert total == 3  # 2 refs + 1 user

    def test_cascade_with_no_field_sources(self):
        """Works cleanly when no RefField sources registered for type."""
        _ref_source_registry.clear()
        _make_ref(value="A")
        count = RefBulk.cascade_rename("SKU", "A", "B")
        assert count == 1

    def test_ignores_unknown_model_source(self):
        """Bad model label is skipped without error."""
        _ref_source_registry.register("nonexistent.Ghost", "field", "SKU")
        _make_ref(value="V")
        # Should not raise
        count = RefBulk.cascade_rename("SKU", "V", "W")
        assert count == 1  # only the ref

    def test_does_not_apply_scope_filter(self):
        """cascade_rename ignores scope — it's a global rename."""
        scope_a = {"store_id": 1, "business_date": "2026-04-20"}
        scope_b = {"store_id": 2, "business_date": "2026-04-20"}
        _make_ref(ref_type="TABLE", value="12", scope=scope_a, target_id="1")
        _make_ref(ref_type="TABLE", value="12", scope=scope_b, target_id="2")

        total = RefBulk.cascade_rename("TABLE", "12", "TWELVE")
        assert total == 2  # both renamed regardless of scope


# ── RefBulk.migrate_target() ─────────────────────────────────────────────────

class TestMigrateTarget:
    def test_moves_all_refs_to_new_target(self):
        _make_ref(target_type="guestman.Customer", target_id="10")
        _make_ref(ref_type="TABLE", value="A", target_type="guestman.Customer", target_id="10")
        count = RefBulk.migrate_target(
            "guestman.Customer:10", "guestman.Customer:42", actor="merge"
        )
        assert count == 2
        assert Ref.objects.filter(target_id="42").count() == 2
        assert Ref.objects.filter(target_id="10").count() == 0

    def test_migrates_inactive_refs_too(self):
        _make_ref(target_type="guestman.Customer", target_id="10", is_active=False)
        count = RefBulk.migrate_target("guestman.Customer:10", "guestman.Customer:42")
        assert count == 1
        assert Ref.objects.filter(target_id="42", is_active=False).count() == 1

    def test_accepts_model_instances(self, db):
        user1 = User.objects.create_user(username="u1", password="x")
        user2 = User.objects.create_user(username="u2", password="x")
        _make_ref(target_type="auth.User", target_id=str(user1.pk))
        count = RefBulk.migrate_target(user1, user2, actor="merge")
        assert count == 1
        assert Ref.objects.filter(target_id=str(user2.pk)).count() == 1

    def test_returns_zero_if_no_refs(self):
        count = RefBulk.migrate_target("guestman.Customer:999", "guestman.Customer:1")
        assert count == 0

    def test_does_not_move_refs_of_other_targets(self):
        _make_ref(target_type="guestman.Customer", target_id="10")
        _make_ref(target_type="guestman.Customer", target_id="20")
        RefBulk.migrate_target("guestman.Customer:10", "guestman.Customer:99")
        assert Ref.objects.filter(target_id="20").count() == 1
        assert Ref.objects.filter(target_id="10").count() == 0


# ── RefBulk.deactivate_scope() ───────────────────────────────────────────────

class TestDeactivateScope:
    def test_deactivates_matching_refs(self, day_scope):
        _make_ref(ref_type="TABLE", value="1", scope=day_scope, target_id="1")
        _make_ref(ref_type="TABLE", value="2", scope=day_scope, target_id="2")
        count = RefBulk.deactivate_scope("TABLE", day_scope, actor="lifecycle:day_close")
        assert count == 2
        assert Ref.objects.filter(is_active=True).count() == 0

    def test_sets_deactivated_by_and_at(self, day_scope):
        _make_ref(ref_type="TABLE", value="1", scope=day_scope)
        RefBulk.deactivate_scope("TABLE", day_scope, actor="lifecycle:day_close")
        ref = Ref.objects.get(value="1")
        assert ref.deactivated_by == "lifecycle:day_close"
        assert ref.deactivated_at is not None

    def test_scope_isolation(self):
        scope_a = {"store_id": 1, "business_date": "2026-04-20"}
        scope_b = {"store_id": 2, "business_date": "2026-04-20"}
        _make_ref(ref_type="TABLE", value="1", scope=scope_a, target_id="1")
        _make_ref(ref_type="TABLE", value="1", scope=scope_b, target_id="2")

        RefBulk.deactivate_scope("TABLE", scope_a)
        assert Ref.objects.filter(scope__store_id=1, is_active=True).count() == 0
        assert Ref.objects.filter(scope__store_id=2, is_active=True).count() == 1

    def test_ignores_already_inactive(self, day_scope):
        _make_ref(ref_type="TABLE", value="1", scope=day_scope, is_active=False)
        count = RefBulk.deactivate_scope("TABLE", day_scope)
        assert count == 0

    def test_emits_ref_deactivated_per_ref(self, day_scope):
        _make_ref(ref_type="TABLE", value="1", scope=day_scope, target_id="1")
        _make_ref(ref_type="TABLE", value="2", scope=day_scope, target_id="2")
        received = []

        def handler(sender, **kw):
            received.append(kw)

        ref_deactivated.connect(handler, weak=False)
        try:
            RefBulk.deactivate_scope("TABLE", day_scope, actor="test")
        finally:
            ref_deactivated.disconnect(handler)
        assert len(received) == 2
        for kw in received:
            assert kw["ref"].is_active is False
            assert kw["actor"] == "test"


# ── RefBulk.find_orphaned() ──────────────────────────────────────────────────

class TestFindOrphaned:
    def test_live_target_not_orphaned(self, db):
        user = User.objects.create_user(username="live", password="x")
        _make_ref(target_type="auth.User", target_id=str(user.pk))
        orphaned = RefBulk.find_orphaned()
        assert len(orphaned) == 0

    def test_deleted_target_is_orphaned(self, db):
        user = User.objects.create_user(username="gone", password="x")
        pk = user.pk
        _make_ref(target_type="auth.User", target_id=str(pk), value="GONE")
        user.delete()
        orphaned = RefBulk.find_orphaned()
        assert len(orphaned) == 1
        assert orphaned[0].value == "GONE"

    def test_unknown_target_type_is_orphaned(self):
        _make_ref(target_type="nonexistent.Ghost", target_id="1", value="GHOST")
        orphaned = RefBulk.find_orphaned()
        assert len(orphaned) == 1

    def test_mix_of_live_and_dead(self, db):
        live_user = User.objects.create_user(username="live", password="x")
        dead_user = User.objects.create_user(username="dead", password="x")
        dead_pk = dead_user.pk

        _make_ref(target_type="auth.User", target_id=str(live_user.pk), value="LIVE")
        _make_ref(target_type="auth.User", target_id=str(dead_pk), value="DEAD")
        dead_user.delete()

        orphaned = RefBulk.find_orphaned()
        assert len(orphaned) == 1
        assert orphaned[0].value == "DEAD"

    def test_ref_type_filter(self, db):
        user = User.objects.create_user(username="u", password="x")
        pk = user.pk
        _make_ref(ref_type="SKU", target_type="auth.User", target_id=str(pk), value="A")
        _make_ref(ref_type="TABLE", target_type="auth.User", target_id=str(pk), value="B")
        user.delete()

        orphaned_sku = RefBulk.find_orphaned(ref_type="SKU")
        assert len(orphaned_sku) == 1
        assert orphaned_sku[0].ref_type == "SKU"

    def test_no_refs_returns_empty(self):
        assert RefBulk.find_orphaned() == []
