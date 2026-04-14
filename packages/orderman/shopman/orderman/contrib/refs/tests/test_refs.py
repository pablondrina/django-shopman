"""
Tests para contrib/refs.
"""

import uuid
from datetime import date

import pytest
from django.test import TestCase
from shopman.orderman.contrib.refs.exceptions import (
    RefConflict,
    RefScopeInvalid,
    RefTypeNotFound,
)
from shopman.orderman.contrib.refs.models import Ref, RefSequence
from shopman.orderman.contrib.refs.registry import (
    clear_ref_types,
    get_ref_type,
    register_ref_type,
)
from shopman.orderman.contrib.refs.sequences import (
    attach_sequence_ref,
    generate_sequence_value,
    get_current_sequence_value,
    reset_sequence,
)
from shopman.orderman.contrib.refs.services import (
    attach_ref,
    deactivate_refs,
    on_session_committed,
    resolve_ref,
)
from shopman.orderman.contrib.refs.types import POS_TAB, POS_TABLE, RefType

# RefType de teste para sequences e copy_to_order
TEST_TICKET = RefType(
    slug="TEST_TICKET",
    label="Ticket de Teste",
    target_kind="SESSION",
    scope_keys=("store_id", "business_date"),
    unique_while_active=True,
    expires_on_session_close=False,
    copy_to_order=True,
)


class RefTypeRegistryTests(TestCase):
    """Testes para o registry de RefTypes."""

    def setUp(self):
        clear_ref_types()

    def tearDown(self):
        clear_ref_types()

    def test_register_and_get(self):
        """RefType pode ser registrado e recuperado."""
        ref_type = RefType(
            slug="TEST_TYPE",
            label="Test",
            target_kind="SESSION",
            scope_keys=("store_id",),
        )
        register_ref_type(ref_type)

        result = get_ref_type("TEST_TYPE")
        assert result == ref_type

    def test_get_nonexistent_returns_none(self):
        """get_ref_type retorna None para slug não registrado."""
        assert get_ref_type("NONEXISTENT") is None

    def test_duplicate_registration_raises(self):
        """Registrar mesmo slug duas vezes levanta ValueError."""
        ref_type = RefType(
            slug="DUPLICATE",
            label="Test",
            target_kind="SESSION",
            scope_keys=(),
        )
        register_ref_type(ref_type)

        with pytest.raises(ValueError, match="already registered"):
            register_ref_type(ref_type)


class AttachRefTests(TestCase):
    """Testes para attach_ref."""

    def setUp(self):
        clear_ref_types()
        register_ref_type(POS_TABLE)
        register_ref_type(POS_TAB)
        Ref.objects.all().delete()

    def tearDown(self):
        clear_ref_types()

    def test_attach_creates_ref(self):
        """attach_ref cria nova Ref."""
        session_id = uuid.uuid4()
        scope = {"store_id": 1, "business_date": str(date.today())}

        ref = attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)

        assert ref.ref_type == "POS_TABLE"
        assert ref.target_kind == "SESSION"
        assert ref.target_id == session_id
        assert ref.value == "12"  # Normalizado (uppercase, mas "12" já é)
        assert ref.is_active is True

    def test_attach_normalizes_value(self):
        """attach_ref normaliza valor (trim + uppercase)."""
        session_id = uuid.uuid4()
        scope = {"store_id": 1, "business_date": str(date.today())}

        ref = attach_ref("SESSION", session_id, "POS_TABLE", "  mesa 12  ", scope)

        assert ref.value == "MESA 12"

    def test_attach_idempotent_same_target(self):
        """attach_ref é idempotente para mesmo target."""
        session_id = uuid.uuid4()
        scope = {"store_id": 1, "business_date": str(date.today())}

        ref1 = attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)
        ref2 = attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)

        assert ref1.id == ref2.id
        assert Ref.objects.count() == 1

    def test_attach_conflict_different_target(self):
        """attach_ref levanta RefConflict para target diferente."""
        session1 = uuid.uuid4()
        session2 = uuid.uuid4()
        scope = {"store_id": 1, "business_date": str(date.today())}

        attach_ref("SESSION", session1, "POS_TABLE", "12", scope)

        with pytest.raises(RefConflict):
            attach_ref("SESSION", session2, "POS_TABLE", "12", scope)

    def test_attach_invalid_scope_raises(self):
        """attach_ref levanta RefScopeInvalid se scope incompleto."""
        session_id = uuid.uuid4()
        scope = {"store_id": 1}  # Falta business_date

        with pytest.raises(RefScopeInvalid) as exc:
            attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)

        assert "business_date" in str(exc.value.missing_keys)

    def test_attach_unknown_ref_type_raises(self):
        """attach_ref levanta RefTypeNotFound para RefType desconhecido."""
        session_id = uuid.uuid4()

        with pytest.raises(RefTypeNotFound):
            attach_ref("SESSION", session_id, "UNKNOWN", "12", {})


