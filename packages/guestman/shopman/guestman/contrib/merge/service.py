"""MergeService — consolidate two customer records into one."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from shopman.guestman.exceptions import CustomerError
from shopman.guestman.gates import Gates
from shopman.guestman.models import (
    ContactPoint,
    Customer,
    CustomerAddress,
    ExternalIdentity,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MergeResult:
    """Summary of a completed merge."""

    source_ref: str
    target_ref: str
    migrated_contact_points: int
    migrated_external_identities: int
    migrated_identifiers: int
    migrated_addresses: int
    migrated_preferences: int
    migrated_consents: int
    migrated_timeline_events: int
    loyalty_merged: bool
    audit_id: str = ""


class MergeService:
    """
    Service for merging duplicate customers.

    Consolidates all related data from source into target, then
    deactivates the source. Requires strong evidence (Gate G6).

    All operations run inside a single transaction.atomic().
    """

    @classmethod
    def merge(
        cls,
        source_customer: Customer,
        target_customer: Customer,
        evidence: dict,
        actor: str = "",
    ) -> MergeResult:
        """
        Merge source_customer into target_customer.

        Args:
            source_customer: Customer to be deactivated (donor).
            target_customer: Customer to receive all data (survivor).
            evidence: Dict with evidence keys for G6 gate.
            actor: Who initiated the merge (audit trail).

        Returns:
            MergeResult with counts of migrated records.

        Raises:
            CustomerError: If gate validation fails or customers are invalid.
        """
        # --- Validate via G6 ---
        Gates.merge_safety(
            source_id=str(source_customer.pk),
            target_id=str(target_customer.pk),
            evidence=evidence,
        )

        if not source_customer.is_active:
            raise CustomerError(
                "MERGE_DENIED",
                message="Source customer is already inactive.",
            )
        if not target_customer.is_active:
            raise CustomerError(
                "MERGE_DENIED",
                message="Target customer is inactive.",
            )

        with transaction.atomic():
            # Lock both rows to prevent concurrent modifications
            source = Customer.objects.select_for_update().get(pk=source_customer.pk)
            target = Customer.objects.select_for_update().get(pk=target_customer.pk)

            # Snapshot tracks migrated PKs for undo
            snapshot: dict[str, list] = {}

            counts = {
                "contact_points": cls._migrate_contact_points(source, target, snapshot),
                "external_identities": cls._migrate_external_identities(source, target, snapshot),
                "identifiers": cls._migrate_identifiers(source, target, snapshot),
                "addresses": cls._migrate_addresses(source, target, snapshot),
                "preferences": cls._migrate_preferences(source, target, snapshot),
                "consents": cls._migrate_consents(source, target, snapshot),
                "timeline_events": cls._migrate_timeline_events(source, target, snapshot),
            }
            loyalty_merged = cls._merge_loyalty(source, target, snapshot)

            # Recalculate insights for target
            cls._recalculate_insights(target)

            # Audit trail — timeline event on target
            cls._log_merge_event(source, target, evidence, actor)

            # Deactivate source — use .update() to bypass _sync_contact_points()
            # which would fail since source's CPs were migrated to target.
            merge_note = f"{source.notes}\n[MERGED] → {target.ref} by {actor}".strip()
            Customer.objects.filter(pk=source.pk).update(
                is_active=False,
                notes=merge_note,
            )
            source.refresh_from_db()

            # Create audit record
            audit = cls._create_audit(source, target, evidence, actor, counts, loyalty_merged, snapshot)

        logger.info(
            "Merged customer %s → %s by %s: %s (audit=%s)",
            source.ref,
            target.ref,
            actor,
            counts,
            audit.pk,
        )

        return MergeResult(
            source_ref=source.ref,
            target_ref=target.ref,
            migrated_contact_points=counts["contact_points"],
            migrated_external_identities=counts["external_identities"],
            migrated_identifiers=counts["identifiers"],
            migrated_addresses=counts["addresses"],
            migrated_preferences=counts["preferences"],
            migrated_consents=counts["consents"],
            migrated_timeline_events=counts["timeline_events"],
            loyalty_merged=loyalty_merged,
            audit_id=str(audit.pk),
        )

    @classmethod
    def undo(cls, audit_id: str, actor: str = "") -> None:
        """
        Partially revert a merge within the undo window.

        Moves migrated records back to the source customer and
        reactivates it. Loyalty is NOT reverted (too complex, manual only).

        Args:
            audit_id: UUID of the MergeAudit record.
            actor: Who initiated the undo.

        Raises:
            CustomerError: If audit not found, already reverted, or window expired.
        """
        from shopman.guestman.contrib.merge.models import MergeAudit, MergeStatus

        try:
            audit = MergeAudit.objects.get(pk=audit_id)
        except MergeAudit.DoesNotExist:
            raise CustomerError("UNDO_FAILED", message="Merge audit record not found.")

        if audit.status != MergeStatus.COMPLETED:
            raise CustomerError("UNDO_FAILED", message="Merge already reverted.")

        if not audit.can_undo:
            raise CustomerError(
                "UNDO_FAILED",
                message=f"Undo window expired at {audit.undo_deadline}.",
            )

        with transaction.atomic():
            source = Customer.objects.select_for_update().get(pk=audit.source_id)
            target = Customer.objects.select_for_update().get(pk=audit.target_id)

            snapshot = audit.snapshot

            # Revert contact points
            cp_pks = snapshot.get("contact_points", [])
            if cp_pks:
                ContactPoint.objects.filter(pk__in=cp_pks, customer=target).update(
                    customer=source,
                )

            # Revert external identities
            eid_pks = snapshot.get("external_identities", [])
            if eid_pks:
                ExternalIdentity.objects.filter(pk__in=eid_pks, customer=target).update(
                    customer=source,
                )

            # Revert identifiers
            ident_pks = snapshot.get("identifiers", [])
            if ident_pks:
                try:
                    from shopman.guestman.contrib.identifiers.models import CustomerIdentifier

                    CustomerIdentifier.objects.filter(pk__in=ident_pks, customer=target).update(
                        customer=source,
                    )
                except ImportError:
                    pass

            # Revert addresses
            addr_pks = snapshot.get("addresses", [])
            if addr_pks:
                CustomerAddress.objects.filter(pk__in=addr_pks, customer=target).update(
                    customer=source,
                )

            # Revert preferences
            pref_pks = snapshot.get("preferences", [])
            if pref_pks:
                try:
                    from shopman.guestman.contrib.preferences.models import CustomerPreference

                    CustomerPreference.objects.filter(pk__in=pref_pks, customer=target).update(
                        customer=source,
                    )
                except ImportError:
                    pass

            # Revert consents (only non-conflicting ones that were moved)
            consent_pks = snapshot.get("consents_moved", [])
            if consent_pks:
                try:
                    from shopman.guestman.contrib.consent.models import CommunicationConsent

                    CommunicationConsent.objects.filter(pk__in=consent_pks, customer=target).update(
                        customer=source,
                    )
                except ImportError:
                    pass

            # Revert timeline events
            te_pks = snapshot.get("timeline_events", [])
            if te_pks:
                try:
                    from shopman.guestman.contrib.timeline.models import TimelineEvent

                    TimelineEvent.objects.filter(pk__in=te_pks, customer=target).update(
                        customer=source,
                    )
                except ImportError:
                    pass

            # NOTE: Loyalty is NOT reverted automatically — too complex.
            # Manual adjustment via LoyaltyService if needed.

            # Reactivate source
            Customer.objects.filter(pk=source.pk).update(is_active=True)

            # Log undo event on target timeline
            cls._log_undo_event(source, target, actor)

            # Update audit
            audit.status = MergeStatus.REVERTED
            audit.reverted_at = timezone.now()
            audit.reverted_by = actor
            audit.save(update_fields=["status", "reverted_at", "reverted_by"])

        logger.info("Reverted merge %s (audit=%s) by %s", audit, audit.pk, actor)

    # ======================================================================
    # Audit
    # ======================================================================

    @classmethod
    def _create_audit(
        cls,
        source: Customer,
        target: Customer,
        evidence: dict,
        actor: str,
        counts: dict,
        loyalty_merged: bool,
        snapshot: dict,
    ):
        from shopman.guestman.contrib.merge.models import MergeAudit

        return MergeAudit.objects.create(
            source_ref=source.ref,
            target_ref=target.ref,
            source_id=source.pk,
            target_id=target.pk,
            actor=actor,
            evidence={k: v for k, v in evidence.items() if v},
            snapshot=snapshot,
            migrated_contact_points=counts["contact_points"],
            migrated_external_identities=counts["external_identities"],
            migrated_identifiers=counts["identifiers"],
            migrated_addresses=counts["addresses"],
            migrated_preferences=counts["preferences"],
            migrated_consents=counts["consents"],
            migrated_timeline_events=counts["timeline_events"],
            loyalty_merged=loyalty_merged,
        )

    # ======================================================================
    # Migration helpers
    # ======================================================================

    @classmethod
    def _migrate_contact_points(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """
        Migrate contact points from source to target.

        Strategy:
        - If target already has the same (type, value_normalized), skip (source's is deleted).
        - If source CP is_primary but target already has a primary for that type,
          demote source's to non-primary before moving.
        """
        source_cps = list(source.contact_points.all())
        migrated = 0
        moved_pks: list[str] = []

        for cp in source_cps:
            # Check if target already has this exact contact
            duplicate = ContactPoint.objects.filter(
                customer=target,
                type=cp.type,
                value_normalized=cp.value_normalized,
            ).exists()

            if duplicate:
                # Target already has it — delete source's copy
                cp.delete()
                continue

            # Check global uniqueness — another customer might have this value
            global_exists = ContactPoint.objects.filter(
                type=cp.type,
                value_normalized=cp.value_normalized,
            ).exclude(pk=cp.pk).exists()

            if global_exists:
                # Can't move — unique constraint would fail, delete source's
                cp.delete()
                continue

            # If source's CP is primary, check if target already has a primary for this type
            if cp.is_primary:
                target_has_primary = ContactPoint.objects.filter(
                    customer=target,
                    type=cp.type,
                    is_primary=True,
                ).exists()
                if target_has_primary:
                    cp.is_primary = False

            cp.customer = target
            cp.save(update_fields=["customer", "is_primary", "updated_at"])
            moved_pks.append(str(cp.pk))
            migrated += 1

        snapshot["contact_points"] = moved_pks
        return migrated

    @classmethod
    def _migrate_external_identities(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """
        Migrate external identities from source to target.

        Skip duplicates (same provider+uid already on target).
        """
        source_ids = list(source.external_identities.all())
        migrated = 0
        moved_pks: list[str] = []

        for eid in source_ids:
            duplicate = ExternalIdentity.objects.filter(
                customer=target,
                provider=eid.provider,
                provider_uid=eid.provider_uid,
            ).exists()

            if duplicate:
                eid.delete()
                continue

            eid.customer = target
            try:
                eid.save(update_fields=["customer", "updated_at"])
                moved_pks.append(str(eid.pk))
                migrated += 1
            except IntegrityError:
                # Global unique constraint (provider, provider_uid) — skip
                logger.warning(
                    "Merge: skipped external identity %s/%s (integrity error)",
                    eid.provider,
                    eid.provider_uid,
                )

        snapshot["external_identities"] = moved_pks
        return migrated

    @classmethod
    def _migrate_identifiers(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """
        Migrate CustomerIdentifiers from source to target.

        Skip if target already has identifier with same (type, value).
        Demote is_primary if target already has a primary of that type.
        """
        try:
            from shopman.guestman.contrib.identifiers.models import CustomerIdentifier
        except ImportError:
            snapshot["identifiers"] = []
            return 0

        source_ids = list(CustomerIdentifier.objects.filter(customer=source))
        migrated = 0
        moved_pks: list[str] = []

        for ident in source_ids:
            duplicate = CustomerIdentifier.objects.filter(
                customer=target,
                identifier_type=ident.identifier_type,
                identifier_value=ident.identifier_value,
            ).exists()

            if duplicate:
                ident.delete()
                continue

            # Check global uniqueness
            global_exists = CustomerIdentifier.objects.filter(
                identifier_type=ident.identifier_type,
                identifier_value=ident.identifier_value,
            ).exclude(pk=ident.pk).exists()

            if global_exists:
                ident.delete()
                continue

            if ident.is_primary:
                target_has_primary = CustomerIdentifier.objects.filter(
                    customer=target,
                    identifier_type=ident.identifier_type,
                    is_primary=True,
                ).exists()
                if target_has_primary:
                    ident.is_primary = False

            ident.customer = target
            ident.save(update_fields=["customer", "is_primary"])
            moved_pks.append(str(ident.pk))
            migrated += 1

        snapshot["identifiers"] = moved_pks
        return migrated

    @classmethod
    def _migrate_addresses(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """
        Migrate addresses from source to target.

        If source address is_default but target already has a default,
        demote source's.
        """
        source_addrs = list(source.addresses.all())
        migrated = 0
        moved_pks: list[str] = []

        for addr in source_addrs:
            if addr.is_default:
                target_has_default = CustomerAddress.objects.filter(
                    customer=target,
                    is_default=True,
                ).exists()
                if target_has_default:
                    addr.is_default = False

            addr.customer = target
            addr.save(update_fields=["customer", "is_default", "updated_at"])
            moved_pks.append(str(addr.pk))
            migrated += 1

        snapshot["addresses"] = moved_pks
        return migrated

    @classmethod
    def _migrate_preferences(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """
        Migrate preferences. Target wins on conflict (same category+key).
        """
        try:
            from shopman.guestman.contrib.preferences.models import CustomerPreference
        except ImportError:
            snapshot["preferences"] = []
            return 0

        source_prefs = list(CustomerPreference.objects.filter(customer=source))
        migrated = 0
        moved_pks: list[str] = []

        for pref in source_prefs:
            conflict = CustomerPreference.objects.filter(
                customer=target,
                category=pref.category,
                key=pref.key,
            ).exists()

            if conflict:
                # Target wins — discard source's preference
                pref.delete()
                continue

            pref.customer = target
            pref.save(update_fields=["customer", "updated_at"])
            moved_pks.append(str(pref.pk))
            migrated += 1

        snapshot["preferences"] = moved_pks
        return migrated

    @classmethod
    def _migrate_consents(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """
        Migrate consents. More restrictive wins on conflict.

        Restrictiveness order: opted_out > pending > opted_in.
        If source is more restrictive, update target's record.
        """
        try:
            from shopman.guestman.contrib.consent.models import (
                CommunicationConsent,
                ConsentStatus,
            )
        except ImportError:
            snapshot["consents_moved"] = []
            return 0

        _RESTRICTIVENESS = {
            ConsentStatus.OPTED_OUT: 3,
            ConsentStatus.PENDING: 2,
            ConsentStatus.OPTED_IN: 1,
        }

        source_consents = list(CommunicationConsent.objects.filter(customer=source))
        migrated = 0
        moved_pks: list[str] = []  # Only non-conflict moves (reversible)

        for consent in source_consents:
            try:
                target_consent = CommunicationConsent.objects.get(
                    customer=target,
                    channel=consent.channel,
                )
            except CommunicationConsent.DoesNotExist:
                # No conflict — move to target
                consent.customer = target
                consent.save(update_fields=["customer", "updated_at"])
                moved_pks.append(str(consent.pk))
                migrated += 1
                continue

            # Conflict — more restrictive wins
            source_level = _RESTRICTIVENESS.get(consent.status, 0)
            target_level = _RESTRICTIVENESS.get(target_consent.status, 0)

            if source_level > target_level:
                target_consent.status = consent.status
                target_consent.revoked_at = consent.revoked_at
                target_consent.save(update_fields=["status", "revoked_at", "updated_at"])

            # Either way, delete source's consent record
            consent.delete()
            migrated += 1

        snapshot["consents_moved"] = moved_pks
        return migrated

    @classmethod
    def _migrate_timeline_events(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> int:
        """Reassign all timeline events from source to target."""
        try:
            from shopman.guestman.contrib.timeline.models import TimelineEvent
        except ImportError:
            snapshot["timeline_events"] = []
            return 0

        event_pks = list(
            TimelineEvent.objects.filter(customer=source).values_list("pk", flat=True)
        )
        count = TimelineEvent.objects.filter(pk__in=event_pks).update(customer=target)
        snapshot["timeline_events"] = [str(pk) for pk in event_pks]
        return count

    @classmethod
    def _merge_loyalty(
        cls, source: Customer, target: Customer, snapshot: dict
    ) -> bool:
        """
        Merge loyalty accounts: sum points, keep higher tier.

        Source's transactions are reassigned to target's account.
        """
        try:
            from shopman.guestman.contrib.loyalty.models import (
                LoyaltyAccount,
                LoyaltyTransaction,
                LoyaltyTier,
                TransactionType,
            )
        except ImportError:
            return False

        try:
            source_account = LoyaltyAccount.objects.select_for_update().get(
                customer=source,
            )
        except LoyaltyAccount.DoesNotExist:
            return False

        # Get or create target account
        target_account, _ = LoyaltyAccount.objects.get_or_create(
            customer=target,
        )
        target_account = LoyaltyAccount.objects.select_for_update().get(
            pk=target_account.pk,
        )

        # Save pre-merge state for reference (loyalty undo is manual)
        snapshot["loyalty"] = {
            "source_account_id": str(source_account.pk),
            "target_account_id": str(target_account.pk),
            "source_points": source_account.points_balance,
            "source_lifetime": source_account.lifetime_points,
            "source_stamps": source_account.stamps_current,
            "source_stamps_completed": source_account.stamps_completed,
            "source_tier": source_account.tier,
            "target_points_before": target_account.points_balance,
            "target_tier_before": target_account.tier,
        }

        # Sum points
        target_account.points_balance += source_account.points_balance
        target_account.lifetime_points += source_account.lifetime_points

        # Sum stamps
        target_account.stamps_current += source_account.stamps_current
        target_account.stamps_completed += source_account.stamps_completed

        # Keep higher tier
        _TIER_ORDER = {
            LoyaltyTier.BRONZE: 0,
            LoyaltyTier.SILVER: 1,
            LoyaltyTier.GOLD: 2,
            LoyaltyTier.PLATINUM: 3,
        }
        if _TIER_ORDER.get(source_account.tier, 0) > _TIER_ORDER.get(target_account.tier, 0):
            target_account.tier = source_account.tier

        target_account.save(update_fields=[
            "points_balance",
            "lifetime_points",
            "stamps_current",
            "stamps_completed",
            "tier",
            "updated_at",
        ])

        # Reassign transactions to target account
        LoyaltyTransaction.objects.filter(account=source_account).update(
            account=target_account,
        )

        # Record a merge adjustment transaction
        LoyaltyTransaction.objects.create(
            account=target_account,
            transaction_type=TransactionType.ADJUST,
            points=source_account.points_balance,
            balance_after=target_account.points_balance,
            description=f"Merge: absorbed {source.ref}",
            reference=f"merge:{source.ref}",
        )

        # Deactivate source account
        source_account.is_active = False
        source_account.save(update_fields=["is_active", "updated_at"])

        return True

    @classmethod
    def _recalculate_insights(cls, target: Customer) -> None:
        """Recalculate insights for the merged target customer."""
        try:
            from shopman.guestman.contrib.insights.service import InsightService

            InsightService.recalculate(target.ref)
        except ImportError:
            pass
        except Exception as exc:
            # Non-fatal — insights can be recalculated later
            logger.warning(
                "Merge: could not recalculate insights for %s: %s",
                target.ref,
                exc,
            )

    @classmethod
    def _log_merge_event(
        cls,
        source: Customer,
        target: Customer,
        evidence: dict,
        actor: str,
    ) -> None:
        """Record the merge as a timeline event on the target."""
        try:
            from shopman.guestman.contrib.timeline.models import EventType, TimelineEvent

            TimelineEvent.objects.create(
                customer=target,
                event_type=EventType.SYSTEM,
                title=f"Merge: {source.ref} → {target.ref}",
                description=(
                    f"Customer {source.ref} ({source.name}) merged into "
                    f"{target.ref} ({target.name})."
                ),
                channel="admin",
                reference=f"merge:{source.ref}",
                metadata={
                    "source_ref": source.ref,
                    "source_name": source.name,
                    "evidence": {k: v for k, v in evidence.items() if v},
                },
                created_by=actor,
            )
        except ImportError:
            pass

    @classmethod
    def _log_undo_event(
        cls,
        source: Customer,
        target: Customer,
        actor: str,
    ) -> None:
        """Record the undo as a timeline event on the target."""
        try:
            from shopman.guestman.contrib.timeline.models import EventType, TimelineEvent

            TimelineEvent.objects.create(
                customer=target,
                event_type=EventType.SYSTEM,
                title=f"Merge reverted: {source.ref} ← {target.ref}",
                description=(
                    f"Merge of {source.ref} into {target.ref} was reverted."
                ),
                channel="admin",
                reference=f"undo-merge:{source.ref}",
                metadata={"source_ref": source.ref, "target_ref": target.ref},
                created_by=actor,
            )
        except ImportError:
            pass
