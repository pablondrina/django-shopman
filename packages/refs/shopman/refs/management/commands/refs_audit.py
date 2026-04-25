"""
refs_audit — find orphaned, stale, or duplicate refs.

Usage:
    python manage.py refs_audit --orphaned
    python manage.py refs_audit --stale --days=30
    python manage.py refs_audit --duplicates
    python manage.py refs_audit --orphaned --stale --duplicates   # combine
    python manage.py refs_audit --type=SKU --orphaned
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Audit refs for data quality issues."

    def add_arguments(self, parser):
        parser.add_argument("--orphaned", action="store_true",
                            help="Find refs whose target entity no longer exists")
        parser.add_argument("--stale", action="store_true",
                            help="Find active refs created more than --days ago")
        parser.add_argument("--duplicates", action="store_true",
                            help="Find (type, value) pairs with multiple active refs")
        parser.add_argument("--days", type=int, default=30, metavar="N",
                            help="Days threshold for --stale (default: 30)")
        parser.add_argument("--type", dest="ref_type", metavar="REF_TYPE", default=None,
                            help="Limit audit to this RefType slug")

    def handle(self, *args, **options):
        orphaned = options["orphaned"]
        stale = options["stale"]
        duplicates = options["duplicates"]
        days = options["days"]
        ref_type = options["ref_type"]

        if not any([orphaned, stale, duplicates]):
            raise CommandError("Specify at least one of --orphaned, --stale, --duplicates")

        found_any = False

        if orphaned:
            found_any |= self._audit_orphaned(ref_type)

        if stale:
            found_any |= self._audit_stale(ref_type, days)

        if duplicates:
            found_any |= self._audit_duplicates(ref_type)

        if not found_any:
            self.stdout.write(self.style.SUCCESS("No issues found."))

    # ── Orphaned ─────────────────────────────────────────────────────────────

    def _audit_orphaned(self, ref_type):
        from shopman.refs.bulk import RefBulk
        orphans = RefBulk.find_orphaned(ref_type=ref_type)
        if not orphans:
            self.stdout.write(self.style.SUCCESS("Orphaned refs: 0"))
            return False

        self.stdout.write(self.style.ERROR(f"Orphaned refs: {len(orphans)}"))
        for ref in orphans[:20]:
            self.stdout.write(f"  {ref.ref_type}:{ref.value} → {ref.target_type}:{ref.target_id} "
                              f"(active={ref.is_active})")
        if len(orphans) > 20:
            self.stdout.write(f"  ... and {len(orphans) - 20} more")
        return True

    # ── Stale ─────────────────────────────────────────────────────────────────

    def _audit_stale(self, ref_type, days):
        from shopman.refs.models import Ref
        cutoff = timezone.now() - timezone.timedelta(days=days)
        qs = Ref.objects.filter(is_active=True, created_at__lt=cutoff)
        if ref_type:
            qs = qs.filter(ref_type=ref_type)
        count = qs.count()

        if not count:
            self.stdout.write(self.style.SUCCESS(f"Stale refs (>{days}d): 0"))
            return False

        self.stdout.write(self.style.WARNING(f"Stale active refs (>{days}d): {count}"))
        for ref in qs[:20]:
            age = (timezone.now() - ref.created_at).days
            self.stdout.write(f"  {ref.ref_type}:{ref.value} → {ref.target_type}:{ref.target_id} "
                              f"(age={age}d, actor={ref.actor!r})")
        if count > 20:
            self.stdout.write(f"  ... and {count - 20} more")
        return True

    # ── Duplicates ────────────────────────────────────────────────────────────

    def _audit_duplicates(self, ref_type):
        from django.db.models import Count

        from shopman.refs.models import Ref

        qs = Ref.objects.filter(is_active=True)
        if ref_type:
            qs = qs.filter(ref_type=ref_type)

        dupes = (
            qs.values("ref_type", "value")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .order_by("-n")
        )

        if not dupes:
            self.stdout.write(self.style.SUCCESS("Duplicate active refs: 0"))
            return False

        total = sum(d["n"] for d in dupes)
        self.stdout.write(self.style.WARNING(f"Duplicate active (type, value) pairs: {dupes.count()} "
                                             f"({total} refs total)"))
        for d in list(dupes)[:20]:
            self.stdout.write(f"  {d['ref_type']}:{d['value']} — {d['n']} active refs")
        if dupes.count() > 20:
            self.stdout.write(f"  ... and {dupes.count() - 20} more pairs")
        return True
