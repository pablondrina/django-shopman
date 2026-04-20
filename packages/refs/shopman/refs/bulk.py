"""
Bulk ref operations — rename, cascade_rename, migrate_target, deactivate_scope, find_orphaned.

All write operations run in transaction.atomic() with select_for_update().
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.apps import apps
from django.db import transaction
from django.utils import timezone

from shopman.refs.models import Ref
from shopman.refs.registry import _ref_source_registry, get_ref_type
from shopman.refs.services import _build_scope_filter, _coerce_target, _normalize_value
from shopman.refs.signals import ref_deactivated, ref_renamed

if TYPE_CHECKING:
    pass

logger = logging.getLogger("shopman.refs")


class RefBulk:
    """Bulk operations on Refs and RefField sources."""

    @classmethod
    def rename(
        cls,
        ref_type: str,
        old_value: str,
        new_value: str,
        scope: dict | None = None,
        actor: str = "",
    ) -> int:
        """Rename a ref value across all matching Refs.

        Normalizes both old_value and new_value using the RefType's normalizer (if registered).
        If scope is provided, only refs matching that scope are updated.

        Args:
            ref_type: RefType slug.
            old_value: Current value to find.
            new_value: Replacement value.
            scope: Optional scope filter. None = rename across all scopes.
            actor: Who is performing the rename (logged + stored in structured log).

        Returns:
            Number of Refs updated.
        """
        rt = get_ref_type(ref_type)
        normalizer = rt.normalizer if rt else "none"
        old_norm = _normalize_value(old_value, normalizer)
        new_norm = _normalize_value(new_value, normalizer)

        with transaction.atomic():
            qs = Ref.objects.select_for_update().filter(ref_type=ref_type, value=old_norm)

            if scope is not None and rt and rt.scope_keys:
                filt = _build_scope_filter(scope, rt.scope_keys)
                if filt:
                    qs = qs.filter(**filt)

            refs = list(qs)  # fetch before update for signal emission
            count = qs.update(value=new_norm)

            for ref in refs:
                ref.value = new_norm
                ref_renamed.send(
                    sender=Ref,
                    ref=ref,
                    old_value=old_norm,
                    actor=actor,
                )

        logger.info(
            "refs.bulk.renamed",
            extra={
                "ref_type": ref_type,
                "old_value": old_norm,
                "new_value": new_norm,
                "count": count,
                "actor": actor,
            },
        )
        return count

    @classmethod
    def cascade_rename(
        cls,
        ref_type: str,
        old_value: str,
        new_value: str,
        actor: str = "",
    ) -> int:
        """Rename a ref value in the Ref table AND in all registered RefField sources.

        Uses RefSourceRegistry to find all (model, field) pairs that store values
        of this ref_type, then bulk-updates them alongside the Ref table.

        Args:
            ref_type: RefType slug.
            old_value: Current value to find.
            new_value: Replacement value.
            actor: Who is performing the rename.

        Returns:
            Total number of rows updated (Refs + model field rows combined).
        """
        rt = get_ref_type(ref_type)
        normalizer = rt.normalizer if rt else "none"
        old_norm = _normalize_value(old_value, normalizer)
        new_norm = _normalize_value(new_value, normalizer)

        total = 0

        with transaction.atomic():
            # 1. Update Ref table (no scope filter — cascade affects all)
            ref_qs = Ref.objects.select_for_update().filter(ref_type=ref_type, value=old_norm)
            refs = list(ref_qs)
            ref_count = ref_qs.update(value=new_norm)
            total += ref_count

            for ref in refs:
                ref.value = new_norm
                ref_renamed.send(sender=Ref, ref=ref, old_value=old_norm, actor=actor)

            # 2. Update all registered RefField sources
            sources = _ref_source_registry.get_sources_for_type(ref_type)
            for model_label, field_name in sources:
                try:
                    app_label, model_name = model_label.split(".", 1)
                    Model = apps.get_model(app_label, model_name)
                except (ValueError, LookupError):
                    logger.warning(
                        "refs.bulk.cascade_rename.model_not_found",
                        extra={"model": model_label, "ref_type": ref_type},
                    )
                    continue

                field_count = Model.objects.filter(**{field_name: old_norm}).update(
                    **{field_name: new_norm}
                )
                total += field_count
                if field_count:
                    logger.info(
                        "refs.bulk.cascade_rename.field_updated",
                        extra={
                            "model": model_label,
                            "field": field_name,
                            "count": field_count,
                            "actor": actor,
                        },
                    )

        logger.info(
            "refs.bulk.cascade_renamed",
            extra={
                "ref_type": ref_type,
                "old_value": old_norm,
                "new_value": new_norm,
                "total": total,
                "actor": actor,
            },
        )
        return total

    @classmethod
    def migrate_target(
        cls,
        old_target: str,
        new_target: str,
        actor: str = "",
    ) -> int:
        """Move all refs from old_target to new_target.

        Transfers both active and inactive refs so the full history follows
        the new target (primary use case: customer/session merge).

        Args:
            old_target: Source target string "app_label.ModelName:pk" or model instance.
            new_target: Destination target string or model instance.
            actor: Who is performing the migration (logged).

        Returns:
            Number of Refs migrated.
        """
        src_type, src_id = _coerce_target(old_target)
        dst_type, dst_id = _coerce_target(new_target)

        with transaction.atomic():
            qs = Ref.objects.select_for_update().filter(
                target_type=src_type, target_id=src_id
            )
            count = qs.count()
            qs.update(target_type=dst_type, target_id=dst_id)

        if count:
            logger.info(
                "refs.bulk.target_migrated",
                extra={
                    "from": f"{src_type}:{src_id}",
                    "to": f"{dst_type}:{dst_id}",
                    "count": count,
                    "actor": actor,
                },
            )
        return count

    @classmethod
    def deactivate_scope(
        cls,
        ref_type: str,
        scope: dict,
        actor: str = "",
    ) -> int:
        """Deactivate all active refs for a ref_type within a scope.

        Primary use case: end-of-day close — deactivate all POS_TABLE refs
        for a given store+business_date.

        Args:
            ref_type: RefType slug.
            scope: Scope dict. All scope_keys must be present (validated against RefType).
            actor: Who is performing the deactivation (stored in deactivated_by).

        Returns:
            Number of Refs deactivated.
        """
        rt = get_ref_type(ref_type)
        now = timezone.now()

        qs = Ref.objects.filter(ref_type=ref_type, is_active=True)

        if rt and rt.scope_keys:
            filt = _build_scope_filter(scope, rt.scope_keys)
            if filt:
                qs = qs.filter(**filt)
        else:
            # No scope_keys defined — filter by all provided scope keys
            filt = {f"scope__{k}": v for k, v in scope.items()}
            if filt:
                qs = qs.filter(**filt)

        refs = list(qs)  # fetch before update for signal emission
        count = qs.update(is_active=False, deactivated_at=now, deactivated_by=actor)

        for ref in refs:
            ref.is_active = False
            ref.deactivated_at = now
            ref.deactivated_by = actor
            ref_deactivated.send(sender=Ref, ref=ref, actor=actor)

        if count:
            logger.info(
                "refs.bulk.scope_deactivated",
                extra={
                    "ref_type": ref_type,
                    "scope": scope,
                    "count": count,
                    "actor": actor,
                },
            )
        return count

    @classmethod
    def find_orphaned(cls, ref_type: str | None = None) -> list[Ref]:
        """Find Refs whose target entity no longer exists.

        Groups Refs by target_type, then for each type checks which target_ids
        are missing from the model's table. Also includes Refs with unresolvable
        target_types (unknown app/model).

        Args:
            ref_type: Optional filter to a specific ref_type slug.

        Returns:
            List of Ref instances whose target does not exist.
        """
        qs = Ref.objects.all()
        if ref_type:
            qs = qs.filter(ref_type=ref_type)

        orphaned: list[Ref] = []

        for ttype in qs.values_list("target_type", flat=True).distinct():
            refs_of_type = list(qs.filter(target_type=ttype))
            target_ids = {ref.target_id for ref in refs_of_type}

            try:
                app_label, model_name = ttype.split(".", 1)
                Model = apps.get_model(app_label, model_name)
            except (ValueError, LookupError):
                # Unresolvable model — all refs with this target_type are orphaned
                orphaned.extend(refs_of_type)
                continue

            existing_ids = {
                str(pk)
                for pk in Model.objects.filter(pk__in=list(target_ids)).values_list("pk", flat=True)
            }

            orphaned.extend(ref for ref in refs_of_type if ref.target_id not in existing_ids)

        return orphaned
