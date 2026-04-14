"""Management command to cleanup old processed events."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from shopman.guestman.models import ProcessedEvent


class Command(BaseCommand):
    help = "Remove processed events older than EVENT_CLEANUP_DAYS"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Override EVENT_CLEANUP_DAYS setting",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many events would be deleted without deleting",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days is None:
            from shopman.guestman.conf import guestman_settings
            days = guestman_settings.EVENT_CLEANUP_DAYS

        cutoff = timezone.now() - timedelta(days=days)
        qs = ProcessedEvent.objects.filter(processed_at__lt=cutoff)

        if options["dry_run"]:
            count = qs.count()
            self.stdout.write(f"Would delete {count} processed events older than {days} days.")
            return

        deleted_count, _ = qs.delete()
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {deleted_count} old processed events.")
        )
