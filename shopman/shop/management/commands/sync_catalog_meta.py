"""
Management command: sync_catalog_meta

Syncs the Meta listing (Instagram + Facebook Commerce Catalog) to the Graph
``items_batch`` API.

Usage:
    python manage.py sync_catalog_meta            # incremental, retract-aware
    python manage.py sync_catalog_meta --full     # full upsert (no retract)
    python manage.py sync_catalog_meta --dry-run  # preview the batch JSON, no API call

Mirrors ``sync_catalog_ifood``: routes through ``CatalogService.project_listing()``
(the canonical, retract-aware engine) which resolves the Meta backend from the
canonical registry (``OFFERMAN["PROJECTION_BACKENDS"]``). ``--dry-run`` prints the
exact ``requests`` payload the adapter would POST — verifiable without credentials.
"""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Sync catalog to the Meta Commerce Catalog (IG/FB). Use --full for initial load."

    def add_arguments(self, parser):
        parser.add_argument(
            "--full",
            action="store_true",
            default=False,
            help="Full catalog sync — upsert every item (no retract).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print the items_batch requests without calling the Graph API.",
        )

    def handle(self, *args, **options):
        import json

        from shopman.offerman.exceptions import CatalogError
        from shopman.offerman.service import CatalogService

        from shopman.shop.adapters.catalog_projection_meta import build_batch_requests

        try:
            items = CatalogService.get_projection_items("meta")
        except Exception as exc:
            raise CommandError(f"Failed to fetch projection items: {exc}") from exc

        if not items:
            self.stdout.write(self.style.WARNING("No items in listing 'meta'. Nothing to sync."))
            return

        if options["dry_run"]:
            from django.conf import settings

            cfg = getattr(settings, "SHOPMAN_META", {}) or {}
            requests_payload = build_batch_requests(items, cfg)
            self.stdout.write(f"Dry run — {len(items)} item(s) in listing 'meta':\n")
            self.stdout.write(
                json.dumps(
                    {"item_type": "PRODUCT_ITEM", "allow_upsert": True, "requests": requests_payload},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            self.stdout.write("\nNo changes sent to Meta (dry run).")
            return

        mode = "full" if options["full"] else "incremental"
        self.stdout.write(f"Syncing {len(items)} item(s) to Meta ({mode})…")

        try:
            result = CatalogService.project_listing("meta", full_sync=options["full"])
        except CatalogError as exc:
            if exc.code == "PROJECTION_BACKEND_NOT_CONFIGURED":
                raise CommandError(
                    "Meta projection backend not configured. Set META_CATALOG_PROJECTION=1 "
                    "(with SHOPMAN_META access_token + catalog_id) to enable."
                ) from exc
            raise CommandError(f"Meta sync error: {exc}") from exc
        except Exception as exc:
            raise CommandError(f"Meta API error: {exc}") from exc

        if result.success:
            self.stdout.write(
                self.style.SUCCESS(f"Done — {result.projected} item(s) projected to Meta.")
            )
        else:
            for err in result.errors:
                self.stdout.write(self.style.ERROR(f"  {err}"))
            raise CommandError(f"Sync completed with {len(result.errors)} error(s).")
