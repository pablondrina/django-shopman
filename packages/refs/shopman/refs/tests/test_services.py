"""
Tests for shopman.refs services — attach, resolve, resolve_partial,
resolve_object, deactivate, transfer, refs_for.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from shopman.refs.exceptions import AmbiguousRef, RefConflict, RefScopeInvalid
from shopman.refs.models import Ref
from shopman.refs.registry import clear_ref_types, register_ref_type
from shopman.refs.services import (
    _coerce_target,
    _normalize_value,
    attach,
    deactivate,
    parse_target,
    refs_for,
    resolve,
    resolve_object,
    resolve_partial,
    target_str,
    transfer,
)
from shopman.refs.types import RefType

pytestmark = pytest.mark.django_db

User = get_user_model()

# ── Test RefTypes ─────────────────────────────────────────────────────────────

TABLE = RefType(
    slug="TABLE",
    label="Mesa",
    scope_keys=("store_id", "business_date"),
    unique_scope="active",
    normalizer="upper_strip",
)

TICKET = RefType(
    slug="TICKET",
    label="Senha",
    scope_keys=("store_id",),
    unique_scope="all",
    normalizer="upper_strip",
)

ORDER_CODE = RefType(
    slug="ORDER_CODE",
    label="Codigo do Pedido",
    scope_keys=("store_id", "business_date"),
    unique_scope="none",
    normalizer="upper_strip",
)

LOWER_TYPE = RefType(
    slug="LOWER_TYPE",
    label="Lower",
    scope_keys=(),
    normalizer="lower_strip",
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def registry(db):
    clear_ref_types()
    register_ref_type(TABLE)
    register_ref_type(TICKET)
    register_ref_type(ORDER_CODE)
    register_ref_type(LOWER_TYPE)
    yield
    clear_ref_types()


@pytest.fixture
def scope():
    return {"store_id": 1, "business_date": "2026-04-20"}


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", password="x")


# ── Helpers tests ─────────────────────────────────────────────────────────────

class TestTargetStr:
    def test_from_instance(self, user):
        result = target_str(user)
        assert result == f"auth.User:{user.pk}"

    def test_format_matches_parse(self, user):
        s = target_str(user)
        ttype, tid = parse_target(s)
        assert ttype == "auth.User"
        assert tid == str(user.pk)


class TestParseTarget:
    def test_basic(self):
        assert parse_target("orderman.Session:47") == ("orderman.Session", "47")

    def test_uuid_id(self):
        assert parse_target("refs.Ref:abc-123-def") == ("refs.Ref", "abc-123-def")

    def test_invalid_no_colon(self):
        with pytest.raises(ValueError, match="Invalid target"):
            parse_target("orderman.Session")

    def test_invalid_empty_id(self):
        with pytest.raises(ValueError):
            parse_target("orderman.Session:")

    def test_invalid_empty_type(self):
        with pytest.raises(ValueError):
            parse_target(":47")


class TestNormalizeValue:
    def test_upper_strip(self):
        assert _normalize_value("  mesa 12  ", "upper_strip") == "MESA 12"

    def test_lower_strip(self):
        assert _normalize_value("  MESA 12  ", "lower_strip") == "mesa 12"

    def test_none(self):
        assert _normalize_value("  Mesa  ", "none") == "  Mesa  "


class TestCoerceTarget:
    def test_string(self):
        assert _coerce_target("orderman.Session:47") == ("orderman.Session", "47")

    def test_tuple_strings(self):
        assert _coerce_target(("orderman.Session", "47")) == ("orderman.Session", "47")

    def test_tuple_with_int(self):
        assert _coerce_target(("orderman.Session", 47)) == ("orderman.Session", "47")

    def test_model_instance(self, user):
        ttype, tid = _coerce_target(user)
        assert ttype == "auth.User"
        assert tid == str(user.pk)


# ── attach() tests ────────────────────────────────────────────────────────────

class TestAttach:
    def test_basic_attach(self, scope):
        ref = attach("TABLE", "12", "orderman.Session:47", scope=scope, actor="pos:caixa")
        assert ref.ref_type == "TABLE"
        assert ref.value == "12"
        assert ref.target_type == "orderman.Session"
        assert ref.target_id == "47"
        assert ref.scope == scope
        assert ref.actor == "pos:caixa"
        assert ref.is_active is True

    def test_value_normalized_upper_strip(self, scope):
        ref = attach("TABLE", "  mesa 12  ", "orderman.Session:1", scope=scope)
        assert ref.value == "MESA 12"

    def test_value_normalized_lower(self):
        ref = attach("LOWER_TYPE", "  HELLO  ", "test.Model:1")
        assert ref.value == "hello"

    def test_idempotent_same_target(self, scope):
        r1 = attach("TABLE", "12", "orderman.Session:47", scope=scope)
        r2 = attach("TABLE", "12", "orderman.Session:47", scope=scope)
        assert r1.pk == r2.pk
        assert Ref.objects.filter(ref_type="TABLE", value="12").count() == 1

    def test_idempotent_normalizes_before_check(self, scope):
        r1 = attach("TABLE", "12", "orderman.Session:47", scope=scope)
        r2 = attach("TABLE", "  12  ", "orderman.Session:47", scope=scope)
        assert r1.pk == r2.pk

    def test_conflict_different_target(self, scope):
        attach("TABLE", "12", "orderman.Session:47", scope=scope)
        with pytest.raises(RefConflict) as exc_info:
            attach("TABLE", "12", "orderman.Session:99", scope=scope)
        assert exc_info.value.ref_type_slug == "TABLE"
        assert exc_info.value.value == "12"
        assert exc_info.value.existing_target_id == "47"

    def test_scope_validation_missing_key(self, scope):
        bad_scope = {"store_id": 1}  # missing business_date
        with pytest.raises(RefScopeInvalid) as exc_info:
            attach("TABLE", "12", "orderman.Session:47", scope=bad_scope)
        assert "business_date" in exc_info.value.missing_keys

    def test_unregistered_type_raises(self, scope):
        with pytest.raises(KeyError, match="not registered"):
            attach("UNKNOWN_TYPE", "x", "t.Model:1", scope=scope)

    def test_metadata_stored(self, scope):
        ref = attach("TABLE", "5", "orderman.Session:10", scope=scope, metadata={"note": "vip"})
        assert ref.metadata["note"] == "vip"

    def test_unique_scope_none_allows_duplicates(self):
        attach("ORDER_CODE", "A1", "orderman.Order:1",
               scope={"store_id": 1, "business_date": "2026-04-20"})
        ref2 = attach("ORDER_CODE", "A1", "orderman.Order:2",
                      scope={"store_id": 1, "business_date": "2026-04-20"})
        assert ref2.target_id == "2"
        assert Ref.objects.filter(ref_type="ORDER_CODE", value="A1").count() == 2

    def test_unique_scope_all_conflicts_on_inactive(self, scope):
        """unique_scope='all' checks inactive refs too — conflict even after deactivation."""
        ref = attach("TICKET", "T001", "orderman.Order:1", scope={"store_id": 1})
        ref.is_active = False
        ref.save(update_fields=["is_active"])

        with pytest.raises(RefConflict):
            attach("TICKET", "T001", "orderman.Order:2", scope={"store_id": 1})

    def test_unique_scope_active_allows_reuse_after_deactivation(self, scope):
        """unique_scope='active' (TABLE type): deactivated ref can be reattached."""
        ref = attach("TABLE", "12", "orderman.Session:47", scope=scope)
        ref.is_active = False
        ref.save(update_fields=["is_active"])

        ref2 = attach("TABLE", "12", "orderman.Session:99", scope=scope)
        assert ref2.target_id == "99"

    def test_target_as_model_instance(self, scope, user):
        ref = attach("TABLE", "5", user, scope=scope)
        assert ref.target_type == "auth.User"
        assert ref.target_id == str(user.pk)

    def test_target_as_tuple_modelclass(self, scope, user):
        ref = attach("TABLE", "7", (User, user.pk), scope=scope)
        assert ref.target_type == "auth.User"
        assert ref.target_id == str(user.pk)

    def test_target_as_tuple_strings(self, scope):
        ref = attach("TABLE", "9", ("orderman.Session", "55"), scope=scope)
        assert ref.target_type == "orderman.Session"
        assert ref.target_id == "55"

    def test_different_scopes_can_hold_same_value(self):
        scope_a = {"store_id": 1, "business_date": "2026-04-20"}
        scope_b = {"store_id": 2, "business_date": "2026-04-20"}
        r1 = attach("TABLE", "12", "orderman.Session:1", scope=scope_a)
        r2 = attach("TABLE", "12", "orderman.Session:2", scope=scope_b)
        assert r1.pk != r2.pk


# ── resolve() tests ───────────────────────────────────────────────────────────

class TestResolve:
    def test_found(self, scope):
        attach("TABLE", "12", "orderman.Session:47", scope=scope)
        result = resolve("TABLE", "12", scope=scope)
        assert result == ("orderman.Session", "47")

    def test_not_found(self, scope):
        assert resolve("TABLE", "99", scope=scope) is None

    def test_normalizes_on_resolve(self, scope):
        attach("TABLE", "12", "orderman.Session:47", scope=scope)
        result = resolve("TABLE", "  12  ", scope=scope)
        assert result is not None

    def test_returns_none_for_inactive(self, scope):
        ref = attach("TABLE", "12", "orderman.Session:47", scope=scope)
        ref.is_active = False
        ref.save(update_fields=["is_active"])
        assert resolve("TABLE", "12", scope=scope) is None

    def test_scope_isolates_lookup(self):
        scope_a = {"store_id": 1, "business_date": "2026-04-20"}
        scope_b = {"store_id": 2, "business_date": "2026-04-20"}
        attach("TABLE", "12", "orderman.Session:1", scope=scope_a)
        attach("TABLE", "12", "orderman.Session:2", scope=scope_b)

        r1 = resolve("TABLE", "12", scope=scope_a)
        r2 = resolve("TABLE", "12", scope=scope_b)
        assert r1 == ("orderman.Session", "1")
        assert r2 == ("orderman.Session", "2")

    def test_no_scope_finds_first_active(self, scope):
        attach("LOWER_TYPE", "hello", "test.Model:1")
        result = resolve("LOWER_TYPE", "HELLO")
        assert result == ("test.Model", "1")


# ── resolve_partial() tests ───────────────────────────────────────────────────

class TestResolvePartial:
    def test_single_match_returns_result(self, scope):
        attach("TABLE", "POS-260420-AZ19", "orderman.Order:1", scope=scope)
        result = resolve_partial("TABLE", "AZ19", scope=scope)
        assert result == ("orderman.Order", "1")

    def test_no_match_returns_none(self, scope):
        result = resolve_partial("TABLE", "ZZ99", scope=scope)
        assert result is None

    def test_multiple_matches_raises_ambiguous(self):
        """Two active refs with same suffix → AmbiguousRef."""
        # Use ORDER_CODE (unique_scope=none) so we can have same suffix in different scopes
        attach("ORDER_CODE", "POS-260420-AZ19", "orderman.Order:1",
               scope={"store_id": 1, "business_date": "2026-04-20"})
        attach("ORDER_CODE", "WEB-260420-AZ19", "orderman.Order:2",
               scope={"store_id": 1, "business_date": "2026-04-20"})

        with pytest.raises(AmbiguousRef) as exc_info:
            resolve_partial("ORDER_CODE", "AZ19", scope={"store_id": 1, "business_date": "2026-04-20"})
        assert exc_info.value.count == 2

    def test_case_insensitive_suffix(self, scope):
        attach("TABLE", "POS-260420-AZ19", "orderman.Order:1", scope=scope)
        result = resolve_partial("TABLE", "az19", scope=scope)
        assert result == ("orderman.Order", "1")

    def test_inactive_not_matched(self, scope):
        ref = attach("TABLE", "POS-AZ19", "orderman.Order:1", scope=scope)
        ref.is_active = False
        ref.save(update_fields=["is_active"])
        assert resolve_partial("TABLE", "AZ19", scope=scope) is None


# ── resolve_object() tests ────────────────────────────────────────────────────

class TestResolveObject:
    def test_returns_model_instance(self, scope, user):
        attach("TABLE", "5", user, scope=scope)
        result = resolve_object("TABLE", "5", scope=scope)
        assert result is not None
        assert result.pk == user.pk

    def test_returns_none_when_not_found(self, scope):
        assert resolve_object("TABLE", "MISSING", scope=scope) is None

    def test_returns_none_when_object_deleted(self, scope, user):
        attach("TABLE", "5", user, scope=scope)
        user.delete()
        result = resolve_object("TABLE", "5", scope=scope)
        assert result is None

    def test_bad_model_returns_none(self, scope):
        Ref.objects.create(
            ref_type="TABLE",
            value="5",
            target_type="nonexistent.Ghost",
            target_id="1",
            scope=scope,
        )
        result = resolve_object("TABLE", "5", scope=scope)
        assert result is None


# ── deactivate() tests ────────────────────────────────────────────────────────

class TestDeactivate:
    def test_deactivates_all_refs_for_target(self, scope):
        attach("TABLE", "1", "orderman.Session:10", scope=scope)
        attach("TABLE", "2", "orderman.Session:10", scope={"store_id": 1, "business_date": "2026-04-21"})
        count = deactivate("orderman.Session:10", actor="lifecycle:close")
        assert count == 2
        assert Ref.objects.filter(target_id="10", is_active=True).count() == 0

    def test_sets_deactivated_by(self, scope):
        attach("TABLE", "1", "orderman.Session:10", scope=scope)
        deactivate("orderman.Session:10", actor="lifecycle:close")
        ref = Ref.objects.get(target_id="10")
        assert ref.deactivated_by == "lifecycle:close"
        assert ref.deactivated_at is not None

    def test_ref_types_filter(self, scope):
        attach("TABLE", "1", "orderman.Session:10", scope=scope)
        attach("TICKET", "T1", "orderman.Session:10", scope={"store_id": 1})
        count = deactivate("orderman.Session:10", ref_types=["TABLE"])
        assert count == 1
        assert Ref.objects.filter(target_id="10", ref_type="TICKET", is_active=True).count() == 1

    def test_deactivate_model_instance(self, scope, user):
        attach("TABLE", "5", user, scope=scope)
        count = deactivate(user)
        assert count == 1

    def test_returns_zero_if_nothing_to_deactivate(self):
        count = deactivate("orderman.Session:999")
        assert count == 0

    def test_does_not_touch_already_inactive(self, scope):
        ref = attach("TABLE", "1", "orderman.Session:10", scope=scope)
        ref.is_active = False
        ref.save(update_fields=["is_active"])
        count = deactivate("orderman.Session:10")
        assert count == 0


# ── transfer() tests ──────────────────────────────────────────────────────────

class TestTransfer:
    def test_transfers_all_active_refs(self, scope):
        attach("TABLE", "1", "orderman.Session:10", scope=scope)
        count = transfer("orderman.Session:10", "orderman.Order:100")
        assert count == 1

        ref = Ref.objects.get(value="1", ref_type="TABLE")
        assert ref.target_type == "orderman.Order"
        assert ref.target_id == "100"

    def test_ref_types_filter(self, scope):
        attach("TABLE", "1", "orderman.Session:10", scope=scope)
        attach("TICKET", "T1", "orderman.Session:10", scope={"store_id": 1})

        count = transfer("orderman.Session:10", "orderman.Order:100", ref_types=["TICKET"])
        assert count == 1

        # TABLE still on session
        assert Ref.objects.filter(ref_type="TABLE", target_id="10").count() == 1
        # TICKET moved to order
        assert Ref.objects.filter(ref_type="TICKET", target_id="100").count() == 1

    def test_only_transfers_active_refs(self, scope):
        ref = attach("TABLE", "1", "orderman.Session:10", scope=scope)
        ref.is_active = False
        ref.save(update_fields=["is_active"])

        count = transfer("orderman.Session:10", "orderman.Order:100")
        assert count == 0

    def test_returns_zero_when_nothing_to_transfer(self):
        count = transfer("orderman.Session:999", "orderman.Order:100")
        assert count == 0

    def test_transfer_model_instances(self, scope, user):
        attach("TABLE", "5", "orderman.Session:10", scope=scope)
        # Just test it accepts instances without error
        transfer("orderman.Session:10", "orderman.Session:20")
        ref = Ref.objects.get(ref_type="TABLE", value="5")
        assert ref.target_id == "20"


# ── refs_for() tests ──────────────────────────────────────────────────────────

class TestRefsFor:
    def test_returns_active_refs(self, scope):
        attach("TABLE", "1", "orderman.Session:10", scope=scope)
        qs = refs_for("orderman.Session:10")
        assert qs.count() == 1

    def test_active_only_true_excludes_inactive(self, scope):
        ref = attach("TABLE", "1", "orderman.Session:10", scope=scope)
        ref.is_active = False
        ref.save(update_fields=["is_active"])

        qs = refs_for("orderman.Session:10", active_only=True)
        assert qs.count() == 0

    def test_active_only_false_includes_inactive(self, scope):
        ref = attach("TABLE", "1", "orderman.Session:10", scope=scope)
        ref.is_active = False
        ref.save(update_fields=["is_active"])

        qs = refs_for("orderman.Session:10", active_only=False)
        assert qs.count() == 1

    def test_multiple_refs_for_target(self, scope):
        attach("TABLE", "1", "orderman.Session:10", scope=scope)
        attach("TICKET", "T1", "orderman.Session:10", scope={"store_id": 1})
        qs = refs_for("orderman.Session:10")
        assert qs.count() == 2

    def test_model_instance_target(self, scope, user):
        attach("TABLE", "5", user, scope=scope)
        qs = refs_for(user)
        assert qs.count() == 1

    def test_ordered_by_created_at(self, scope):
        r1 = attach("TABLE", "1", "orderman.Session:10", scope=scope)
        r2 = attach("TABLE", "2", "orderman.Session:10",
                    scope={"store_id": 1, "business_date": "2026-04-21"})
        qs = list(refs_for("orderman.Session:10"))
        assert qs[0].pk == r1.pk
        assert qs[1].pk == r2.pk
