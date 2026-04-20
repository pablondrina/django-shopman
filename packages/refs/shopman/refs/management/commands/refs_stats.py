"""
refs_stats — show per-type breakdown of refs and registered RefField sources.

Usage:
    python manage.py refs_stats
    python manage.py refs_stats --type=SKU
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Show ref counts by type and registered RefField sources."

    def add_arguments(self, parser):
        parser.add_argument("--type", dest="ref_type", metavar="REF_TYPE", default=None,
                            help="Limit stats to this RefType slug")

    def handle(self, *args, **options):
        ref_type_filter = options["ref_type"]
        self._show_ref_counts(ref_type_filter)
        self._show_registry(ref_type_filter)

    # ── Ref counts ────────────────────────────────────────────────────────────

    def _show_ref_counts(self, ref_type_filter):
        from django.db.models import Count, Q
        from shopman.refs.models import Ref

        qs = Ref.objects.values("ref_type").annotate(
            active=Count("id", filter=Q(is_active=True)),
            inactive=Count("id", filter=Q(is_active=False)),
            total=Count("id"),
        ).order_by("ref_type")

        if ref_type_filter:
            qs = qs.filter(ref_type=ref_type_filter)

        rows = list(qs)

        if not rows:
            self.stdout.write(self.style.WARNING("No refs in database."))
            return

        # Header
        self.stdout.write(self.style.HTTP_INFO(
            f"\n{'Type':<24} {'Active':>8} {'Inactive':>10} {'Total':>8}"
        ))
        self.stdout.write("-" * 54)

        for row in rows:
            self.stdout.write(
                f"{row['ref_type']:<24} {row['active']:>8} {row['inactive']:>10} {row['total']:>8}"
            )

        # Totals
        total_active = sum(r["active"] for r in rows)
        total_inactive = sum(r["inactive"] for r in rows)
        total_all = sum(r["total"] for r in rows)
        self.stdout.write("-" * 54)
        self.stdout.write(
            f"{'TOTAL':<24} {total_active:>8} {total_inactive:>10} {total_all:>8}\n"
        )

    # ── RefSourceRegistry ─────────────────────────────────────────────────────

    def _show_registry(self, ref_type_filter):
        from shopman.refs.registry import _ref_source_registry

        self.stdout.write(self.style.HTTP_INFO("RefField sources (RefSourceRegistry):"))

        if ref_type_filter:
            types_to_show = [ref_type_filter]
        else:
            # introspect internal dict
            types_to_show = list(_ref_source_registry._sources.keys())

        if not types_to_show:
            self.stdout.write("  (none registered)")
            return

        for rtype in sorted(types_to_show):
            sources = _ref_source_registry.get_sources_for_type(rtype)
            if not sources:
                if ref_type_filter:
                    self.stdout.write(f"  {rtype}: (none registered)")
                continue
            self.stdout.write(f"  {rtype}:")
            for model_label, field_name in sources:
                self.stdout.write(f"    {model_label}.{field_name}")
