"""
Management command: cleanup_stale_planning

Removes planning quants (``target_date < today``, ``position IS NULL``) that
never materialized and have no active holds or moves linked. They accumulate
when a WorkOrder is cancelled/forgotten before Craftsman transfers its
planned quant to a physical position — the quant stays orphaned and is
filtered out of the active cycle by :func:`quants_eligible_for`, but still
sits in the database.

Idempotent: safe to run on a schedule.

Usage::

    python manage.py cleanup_stale_planning
    python manage.py cleanup_stale_planning --dry-run
"""

from __future__ import annotations

import logging
from datetime import date

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Remove planning quants com target_date passada, sem posição e sem holds/moves."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Lista os quants candidatos sem deletar.",
        )

    def handle(self, *args, **options):
        from shopman.stockman import Hold, HoldStatus
        from shopman.stockman.models import Move, Quant

        today = date.today()
        dry_run = options["dry_run"]

        active_holds = Hold.objects.filter(
            quant_id=OuterRef("pk"),
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
        )
        any_move = Move.objects.filter(quant_id=OuterRef("pk"))

        stale = (
            Quant.objects.filter(
                target_date__lt=today,
                position__isnull=True,
            )
            .annotate(has_holds=Exists(active_holds))
            .annotate(has_moves=Exists(any_move))
            .filter(has_holds=False, has_moves=False)
        )

        total = stale.count()
        if dry_run:
            for q in stale[:50]:
                self.stdout.write(
                    f"  - Quant#{q.pk} sku={q.sku} target={q.target_date} qty={q._quantity}"
                )
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] {total} quant(s) de planejamento ficariam para remoção."
                )
            )
            return

        deleted, _ = stale.delete()
        logger.info("stock.cleanup_stale_planning: removed %s quants", deleted)
        self.stdout.write(
            self.style.SUCCESS(f"Removidos {deleted} quant(s) de planejamento órfãos.")
        )
