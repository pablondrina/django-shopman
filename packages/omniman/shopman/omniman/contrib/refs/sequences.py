"""
Sequences para geração automática de valores.

Usado para RefTypes que precisam de valores sequenciais (senhas, tickets, etc.).
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal
from uuid import UUID

from django.db import transaction

from shopman.omniman.contrib.refs.models import Ref, RefSequence
from shopman.omniman.contrib.refs.registry import get_ref_type
from shopman.omniman.contrib.refs.exceptions import RefTypeNotFound, RefScopeInvalid


def _compute_scope_hash(scope: dict) -> str:
    """Computa hash determinístico do scope."""
    # Ordenar keys para garantir determinismo
    sorted_scope = json.dumps(scope, sort_keys=True, default=str)
    return hashlib.sha256(sorted_scope.encode()).hexdigest()[:16]


def generate_sequence_value(
    sequence_name: str,
    scope: dict,
    pad_width: int = 3,
) -> str:
    """
    Gera próximo valor sequencial para um escopo.

    Args:
        sequence_name: Nome da sequência (geralmente RefType.slug)
        scope: Scope de particionamento
        pad_width: Largura do padding com zeros (ex: 3 -> "001")

    Returns:
        Próximo valor formatado (ex: "001", "002", ...)

    Thread-safe via SELECT FOR UPDATE.
    """
    scope_hash = _compute_scope_hash(scope)

    with transaction.atomic():
        seq, created = RefSequence.objects.select_for_update().get_or_create(
            sequence_name=sequence_name,
            scope_hash=scope_hash,
            defaults={"scope": scope, "last_value": 0},
        )

        seq.last_value += 1
        seq.save(update_fields=["last_value"])

        return str(seq.last_value).zfill(pad_width)


def attach_sequence_ref(
    target_kind: Literal["SESSION", "ORDER"],
    target_id: UUID,
    ref_type_slug: str,
    scope: dict,
    pad_width: int = 3,
) -> Ref:
    """
    Gera valor sequencial e anexa como Ref.

    Combina generate_sequence_value + attach_ref em transação atômica.

    Args:
        target_kind: "SESSION" ou "ORDER"
        target_id: ID do target
        ref_type_slug: Slug do RefType
        scope: Scope de unicidade e sequência
        pad_width: Largura do padding com zeros

    Returns:
        Ref criada com valor sequencial.

    Raises:
        RefTypeNotFound: Se RefType não registrado
        RefScopeInvalid: Se scope inválido
    """
    from shopman.omniman.contrib.refs.services import attach_ref

    ref_type = get_ref_type(ref_type_slug)
    if not ref_type:
        raise RefTypeNotFound(ref_type_slug)

    # Validar scope
    required_keys = set(ref_type.scope_keys)
    provided_keys = set(scope.keys())
    missing = required_keys - provided_keys
    if missing:
        raise RefScopeInvalid(missing, ref_type_slug)

    # Filtrar scope para apenas as keys relevantes
    filtered_scope = {k: scope[k] for k in ref_type.scope_keys}

    with transaction.atomic():
        value = generate_sequence_value(
            sequence_name=ref_type_slug,
            scope=filtered_scope,
            pad_width=pad_width,
        )

        return attach_ref(
            target_kind=target_kind,
            target_id=target_id,
            ref_type_slug=ref_type_slug,
            value=value,
            scope=filtered_scope,
        )


def reset_sequence(sequence_name: str, scope: dict) -> None:
    """
    Reseta uma sequência para 0.

    Útil para testes ou reset diário.

    Args:
        sequence_name: Nome da sequência
        scope: Scope da sequência
    """
    scope_hash = _compute_scope_hash(scope)

    RefSequence.objects.filter(
        sequence_name=sequence_name,
        scope_hash=scope_hash,
    ).update(last_value=0)


def get_current_sequence_value(sequence_name: str, scope: dict) -> int:
    """
    Retorna valor atual de uma sequência (sem incrementar).

    Args:
        sequence_name: Nome da sequência
        scope: Scope da sequência

    Returns:
        Último valor gerado ou 0 se sequência não existe.
    """
    scope_hash = _compute_scope_hash(scope)

    try:
        seq = RefSequence.objects.get(
            sequence_name=sequence_name,
            scope_hash=scope_hash,
        )
        return seq.last_value
    except RefSequence.DoesNotExist:
        return 0
