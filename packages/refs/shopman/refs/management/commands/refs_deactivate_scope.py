"""
refs_deactivate_scope — deactivate all active refs for a type within a scope.

Usage:
    python manage.py refs_deactivate_scope \\
        --type=POS_TABLE \\
        --scope='{"store_id":1,"business_date":"2026-04-20"}' \\
        --actor=system

    python manage.py refs_deactivate_scope \\
        --type=POS_TABLE \\
        --scope='{"store_id":1,"business_date":"2026-04-20"}' \\
        --dry-run
"""

import json

from django.core.management.base import BaseCommand, CommandError

from shopman.refs.bulk import RefBulk


class Command(BaseCommand):
    help = "Deactivate all active refs of a given type within a scope."

    def add_arguments(self, parser):
        parser.add_argument("--type", required=True, dest="ref_type", metavar="REF_TYPE",
                            help="RefType slug, e.g. POS_TABLE")
        parser.add_argument("--scope", required=True, metavar="JSON",
                            help='Scope as JSON, e.g. \'{"store_id":1,"business_date":"2026-04-20"}\'')
        parser.add_argument("--actor", default="management:refs_deactivate_scope", metavar="ACTOR",
                            help="Actor string for audit trail")
        parser.add_argument("--dry-run", action="store_true",
                            help="Show count of refs that would be deactivated without committing")

    def handle(self, *args, **options):
        ref_type = options["ref_type"]
        actor = options["actor"]
        dry_run = options["dry_run"]

        try:
            scope = json.loads(options["scope"])
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON for --scope: {exc}") from exc

        if not isinstance(scope, dict):
            raise CommandError("--scope must be a JSON object (dict)")

        if dry_run:
            from shopman.refs.models import Ref
            qs = Ref.objects.filter(ref_type=ref_type, is_active=True)
            filt = {f"scope__{k}": v for k, v in scope.items()}
            if filt:
                qs = qs.filter(**filt)
            count = qs.count()
            self.stdout.write(self.style.NOTICE(
                f"[dry-run] Would deactivate {count} ref(s) of type {ref_type!r} in scope {scope}"
            ))
            self.stdout.write(self.style.NOTICE("[dry-run] No changes committed."))
            return

        try:
            count = RefBulk.deactivate_scope(ref_type=ref_type, scope=scope, actor=actor)
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        if count:
            self.stdout.write(self.style.SUCCESS(
                f"Deactivated {count} ref(s) of type {ref_type!r} in scope {scope}"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"No active refs found for type {ref_type!r} in scope {scope}"
            ))
