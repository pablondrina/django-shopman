"""
Management command to clean up expired tokens, codes, and device trusts.

Usage:
    python manage.py auth_cleanup
    python manage.py auth_cleanup --days=30
    python manage.py auth_cleanup --dry-run
"""

from django.core.management.base import BaseCommand
from shopman.doorman.services.access_link import AccessLinkService
from shopman.doorman.services.device_trust import DeviceTrustService
from shopman.doorman.services.verification import AuthService


class Command(BaseCommand):
    help = "Clean up expired access links, verification codes, and device trusts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Delete records older than N days (default: 7)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without deleting",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]

        if dry_run:
            from datetime import timedelta

            from django.utils import timezone
            from shopman.doorman.models import AccessLink, TrustedDevice, VerificationCode

            cutoff = timezone.now() - timedelta(days=days)
            tokens_count = AccessLink.objects.filter(expires_at__lt=cutoff).count()
            codes_count = VerificationCode.objects.filter(expires_at__lt=cutoff).count()
            devices_count = TrustedDevice.objects.filter(expires_at__lt=cutoff).count()

            self.stdout.write(f"Would delete {tokens_count} expired access links")
            self.stdout.write(f"Would delete {codes_count} expired verification codes")
            self.stdout.write(f"Would delete {devices_count} expired device trusts")
            return

        tokens_deleted = AccessLinkService.cleanup_expired_tokens(days=days)
        codes_deleted = AuthService.cleanup_expired_codes(days=days)
        devices_deleted = DeviceTrustService.cleanup(days=days)

        self.stdout.write(
            self.style.SUCCESS(
                f"Cleaned up {tokens_deleted} access links, {codes_deleted} verification codes, "
                f"and {devices_deleted} device trusts (older than {days} days)"
            )
        )
