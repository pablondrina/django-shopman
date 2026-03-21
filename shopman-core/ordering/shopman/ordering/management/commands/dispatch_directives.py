"""Management command to dispatch pending directives."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from shopman.ordering.dispatch import dispatch_pending_directives
from shopman.ordering.models import Directive


class Command(BaseCommand):
    help = "Dispatch pending directives (queued with available_at in the past)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List pending directives without processing them.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            now = timezone.now()
            pending = Directive.objects.filter(
                status="queued", available_at__lte=now,
            ).order_by("available_at", "id")
            count = pending.count()
            for d in pending:
                self.stdout.write(
                    f"  [{d.pk}] topic={d.topic} attempts={d.attempts} "
                    f"available_at={d.available_at}"
                )
            self.stdout.write(f"{count} pending directive(s) (dry-run, nothing processed).")
            return

        processed = dispatch_pending_directives()
        self.stdout.write(f"{processed} directive(s) dispatched.")
