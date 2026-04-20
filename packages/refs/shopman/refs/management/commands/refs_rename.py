"""
refs_rename — rename a ref value, optionally cascading to RefField sources.

Usage:
    python manage.py refs_rename --type=SKU --old=CROISSANT --new=CROISSANT-FR
    python manage.py refs_rename --type=SKU --old=CROISSANT --new=CROISSANT-FR --cascade
    python manage.py refs_rename --type=SKU --old=CROISSANT --new=CROISSANT-FR --cascade --actor=admin
    python manage.py refs_rename --type=SKU --old=CROISSANT --new=CROISSANT-FR --dry-run
"""

from django.core.management.base import BaseCommand, CommandError

from shopman.refs.bulk import RefBulk


class Command(BaseCommand):
    help = "Rename a ref value across the Ref table (and optionally RefField sources)."

    def add_arguments(self, parser):
        parser.add_argument("--type", required=True, dest="ref_type", metavar="REF_TYPE",
                            help="RefType slug, e.g. SKU")
        parser.add_argument("--old", required=True, dest="old_value", metavar="OLD",
                            help="Current value to find")
        parser.add_argument("--new", required=True, dest="new_value", metavar="NEW",
                            help="Replacement value")
        parser.add_argument("--cascade", action="store_true",
                            help="Also update all RefField sources registered for this type")
        parser.add_argument("--actor", default="management:refs_rename", metavar="ACTOR",
                            help="Actor string stored in audit log (default: management:refs_rename)")
        parser.add_argument("--dry-run", action="store_true",
                            help="Show what would be renamed without committing changes")

    def handle(self, *args, **options):
        ref_type = options["ref_type"]
        old_value = options["old_value"]
        new_value = options["new_value"]
        cascade = options["cascade"]
        actor = options["actor"]
        dry_run = options["dry_run"]

        if dry_run:
            self._dry_run(ref_type, old_value, cascade)
            return

        try:
            if cascade:
                count = RefBulk.cascade_rename(
                    ref_type=ref_type,
                    old_value=old_value,
                    new_value=new_value,
                    actor=actor,
                )
                label = "refs + RefField sources"
            else:
                count = RefBulk.rename(
                    ref_type=ref_type,
                    old_value=old_value,
                    new_value=new_value,
                    actor=actor,
                )
                label = "refs"
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        if count:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Renamed {count} {label}: {ref_type} {old_value!r} → {new_value!r}"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"No {label} found for {ref_type} value={old_value!r}"
                )
            )

    def _dry_run(self, ref_type, old_value, cascade):
        from shopman.refs.models import Ref
        from shopman.refs.registry import _ref_source_registry

        count = Ref.objects.filter(ref_type=ref_type, value=old_value).count()
        self.stdout.write(self.style.NOTICE(f"[dry-run] Would rename {count} Ref(s): "
                                            f"{ref_type} {old_value!r}"))

        if cascade:
            sources = _ref_source_registry.get_sources_for_type(ref_type)
            if sources:
                from django.apps import apps as django_apps
                for model_label, field_name in sources:
                    try:
                        app_label, model_name = model_label.split(".", 1)
                        Model = django_apps.get_model(app_label, model_name)
                        n = Model.objects.filter(**{field_name: old_value}).count()
                        self.stdout.write(self.style.NOTICE(
                            f"[dry-run] Would update {n} row(s) in {model_label}.{field_name}"
                        ))
                    except LookupError:
                        self.stdout.write(self.style.WARNING(
                            f"[dry-run] Model {model_label} not found in app registry"
                        ))
            else:
                self.stdout.write(self.style.NOTICE("[dry-run] No RefField sources registered for this type"))
        self.stdout.write(self.style.NOTICE("[dry-run] No changes committed."))