class ResolveRefTests(TestCase):
    """Testes para resolve_ref."""

    def setUp(self):
        clear_ref_types()
        register_ref_type(POS_TABLE)
        Ref.objects.all().delete()

    def tearDown(self):
        clear_ref_types()

    def test_resolve_finds_active_ref(self):
        """resolve_ref encontra Ref ACTIVE."""
        session_id = uuid.uuid4()
        scope = {"store_id": 1, "business_date": str(date.today())}

        attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)

        result = resolve_ref("POS_TABLE", "12", scope)

        assert result is not None
        assert result == ("SESSION", session_id)

    def test_resolve_returns_none_for_inactive(self):
        """resolve_ref retorna None para Ref inativa."""
        session_id = uuid.uuid4()
        scope = {"store_id": 1, "business_date": str(date.today())}

        ref = attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)
        ref.deactivate()

        result = resolve_ref("POS_TABLE", "12", scope)
        assert result is None

    def test_resolve_returns_none_for_different_scope(self):
        """resolve_ref retorna None se scope diferente."""
        session_id = uuid.uuid4()
        scope1 = {"store_id": 1, "business_date": str(date.today())}
        scope2 = {"store_id": 2, "business_date": str(date.today())}

        attach_ref("SESSION", session_id, "POS_TABLE", "12", scope1)

        result = resolve_ref("POS_TABLE", "12", scope2)
        assert result is None

    def test_resolve_normalizes_value(self):
        """resolve_ref normaliza valor antes de buscar."""
        session_id = uuid.uuid4()
        scope = {"store_id": 1, "business_date": str(date.today())}

        attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)

        # Buscar com espaços e lowercase
        result = resolve_ref("POS_TABLE", "  12  ", scope)
        assert result is not None


class DeactivateRefsTests(TestCase):
    """Testes para deactivate_refs."""

    def setUp(self):
        clear_ref_types()
        register_ref_type(POS_TABLE)
        register_ref_type(POS_TAB)
        Ref.objects.all().delete()

    def tearDown(self):
        clear_ref_types()

    def test_deactivate_all(self):
        """deactivate_refs desativa todas as Refs do target."""
        session_id = uuid.uuid4()
        scope = {"store_id": 1, "business_date": str(date.today())}

        attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)
        attach_ref("SESSION", session_id, "POS_TAB", "A1", scope)

        count = deactivate_refs("SESSION", session_id)

        assert count == 2
        assert Ref.objects.filter(target_id=session_id, is_active=True).count() == 0

    def test_deactivate_specific_types(self):
        """deactivate_refs desativa apenas tipos especificados."""
        session_id = uuid.uuid4()
        scope = {"store_id": 1, "business_date": str(date.today())}

        attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)
        attach_ref("SESSION", session_id, "POS_TAB", "A1", scope)

        count = deactivate_refs("SESSION", session_id, ref_type_slugs=["POS_TABLE"])

        assert count == 1

        # POS_TABLE desativado
        assert resolve_ref("POS_TABLE", "12", scope) is None
        # POS_TAB ainda ativo
        assert resolve_ref("POS_TAB", "A1", scope) is not None


