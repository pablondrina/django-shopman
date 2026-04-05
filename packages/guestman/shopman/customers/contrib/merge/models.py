"""MergeAudit — audit trail + undo snapshot for customer merges."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class MergeStatus(models.TextChoices):
    COMPLETED = "completed", "Completed"
    REVERTED = "reverted", "Reverted"


class MergeAudit(models.Model):
    """
    Audit trail for customer merges.

    Stores a snapshot of what was migrated so the merge can be
    partially reverted within the UNDO_WINDOW.
    """

    UNDO_WINDOW_HOURS = 24

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Who was merged
    source_ref = models.CharField(max_length=50)
    target_ref = models.CharField(max_length=50)
    source_id = models.UUIDField()
    target_id = models.UUIDField()

    # Audit info
    actor = models.CharField(max_length=200, blank=True)
    evidence = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=MergeStatus.choices,
        default=MergeStatus.COMPLETED,
    )

    # Snapshot of migrated PKs (for undo)
    snapshot = models.JSONField(
        default=dict,
        help_text="PKs of migrated records by category, for undo.",
    )

    # Counts (denormalized for quick reference)
    migrated_contact_points = models.PositiveIntegerField(default=0)
    migrated_external_identities = models.PositiveIntegerField(default=0)
    migrated_identifiers = models.PositiveIntegerField(default=0)
    migrated_addresses = models.PositiveIntegerField(default=0)
    migrated_preferences = models.PositiveIntegerField(default=0)
    migrated_consents = models.PositiveIntegerField(default=0)
    migrated_timeline_events = models.PositiveIntegerField(default=0)
    loyalty_merged = models.BooleanField(default=False)

    # Timestamps
    merged_at = models.DateTimeField(default=timezone.now)
    reverted_at = models.DateTimeField(null=True, blank=True)
    reverted_by = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-merged_at"]
        indexes = [
            models.Index(fields=["source_ref"], name="customers_merge_src_ref"),
            models.Index(fields=["target_ref"], name="customers_merge_tgt_ref"),
        ]

    def __str__(self) -> str:
        return f"Merge {self.source_ref} → {self.target_ref} ({self.status})"

    @property
    def can_undo(self) -> bool:
        """Check if merge is within the undo window."""
        if self.status != MergeStatus.COMPLETED:
            return False
        from datetime import timedelta

        deadline = self.merged_at + timedelta(hours=self.UNDO_WINDOW_HOURS)
        return timezone.now() < deadline

    @property
    def undo_deadline(self):
        """When the undo window expires."""
        from datetime import timedelta

        return self.merged_at + timedelta(hours=self.UNDO_WINDOW_HOURS)
