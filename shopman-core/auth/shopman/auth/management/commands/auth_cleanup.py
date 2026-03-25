"""
Management command to clean up expired tokens, codes, and device trusts.

Usage:
    python manage.py auth_cleanup
    python manage.py auth_cleanup --days=30
    python manage.py auth_cleanup --dry-run
"""

from django.core.management.base import BaseCommand

from shopman.auth.services.auth_bridge import AuthBridgeService
from shopman.auth.services.device_trust import DeviceTrustService
from shopman.auth.services.verification import VerificationService


class Command(BaseCommand):
    help = "Clean up expired bridge tokens, magic codes, and device trusts."

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

            from shopman.auth.models import BridgeToken, MagicCode, TrustedDevice

            cutoff = timezone.now() - timedelta(days=days)
            tokens_count = BridgeToken.objects.filter(expires_at__lt=cutoff).count()
            codes_count = MagicCode.objects.filter(expires_at__lt=cutoff).count()
            devices_count = TrustedDevice.objects.filter(expires_at__lt=cutoff).count()

            self.stdout.write(f"Would delete {tokens_count} expired tokens")
            self.stdout.write(f"Would delete {codes_count} expired codes")
            self.stdout.write(f"Would delete {devices_count} expired device trusts")
            return

        tokens_deleted = AuthBridgeService.cleanup_expired_tokens(days=days)
        codes_deleted = VerificationService.cleanup_expired_codes(days=days)
        devices_deleted = DeviceTrustService.cleanup(days=days)

        self.stdout.write(
            self.style.SUCCESS(
                f"Cleaned up {tokens_deleted} tokens, {codes_deleted} codes, "
                f"and {devices_deleted} device trusts (older than {days} days)"
            )
        )
