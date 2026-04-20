"""
Load demo data for Craftsman vNext.

Creates realistic production data for a bakery using the vNext API:
- Recipes with RecipeItems (BOM)
- WorkOrders via craft.plan() + craft.finish()

Usage:
    python manage.py load_crafting_demo
    python manage.py load_crafting_demo --clear
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Carrega dados de demonstracao para o Craftsman vNext"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Limpa dados existentes antes de carregar",
        )

    def handle(self, *args, **options):
        from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder, WorkOrderEvent, WorkOrderItem

        self.stdout.write("=" * 60)
        self.stdout.write("Carregando dados de demonstracao do Craftsman vNext...")
        self.stdout.write("=" * 60)

        if options["clear"]:
            self.stdout.write("\nLimpando dados existentes...")
            WorkOrderEvent.objects.all().delete()
            WorkOrderItem.objects.all().delete()
            WorkOrder.objects.all().delete()
            RecipeItem.objects.all().delete()
            Recipe.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("  Dados limpos."))

        recipes = self._create_recipes()
        self._create_work_orders(recipes)
        self._print_summary()

    def _create_recipes(self):
        """Create demo recipes with ingredients (BOM)."""
        from shopman.craftsman.models import Recipe, RecipeItem

        self.stdout.write("\nCriando receitas...")

        RECIPES = [
            {
                "ref": "croissant-v1",
                "name": "Croissant Tradicional",
                "output_sku": "croissant",
                "batch_size": Decimal("30"),
                "steps": ["Mistura", "Laminacao", "Modelagem", "Forno"],
                "items": [
                    ("farinha-t55", Decimal("10"), "kg"),
                    ("manteiga", Decimal("5"), "kg"),
                    ("fermento", Decimal("0.300"), "kg"),
                    ("agua", Decimal("5"), "L"),
                    ("sal", Decimal("0.200"), "kg"),
                ],
            },
            {
                "ref": "pao-frances-v1",
                "name": "Pao Frances",
                "output_sku": "pao-frances",
                "batch_size": Decimal("50"),
                "steps": ["Mistura", "Fermentacao", "Modelagem", "Forno"],
                "items": [
                    ("farinha-t55", Decimal("15"), "kg"),
                    ("agua", Decimal("10"), "L"),
                    ("fermento", Decimal("0.500"), "kg"),
                    ("sal", Decimal("0.300"), "kg"),
                ],
            },
            {
                "ref": "baguette-v1",
                "name": "Baguette",
                "output_sku": "baguette",
                "batch_size": Decimal("40"),
                "steps": ["Mistura", "Fermentacao", "Modelagem", "Forno"],
                "items": [
                    ("farinha-t65", Decimal("12"), "kg"),
                    ("agua", Decimal("8"), "L"),
                    ("fermento", Decimal("0.400"), "kg"),
                    ("sal", Decimal("0.250"), "kg"),
                ],
            },
            {
                "ref": "brioche-v1",
                "name": "Brioche",
                "output_sku": "brioche",
                "batch_size": Decimal("20"),
                "steps": ["Mistura", "Fermentacao", "Modelagem", "Forno"],
                "items": [
                    ("farinha-t45", Decimal("8"), "kg"),
                    ("manteiga", Decimal("4"), "kg"),
                    ("ovos", Decimal("2"), "kg"),
                    ("acucar", Decimal("1.5"), "kg"),
                    ("fermento", Decimal("0.250"), "kg"),
                ],
            },
        ]

        created = []
        for data in RECIPES:
            recipe, was_created = Recipe.objects.get_or_create(
                ref=data["ref"],
                defaults={
                    "name": data["name"],
                    "output_sku": data["output_sku"],
                    "batch_size": data["batch_size"],
                    "steps": data["steps"],
                },
            )
            if was_created:
                for i, (input_sku, qty, unit) in enumerate(data["items"]):
                    RecipeItem.objects.create(
                        recipe=recipe,
                        input_sku=input_sku,
                        quantity=qty,
                        unit=unit,
                        sort_order=i,
                    )
                self.stdout.write(f"  Criada: {recipe.name}")
            else:
                self.stdout.write(f"  Existente: {recipe.name}")
            created.append(recipe)

        return created

    def _create_work_orders(self, recipes):
        """Create demo WorkOrders using craft.plan() and craft.finish()."""
        from shopman.craftsman import craft

        self.stdout.write("\nCriando ordens de producao...")

        today = date.today()

        for days_offset in range(-7, 4):
            target_date = today + timedelta(days=days_offset)
            is_past = days_offset < 0
            is_today = days_offset == 0

            for recipe in recipes:
                qty = int(recipe.batch_size) * random.randint(1, 3)
                wo = craft.plan(recipe, qty, date=target_date)

                if is_past:
                    # Past: all finished with realistic yield
                    finished = int(qty * random.uniform(0.90, 0.99))
                    craft.finish(wo, finished=finished)
                elif is_today and random.random() < 0.5:
                    # Today: 50% chance of being finished
                    finished = int(qty * random.uniform(0.92, 0.98))
                    craft.finish(wo, finished=finished)
                # Future: leave as PLANNED

            label = "(HOJE)" if is_today else "(FUTURO)" if not is_past else ""
            self.stdout.write(f"  {target_date.strftime('%d/%m/%Y')} {label}")

    def _print_summary(self):
        """Print summary of created data."""
        from shopman.craftsman.models import Recipe, WorkOrder

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("Resumo:")
        self.stdout.write(f"  Receitas:  {Recipe.objects.count()}")
        self.stdout.write(f"  OPs total: {WorkOrder.objects.count()}")
        self.stdout.write(
            f"    PLANNED: {WorkOrder.objects.filter(status=WorkOrder.Status.PLANNED).count()}"
        )
        self.stdout.write(
            f"    STARTED: {WorkOrder.objects.filter(status=WorkOrder.Status.STARTED).count()}"
        )
        self.stdout.write(
            f"    FINISHED: {WorkOrder.objects.filter(status=WorkOrder.Status.FINISHED).count()}"
        )
        self.stdout.write(
            f"    VOID: {WorkOrder.objects.filter(status=WorkOrder.Status.VOID).count()}"
        )
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("Dados de demonstracao carregados."))
