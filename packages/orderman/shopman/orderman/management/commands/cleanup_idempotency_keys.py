"""
Management command para limpar IdempotencyKeys expiradas.

Uso:
    python manage.py cleanup_idempotency_keys
    python manage.py cleanup_idempotency_keys --days 7
    python manage.py cleanup_idempotency_keys --dry-run

Recomendação: Agendar via cron para executar diariamente.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from shopman.orderman.models import IdempotencyKey


class Command(BaseCommand):
    help = "Remove IdempotencyKeys expiradas ou antigas"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Remove keys mais antigas que N dias (default: 7)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra o que seria removido sem remover",
        )
        parser.add_argument(
            "--include-in-progress",
            action="store_true",
            help="Também remove keys 'in_progress' antigas (possíveis órfãs)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        include_in_progress = options["include_in_progress"]

        cutoff = timezone.now() - timedelta(days=days)
        now = timezone.now()

        # 1. Keys com expires_at definido e expirado
        expired_qs = IdempotencyKey.objects.filter(expires_at__lt=now)
        expired_count = expired_qs.count()

        # 2. Keys antigas (criadas há mais de N dias)
        old_qs = IdempotencyKey.objects.filter(
            created_at__lt=cutoff,
            status__in=["done", "failed"],
        )
        old_count = old_qs.count()

        # 3. Keys "in_progress" antigas (possíveis órfãs de processos interrompidos)
        orphan_count = 0
        if include_in_progress:
            # Keys in_progress há mais de 1 hora provavelmente são órfãs
            orphan_cutoff = timezone.now() - timedelta(hours=1)
            orphan_qs = IdempotencyKey.objects.filter(
                created_at__lt=orphan_cutoff,
                status="in_progress",
            )
            orphan_count = orphan_qs.count()

        total = expired_count + old_count + orphan_count

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"[DRY RUN] Seriam removidas {total} keys:")
            )
            self.stdout.write(f"  - {expired_count} expiradas (expires_at < now)")
            self.stdout.write(f"  - {old_count} antigas (> {days} dias, done/failed)")
            if include_in_progress:
                self.stdout.write(f"  - {orphan_count} órfãs (in_progress > 1h)")
            return

        # Executar deleção
        deleted = 0

        if expired_count > 0:
            count, _ = expired_qs.delete()
            deleted += count
            self.stdout.write(f"Removidas {count} keys expiradas")

        if old_count > 0:
            count, _ = old_qs.delete()
            deleted += count
            self.stdout.write(f"Removidas {count} keys antigas")

        if include_in_progress and orphan_count > 0:
            count, _ = orphan_qs.delete()
            deleted += count
            self.stdout.write(f"Removidas {count} keys órfãs")

        self.stdout.write(
            self.style.SUCCESS(f"Total removido: {deleted} IdempotencyKeys")
        )
