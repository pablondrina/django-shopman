"""
Ref lifecycle services.

Public API: attach, resolve, resolve_partial, resolve_object, deactivate, transfer, refs_for
Helpers:    target_str, parse_target
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from shopman.refs.exceptions import AmbiguousRef, RefConflict, RefScopeInvalid
from shopman.refs.models import Ref
from shopman.refs.registry import get_ref_type
from shopman.refs.types import RefType

logger = logging.getLogger("shopman.refs")


# ── Target string helpers ─────────────────────────────────────────────────────

def target_str(instance: Any) -> str:
    """Convert a model instance to target string: "orderman.Session:47"."""
    meta = instance._meta
    return f"{meta.app_label}.{meta.object_name}:{instance.pk}"


def parse_target(target: str) -> tuple[str, str]:
    """Parse "orderman.Session:47" into ("orderman.Session", "47").

    Uses rsplit so pks containing colons (e.g. UUIDs with colons, unusual but safe) are handled.

    Raises:
        ValueError: If the string does not contain a colon separator.
    """
    try:
        type_part, id_part = target.rsplit(":", 1)
        if not type_part or not id_part:
            raise ValueError
        return type_part, id_part
    except ValueError:
        raise ValueError(
            f"Invalid target string: {target!r}. Expected format: 'app_label.ModelName:pk'"
        )


def _coerce_target(target: Any) -> tuple[str, str]:
    """Normalize any supported target form to (target_type, target_id) strings.

    Accepts:
        - str:   "orderman.Session:47"
        - tuple: ("orderman.Session", "47") or (ModelClass, pk)
        - model instance
    """
    if isinstance(target, str):
        return parse_target(target)
    if isinstance(target, tuple) and len(target) == 2:
        first, second = target
        if isinstance(first, str):
            return first, str(second)
        # (ModelClass, pk) form
        meta = first._meta
        return f"{meta.app_label}.{meta.object_name}", str(second)
    # Model instance
    meta = target._meta
    return f"{meta.app_label}.{meta.object_name}", str(target.pk)


# ── Value + scope helpers ─────────────────────────────────────────────────────

def _normalize_value(value: str, normalizer: str) -> str:
    if normalizer == "upper_strip":
        return value.strip().upper()
    if normalizer == "lower_strip":
        return value.strip().lower()
    return value  # "none"


def _validate_scope(ref_type: RefType, scope: dict) -> None:
    missing = {k for k in ref_type.scope_keys if k not in scope}
    if missing:
        raise RefScopeInvalid(missing, ref_type.slug)


def _build_scope_filter(scope: dict, scope_keys: tuple) -> dict:
    """Build Django ORM filter kwargs for JSONField scope matching."""
    return {f"scope__{k}": scope[k] for k in scope_keys if k in scope}


# ── Core services ─────────────────────────────────────────────────────────────

def attach(
    ref_type: str,
    value: str,
    target: Any,
    scope: dict | None = None,
    actor: str = "",
    metadata: dict | None = None,
) -> Ref:
    """Attach a ref to a target entity.

    Idempotent: if the same (ref_type, normalized_value, scope) already points at
    the same target, returns the existing Ref.

    Args:
        ref_type: RefType.slug — must be registered.
        value: Raw value (normalized before storage/lookup).
        target: Destination entity — string "orderman.Session:47", (ModelClass, pk),
            or a model instance.
        scope: Partitioning dict. Must contain all RefType.scope_keys.
        actor: Who is attaching (stored in Ref.actor).
        metadata: Arbitrary extra data stored on the Ref.

    Returns:
        The attached (or existing idempotent) Ref.

    Raises:
        KeyError: RefType not registered.
        RefScopeInvalid: scope is missing required keys.
        RefConflict: value+scope already assigned to a different target.
    """
    rt = get_ref_type(ref_type)
    if rt is None:
        raise KeyError(f"RefType '{ref_type}' not registered. Register it in AppConfig.ready().")

    scope = scope or {}
    _validate_scope(rt, scope)

    normalized = _normalize_value(value, rt.normalizer)
    target_type, target_id = _coerce_target(target)

    with transaction.atomic():
        qs = Ref.objects.select_for_update().filter(ref_type=ref_type, value=normalized)

        if rt.scope_keys:
            qs = qs.filter(**_build_scope_filter(scope, rt.scope_keys))

        if rt.unique_scope == "active":
            qs = qs.filter(is_active=True)
        elif rt.unique_scope == "none":
            qs = qs.none()
        # "all" — no is_active filter; check all states

        existing = qs.first()

        if existing is not None:
            if existing.target_type == target_type and existing.target_id == target_id:
                logger.debug(
                    "refs.attach.idempotent",
                    extra={"ref_type": ref_type, "value": normalized, "target": f"{target_type}:{target_id}"},
                )
                return existing
            raise RefConflict(ref_type, normalized, existing.target_type, existing.target_id)

        ref = Ref.objects.create(
            ref_type=ref_type,
            value=normalized,
            target_type=target_type,
            target_id=target_id,
            scope=scope,
            actor=actor,
            metadata=metadata or {},
        )
        logger.info(
            "refs.attached",
            extra={
                "ref_type": ref_type,
                "value": normalized,
                "target": f"{target_type}:{target_id}",
                "actor": actor,
            },
        )
        return ref


def resolve(
    ref_type: str,
    value: str,
    scope: dict | None = None,
) -> tuple[str, str] | None:
    """Find the active ref for (ref_type, value, scope).

    Returns:
        (target_type, target_id) or None if no active ref found.
    """
    rt = get_ref_type(ref_type)
    if rt:
        value = _normalize_value(value, rt.normalizer)

    qs = Ref.objects.filter(ref_type=ref_type, value=value, is_active=True)

    if scope:
        scope_keys = rt.scope_keys if rt else tuple(scope.keys())
        filt = _build_scope_filter(scope, scope_keys)
        if filt:
            qs = qs.filter(**filt)

    ref = qs.first()
    return (ref.target_type, ref.target_id) if ref else None


def resolve_partial(
    ref_type: str,
    suffix: str,
    scope: dict | None = None,
) -> tuple[str, str] | None:
    """Find the active ref whose value ends with suffix.

    Allows operators to use short codes (e.g. "AZ19") to look up full refs
    like "POS-260420-AZ19" within a scope.

    Returns:
        (target_type, target_id) if exactly one match; None if no match.

    Raises:
        AmbiguousRef: More than one active ref ends with suffix in the scope.
    """
    qs = Ref.objects.filter(ref_type=ref_type, value__iendswith=suffix, is_active=True)

    if scope:
        rt = get_ref_type(ref_type)
        scope_keys = rt.scope_keys if rt else tuple(scope.keys())
        filt = _build_scope_filter(scope, scope_keys)
        if filt:
            qs = qs.filter(**filt)

    count = qs.count()
    if count == 0:
        return None
    if count > 1:
        raise AmbiguousRef(ref_type, suffix, count)

    ref = qs.first()
    return (ref.target_type, ref.target_id)


def resolve_object(
    ref_type: str,
    value: str,
    scope: dict | None = None,
) -> Any | None:
    """Resolve ref to the actual model instance via Django's app registry.

    Returns:
        Model instance or None if ref not found or object no longer exists.
    """
    result = resolve(ref_type, value, scope)
    if result is None:
        return None

    target_type, target_id = result
    try:
        app_label, model_name = target_type.split(".", 1)
    except ValueError:
        logger.warning("refs.resolve_object.bad_target_type", extra={"target_type": target_type})
        return None

    from django.apps import apps
    try:
        Model = apps.get_model(app_label, model_name)
    except LookupError:
        logger.warning("refs.resolve_object.model_not_found", extra={"target_type": target_type})
        return None

    try:
        return Model.objects.get(pk=target_id)
    except Model.DoesNotExist:
        return None


def deactivate(
    target: Any,
    ref_types: list[str] | None = None,
    actor: str = "",
) -> int:
    """Deactivate all active refs for a target.

    Args:
        target: "orderman.Session:47" string or model instance.
        ref_types: Optional filter — only deactivate these ref_type slugs.
        actor: Logged in Ref.deactivated_by.

    Returns:
        Number of refs deactivated.
    """
    target_type, target_id = _coerce_target(target)
    now = timezone.now()

    qs = Ref.objects.filter(target_type=target_type, target_id=target_id, is_active=True)
    if ref_types is not None:
        qs = qs.filter(ref_type__in=ref_types)

    count = qs.update(is_active=False, deactivated_at=now, deactivated_by=actor)

    if count:
        logger.info(
            "refs.deactivated",
            extra={"target": f"{target_type}:{target_id}", "count": count, "actor": actor},
        )
    return count


def transfer(
    source: Any,
    dest: Any,
    ref_types: list[str] | None = None,
    actor: str = "",
) -> int:
    """Transfer active refs from source target to dest target.

    Primary use case: move Session refs to Order on commit
    (Session→Order lifecycle transition).

    Args:
        source: Source target string or model instance.
        dest: Destination target string or model instance.
        ref_types: Optional filter — only transfer these ref_type slugs. None = all.
        actor: Used for logging only (not stored on the transferred Refs).

    Returns:
        Number of refs transferred.
    """
    src_type, src_id = _coerce_target(source)
    dst_type, dst_id = _coerce_target(dest)

    with transaction.atomic():
        qs = Ref.objects.select_for_update().filter(
            target_type=src_type, target_id=src_id, is_active=True
        )
        if ref_types is not None:
            qs = qs.filter(ref_type__in=ref_types)

        count = qs.count()
        qs.update(target_type=dst_type, target_id=dst_id)

        if count:
            logger.info(
                "refs.transferred",
                extra={
                    "from": f"{src_type}:{src_id}",
                    "to": f"{dst_type}:{dst_id}",
                    "count": count,
                    "actor": actor,
                },
            )
        return count


def refs_for(
    target: Any,
    active_only: bool = True,
):
    """Return QuerySet of Refs for a target, ordered by created_at.

    Args:
        target: "orderman.Session:47" string or model instance.
        active_only: If True, only return active refs.

    Returns:
        QuerySet[Ref]
    """
    target_type, target_id = _coerce_target(target)
    qs = Ref.objects.filter(target_type=target_type, target_id=target_id)
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.order_by("created_at")
