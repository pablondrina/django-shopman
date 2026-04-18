"""Backfill ingredients + nutrition on Products from active Recipes.

Usage::

    python manage.py fill_nutrition_from_recipe               # all eligible
    python manage.py fill_nutrition_from_recipe --sku BAGUETE # single SKU
    python manage.py fill_nutrition_from_recipe --force       # ignore auto_filled=False

Respects the ``auto_filled`` sentinel by default — products with a
manual override are skipped. ``--force`` clears that flag on each
targeted product before derivation, then the service rewrites the
dict with ``auto_filled=True``.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from shopman.offerman.models import Product

from shopman.shop.services.nutrition_from_recipe import fill_nutrition_from_recipe


class Command(BaseCommand):
    help = "Materialize Product.ingredients_text + nutrition_facts from active Recipes."

    def add_arguments(self, parser):
        parser.add_argument("--sku", type=str, default=None, help="Target a single SKU.")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ignore manual overrides (auto_filled=False) — rewrite anyway.",
        )

    def handle(self, *args, sku: str | None = None, force: bool = False, **options):
        qs = Product.objects.all()
        if sku:
            qs = qs.filter(sku=sku)

        updated = 0
        skipped = 0
        for product in qs:
            if force and product.nutrition_facts:
                product.nutrition_facts = {}  # force auto-fill path
            changed = fill_nutrition_from_recipe(product)
            if changed:
                updated += 1
                self.stdout.write(f"  updated {product.sku}")
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done: {updated} updated, {skipped} skipped."
        ))
