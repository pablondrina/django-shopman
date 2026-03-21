"""
Management command to release expired holds.

Usage:
    python manage.py release_expired_holds
    python manage.py release_expired_holds --dry-run
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from shopman.stocking import stock
from shopman.stocking.models import Hold, HoldStatus


class Command(BaseCommand):
    """Release expired holds command."""
    
    help = 'Libera bloqueios expirados'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra o que seria liberado sem executar'
        )
    
    def handle(self, *args, **options):
        if options['dry_run']:
            expired = Hold.objects.filter(
                status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
                expires_at__lt=timezone.now()
            ).count()
            
            self.stdout.write(f'{expired} bloqueio(s) seria(m) liberado(s)')
        else:
            count = stock.release_expired()
            self.stdout.write(
                self.style.SUCCESS(f'{count} bloqueio(s) liberado(s)')
            )







