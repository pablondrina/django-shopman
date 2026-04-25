"""
Orderman contrib/refs services — thin wrappers over shopman.refs.

Maps the old (target_kind, target_id) convention to the new
target_type string format used by shopman.refs.
"""

from __future__ import annotations

from typing import Literal

from shopman.refs.models import Ref
from shopman.refs.services import attach, deactivate, refs_for, resolve, transfer

_KIND_TO_TYPE = {
    "SESSION": "orderman.Session",
    "ORDER": "orderman.Order",
}

_TYPE_TO_KIND: dict[str, str] = {v: k for k, v in _KIND_TO_TYPE.items()}


def attach_ref(
    target_kind: Literal["SESSION", "ORDER"],
    target_id: int | str,
    ref_type_slug: str,
    value: str,
    scope: dict,
) -> Ref:
    target_type = _KIND_TO_TYPE[target_kind]
    return attach(ref_type_slug, value, f"{target_type}:{target_id}", scope=scope)


def resolve_ref(
    ref_type_slug: str,
    value: str,
    scope: dict,
) -> tuple[str, str] | None:
    result = resolve(ref_type_slug, value, scope)
    if result is None:
        return None
    target_type, target_id = result
    kind = _TYPE_TO_KIND.get(target_type, target_type)
    return (kind, target_id)


def deactivate_refs(
    target_kind: Literal["SESSION", "ORDER"],
    target_id: int | str,
    ref_type_slugs: list[str] | None = None,
) -> int:
    target_type = _KIND_TO_TYPE[target_kind]
    return deactivate(f"{target_type}:{target_id}", ref_types=ref_type_slugs)


def get_refs_for_target(
    target_kind: Literal["SESSION", "ORDER"],
    target_id: int | str,
    active_only: bool = True,
) -> list[Ref]:
    target_type = _KIND_TO_TYPE[target_kind]
    return list(refs_for(f"{target_type}:{target_id}", active_only=active_only))


def on_session_committed(session_id: int | str, order_id: int | str) -> None:
    """Transfer all active session refs to the new order."""
    transfer(
        f"orderman.Session:{session_id}",
        f"orderman.Order:{order_id}",
        actor="lifecycle:commit",
    )
