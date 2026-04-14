"""
Services para contrib/refs.

API principal para manipulação de Refs.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from shopman.orderman.contrib.refs.exceptions import (
    RefConflict,
    RefScopeInvalid,
    RefTypeNotFound,
)
from shopman.orderman.contrib.refs.models import Ref
from shopman.orderman.contrib.refs.registry import get_ref_type


def _normalize_value(value: str) -> str:
    """Normaliza valor: strip + uppercase."""
    return value.strip().upper()


def _validate_scope(ref_type_slug: str, scope: dict, scope_keys: tuple[str, ...]) -> None:
    """Valida que scope contém todas as keys necessárias."""
    provided_keys = set(scope.keys())
    required_keys = set(scope_keys)
    missing = required_keys - provided_keys
    if missing:
        raise RefScopeInvalid(missing, ref_type_slug)


def _build_scope_filter(scope: dict, scope_keys: tuple[str, ...]) -> Q:
    """Constrói filtro Q para scope (apenas keys relevantes)."""
    q = Q()
    for key in scope_keys:
        # JSONField lookup: scope__key=value
        q &= Q(**{f"scope__{key}": scope[key]})
    return q


def resolve_ref(
    ref_type_slug: str,
    value: str,
    scope: dict,
) -> tuple[str, UUID] | None:
    """
    Busca Ref ACTIVE por tipo, valor e scope.

    Args:
        ref_type_slug: Slug do RefType
        value: Valor a buscar (será normalizado)
        scope: Scope de unicidade

    Returns:
        (target_kind, target_id) ou None se não encontrado.

    Raises:
        RefTypeNotFound: Se RefType não registrado
        RefScopeInvalid: Se scope inválido
    """
    ref_type = get_ref_type(ref_type_slug)
    if not ref_type:
        raise RefTypeNotFound(ref_type_slug)

    _validate_scope(ref_type_slug, scope, ref_type.scope_keys)
    normalized = _normalize_value(value)

    scope_filter = _build_scope_filter(scope, ref_type.scope_keys)

    ref = Ref.objects.filter(
        ref_type=ref_type_slug,
        value=normalized,
        is_active=True,
    ).filter(scope_filter).first()

    if ref:
        return (ref.target_kind, ref.target_id)
    return None


def attach_ref(
    target_kind: Literal["SESSION", "ORDER"],
    target_id: UUID,
    ref_type_slug: str,
    value: str,
    scope: dict,
) -> Ref:
    """
    Associa uma Ref a um target.

    Args:
        target_kind: "SESSION" ou "ORDER"
        target_id: ID do target
        ref_type_slug: Slug do RefType
        value: Valor do localizador (será normalizado)
        scope: Scope de unicidade

    Returns:
        Ref existente (idempotência) ou nova Ref criada.

    Raises:
        RefTypeNotFound: Se RefType não registrado
        RefScopeInvalid: Se scope inválido
        RefConflict: Se já existe Ref ACTIVE com mesmo (type, value, scope) para outro target
    """
    ref_type = get_ref_type(ref_type_slug)
    if not ref_type:
        raise RefTypeNotFound(ref_type_slug)

    # Validar target_kind
    if ref_type.target_kind not in ("BOTH", target_kind):
        raise ValueError(
            f"RefType '{ref_type_slug}' does not support target_kind='{target_kind}'"
        )

    _validate_scope(ref_type_slug, scope, ref_type.scope_keys)
    normalized = _normalize_value(value)

    # Extrair apenas as keys relevantes do scope
    filtered_scope = {k: scope[k] for k in ref_type.scope_keys}

    scope_filter = _build_scope_filter(scope, ref_type.scope_keys)

    with transaction.atomic():
        # Buscar Refs existentes
        if ref_type.unique_while_active:
            # Unicidade apenas entre ACTIVE
            existing = Ref.objects.select_for_update().filter(
                ref_type=ref_type_slug,
                value=normalized,
                is_active=True,
            ).filter(scope_filter).first()
        else:
            # Unicidade total (UNIQUE_ALL)
            existing = Ref.objects.select_for_update().filter(
                ref_type=ref_type_slug,
                value=normalized,
            ).filter(scope_filter).first()

        if existing:
            # Idempotência: mesmo target = retorna existente
            if existing.target_kind == target_kind and existing.target_id == target_id:
                return existing

            # Conflito: outro target
            raise RefConflict(
                ref_type_slug,
                normalized,
                existing.target_kind,
                str(existing.target_id),
            )

        # Criar nova Ref
        ref = Ref.objects.create(
            ref_type=ref_type_slug,
            target_kind=target_kind,
            target_id=target_id,
            value=normalized,
            scope=filtered_scope,
            is_active=True,
        )
        return ref


def deactivate_refs(
    target_kind: Literal["SESSION", "ORDER"],
    target_id: UUID,
    ref_type_slugs: list[str] | None = None,
) -> int:
    """
    Desativa Refs de um target.

    Args:
        target_kind: "SESSION" ou "ORDER"
        target_id: ID do target
        ref_type_slugs: Se None, desativa todas. Se lista, só as especificadas.

    Returns:
        Quantidade de Refs desativadas.
    """
    queryset = Ref.objects.filter(
        target_kind=target_kind,
        target_id=target_id,
        is_active=True,
    )

    if ref_type_slugs:
        queryset = queryset.filter(ref_type__in=ref_type_slugs)

    return queryset.update(is_active=False)


def get_refs_for_target(
    target_kind: Literal["SESSION", "ORDER"],
    target_id: UUID,
    active_only: bool = True,
) -> list[Ref]:
    """
    Lista Refs de um target.

    Args:
        target_kind: "SESSION" ou "ORDER"
        target_id: ID do target
        active_only: Se True, retorna apenas ACTIVE

    Returns:
        Lista de Refs.
    """
    queryset = Ref.objects.filter(
        target_kind=target_kind,
        target_id=target_id,
    )

    if active_only:
        queryset = queryset.filter(is_active=True)

    return list(queryset.order_by("created_at"))


def on_session_committed(session_id: UUID, order_id: UUID) -> None:
    """
    Hook chamado após CommitService criar Order.

    Processa carryover de Refs da Session para Order:
    - expires_on_session_close=True: desativa Ref na Session
    - copy_to_order=True: cria cópia da Ref para Order

    Args:
        session_id: ID da Session que foi commitada
        order_id: ID do Order criado
    """
    refs = Ref.objects.filter(
        target_kind="SESSION",
        target_id=session_id,
        is_active=True,
    )

    for ref in refs:
        ref_type = get_ref_type(ref.ref_type)
        if not ref_type:
            continue

        # Copiar para Order se configurado
        if ref_type.copy_to_order:
            Ref.objects.create(
                ref_type=ref.ref_type,
                target_kind="ORDER",
                target_id=order_id,
                value=ref.value,
                scope=ref.scope,
                is_active=True,
            )

        # Desativar na Session se configurado
        if ref_type.expires_on_session_close:
            ref.is_active = False
            ref.save(update_fields=["is_active"])