class SequenceTests(TestCase):
    """Testes para sequences."""

    def setUp(self):
        clear_ref_types()
        register_ref_type(TEST_TICKET)
        Ref.objects.all().delete()
        RefSequence.objects.all().delete()

    def tearDown(self):
        clear_ref_types()

    def test_generate_sequence_increments(self):
        """generate_sequence_value incrementa corretamente."""
        scope = {"store_id": 1, "business_date": str(date.today())}

        v1 = generate_sequence_value("TICKET", scope)
        v2 = generate_sequence_value("TICKET", scope)
        v3 = generate_sequence_value("TICKET", scope)

        assert v1 == "001"
        assert v2 == "002"
        assert v3 == "003"

    def test_sequence_isolated_by_scope(self):
        """Sequências são isoladas por scope."""
        scope1 = {"store_id": 1, "business_date": str(date.today())}
        scope2 = {"store_id": 2, "business_date": str(date.today())}

        v1_s1 = generate_sequence_value("TICKET", scope1)
        v1_s2 = generate_sequence_value("TICKET", scope2)
        v2_s1 = generate_sequence_value("TICKET", scope1)

        assert v1_s1 == "001"
        assert v1_s2 == "001"  # Scope diferente, sequência independente
        assert v2_s1 == "002"

    def test_attach_sequence_ref(self):
        """attach_sequence_ref gera valor e anexa."""
        session_id = uuid.uuid4()
        scope = {"store_id": 1, "business_date": str(date.today())}

        ref = attach_sequence_ref("SESSION", session_id, "TEST_TICKET", scope)

        assert ref.value == "001"
        assert ref.ref_type == "TEST_TICKET"
        assert ref.is_active is True

    def test_reset_sequence(self):
        """reset_sequence zera contador."""
        scope = {"store_id": 1, "business_date": str(date.today())}

        generate_sequence_value("TICKET", scope)
        generate_sequence_value("TICKET", scope)

        reset_sequence("TICKET", scope)

        v = generate_sequence_value("TICKET", scope)
        assert v == "001"

    def test_get_current_sequence_value(self):
        """get_current_sequence_value retorna valor sem incrementar."""
        scope = {"store_id": 1, "business_date": str(date.today())}

        generate_sequence_value("TICKET", scope)
        generate_sequence_value("TICKET", scope)

        current = get_current_sequence_value("TICKET", scope)
        assert current == 2

        # Não incrementou
        assert get_current_sequence_value("TICKET", scope) == 2


class OnSessionCommittedTests(TestCase):
    """Testes para on_session_committed hook."""

    def setUp(self):
        clear_ref_types()
        register_ref_type(POS_TABLE)  # expires_on_session_close=True, copy_to_order=False
        register_ref_type(TEST_TICKET)  # expires_on_session_close=False, copy_to_order=True
        Ref.objects.all().delete()

    def tearDown(self):
        clear_ref_types()

    def test_expires_on_session_close(self):
        """Ref com expires_on_session_close=True é desativada."""
        session_id = uuid.uuid4()
        order_id = uuid.uuid4()
        scope = {"store_id": 1, "business_date": str(date.today())}

        attach_ref("SESSION", session_id, "POS_TABLE", "12", scope)

        on_session_committed(session_id, order_id)

        # POS_TABLE deve estar inativo
        ref = Ref.objects.get(ref_type="POS_TABLE", target_id=session_id)
        assert ref.is_active is False

    def test_copy_to_order(self):
        """Ref com copy_to_order=True é copiada para Order."""
        session_id = uuid.uuid4()
        order_id = uuid.uuid4()
        scope = {"store_id": 1, "business_date": str(date.today())}

        attach_ref("SESSION", session_id, "TEST_TICKET", "001", scope)

        on_session_committed(session_id, order_id)

        # TEST_TICKET deve ter cópia no Order
        order_ref = Ref.objects.filter(
            ref_type="TEST_TICKET",
            target_kind="ORDER",
            target_id=order_id,
        ).first()
        assert order_ref is not None
        assert order_ref.value == "001"
        assert order_ref.is_active is True

        # Original na Session ainda existe (expires_on_session_close=False)
        session_ref = Ref.objects.get(
            ref_type="TEST_TICKET",
            target_kind="SESSION",
            target_id=session_id,
        )
        assert session_ref.is_active is True
