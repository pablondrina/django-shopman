"""
Management command: cleanup_stale_sessions

Deletes ordering Sessions that have no associated Order and haven't been
updated in the last 48 hours. Prevents indefinite accumulation of
abandoned sessions.

Usage:
    python manage.py cleanup_stale_sessions
    python manage.py cleanup_stale_sessions --hours 24
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Remove sessions sem pedido inativas há mais de 48h (configurável)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=48,
            help="Horas de inatividade antes de remover (default: 48)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Apenas conta, sem remover.",
        )

    def handle(self, *args, **options):
        from django.db.models import Exists, OuterRef

        from shopman.ordering.models import Order, Session

        hours = options["hours"]
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timedelta(hours=hours)

        # Exclude sessions that have an associated Order (matched by session_key)
        has_order = Order.objects.filter(session_key=OuterRef("session_key"))
        stale = Session.objects.filter(
            updated_at__lt=cutoff,
        ).exclude(Exists(has_order))
        count = stale.count()

        if dry_run:
            self.stdout.write(f"[dry-run] {count} sessions seriam removidas.")
            return

        if count == 0:
            self.stdout.write("Nenhuma session stale encontrada.")
            return

        deleted, _ = stale.delete()
        logger.info("cleanup_stale_sessions: removed %d sessions (cutoff=%s)", deleted, cutoff)
        self.stdout.write(self.style.SUCCESS(f"Removidas {deleted} sessions stale (> {hours}h sem atividade)."))
