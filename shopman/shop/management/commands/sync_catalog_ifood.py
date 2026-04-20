"""
Management command: sync_catalog_ifood

Syncs the iFood listing to the iFood Merchant API.

Usage:
    python manage.py sync_catalog_ifood           # incremental upsert
    python manage.py sync_catalog_ifood --full    # full catalog replace
    python manage.py sync_catalog_ifood --dry-run # preview items, no API call
"""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Sync catalog to iFood Merchant API. Use --full for initial load."

    def add_arguments(self, parser):
        parser.add_argument(
            "--full",
            action="store_true",
            default=False,
            help="Full catalog sync — replace the entire iFood menu.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print items to sync without calling the iFood API.",
        )

    def handle(self, *args, **options):
        from shopman.offerman.service import CatalogService
        from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection
        from shopman.shop.models import Channel

        try:
            channel = Channel.objects.get(ref="ifood")
        except Channel.DoesNotExist:
            raise CommandError("Channel 'ifood' not found. Create it in the admin first.")

        if not channel.is_active:
            self.stdout.write(self.style.WARNING("Channel 'ifood' is not active — skipping sync."))
            return

        try:
            items = CatalogService.get_projection_items("ifood")
        except Exception as exc:
            raise CommandError(f"Failed to fetch projection items: {exc}") from exc

        if not items:
            self.stdout.write(self.style.WARNING("No items in listing 'ifood'. Nothing to sync."))
            return

        if options["dry_run"]:
            self.stdout.write(f"Dry run — {len(items)} item(s) in listing 'ifood':\n")
            for item in items:
                price = item.price_q / 100
                avail = "✓" if (item.is_published and item.is_sellable) else "✗"
                self.stdout.write(f"  [{avail}] {item.sku} — {item.name} — R${price:.2f}")
            self.stdout.write("\nNo changes sent to iFood (dry run).")
            return

        mode = "full" if options["full"] else "incremental"
        self.stdout.write(f"Syncing {len(items)} item(s) to iFood ({mode})…")

        backend = IFoodCatalogProjection()
        try:
            result = backend.project(items, channel="ifood", full_sync=options["full"])
        except Exception as exc:
            raise CommandError(f"iFood API error: {exc}") from exc

        if result.success:
            self.stdout.write(
                self.style.SUCCESS(f"Done — {result.projected} item(s) projected to iFood.")
            )
        else:
            for err in result.errors:
                self.stdout.write(self.style.ERROR(f"  {err}"))
            raise CommandError(f"Sync completed with {len(result.errors)} error(s).")
