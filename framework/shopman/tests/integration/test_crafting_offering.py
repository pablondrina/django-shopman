"""
Integration tests: Crafting <-> Offering

Tests the production/catalog integration:
- Recipe references Offering products via output_ref (SKU)
- RecipeItem references ingredients via input_ref (SKU)
- Bundle/combo production

Covers:
- Recipe.output_ref -> Offering Product.sku
- RecipeItem.input_ref -> Offering Product.sku (ingredient)
"""

from decimal import Decimal

import pytest

from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder
from shopman.offerman.models import Product, ProductComponent

pytestmark = pytest.mark.django_db


# =============================================================================
# RECIPE -> PRODUCT RELATIONSHIP
# =============================================================================


class TestRecipeProductRelationship:
    """Tests for Recipe referencing Offering Product via output_ref."""

    def test_recipe_output_ref_matches_product_sku(self, recipe, croissant):
        """Recipe output_ref should match Offering Product SKU."""
        assert recipe.output_ref == croissant.sku
        assert recipe.output_ref == "CROISSANT"

    def test_recipe_can_find_output_product(self, recipe, croissant):
        """Recipe output_ref can resolve to Offering Product."""
        product = Product.objects.get(sku=recipe.output_ref)
        assert product == croissant
        assert product.base_price_q == 800

    def test_recipe_for_hidden_product(self, db, collection):
        """Recipe can reference hidden (unpublished) products."""
        from shopman.offerman.models import CollectionItem

        hidden = Product.objects.create(
            sku="HIDDEN-PROD",
            name="Hidden Product",
            base_price_q=1000,
            is_published=False,
        )
        CollectionItem.objects.create(
            collection=collection, product=hidden, is_primary=True,
        )

        recipe = Recipe.objects.create(
            code="hidden-recipe",
            name="Hidden Recipe",
            output_ref=hidden.sku,
            batch_size=Decimal("10"),
        )

        assert recipe.output_ref == hidden.sku
        product = Product.objects.get(sku=recipe.output_ref)
        assert product.is_hidden is True

    def test_recipe_for_unavailable_product(self, db, collection):
        """Recipe can reference paused (unavailable) products."""
        from shopman.offerman.models import CollectionItem

        paused = Product.objects.create(
            sku="PAUSED-PROD",
            name="Paused Product",
            base_price_q=1000,
            is_available=False,
        )
        CollectionItem.objects.create(
            collection=collection, product=paused, is_primary=True,
        )

        recipe = Recipe.objects.create(
            code="paused-recipe",
            name="Paused Recipe",
            output_ref=paused.sku,
            batch_size=Decimal("10"),
        )

        product = Product.objects.get(sku=recipe.output_ref)
        assert product.is_available is False


# =============================================================================
# RECIPE ITEMS (INGREDIENTS)
# =============================================================================


class TestRecipeIngredients:
    """Tests for Recipe ingredients from Offering catalog."""

    def test_recipe_item_references_product_by_sku(self, recipe, ingredient):
        """RecipeItem should reference Offering Product via input_ref."""
        item = recipe.items.first()

        assert item is not None
        assert item.input_ref == ingredient.sku
        assert item.input_ref == "FARINHA"

    def test_ingredient_is_non_available(self, ingredient):
        """Ingredients are typically non-available products."""
        assert ingredient.is_available is False
        assert ingredient.sku == "FARINHA"

    def test_recipe_with_multiple_ingredients(self, db, collection, croissant):
        """Recipe can have multiple ingredients."""
        from shopman.offerman.models import CollectionItem

        # Create additional ingredients
        butter = Product.objects.create(
            sku="MANTEIGA",
            name="Manteiga",
            unit="kg",
            base_price_q=2500,
            is_available=False,
        )
        CollectionItem.objects.create(
            collection=collection, product=butter, is_primary=True,
        )
        eggs = Product.objects.create(
            sku="OVOS",
            name="Ovos",
            unit="un",
            base_price_q=50,
            is_available=False,
        )
        CollectionItem.objects.create(
            collection=collection, product=eggs, is_primary=True,
        )

        recipe = Recipe.objects.create(
            code="croissant-full",
            name="Croissant Completo",
            output_ref=croissant.sku,
            batch_size=Decimal("10"),
        )

        RecipeItem.objects.create(
            recipe=recipe,
            input_ref=butter.sku,
            quantity=Decimal("0.5"),
            unit="kg",
        )
        RecipeItem.objects.create(
            recipe=recipe,
            input_ref=eggs.sku,
            quantity=Decimal("6"),
            unit="un",
        )

        assert recipe.items.count() == 2

        # Access ingredient refs
        input_refs = list(recipe.items.values_list("input_ref", flat=True))
        assert "MANTEIGA" in input_refs
        assert "OVOS" in input_refs

    def test_ingredient_cost_calculation(self, db, collection, croissant):
        """Calculate recipe cost from ingredient prices."""
        from shopman.offerman.models import CollectionItem

        flour = Product.objects.create(
            sku="FARINHA-CUSTO",
            name="Farinha",
            unit="kg",
            base_price_q=500,  # R$ 5.00/kg
            is_available=False,
        )
        CollectionItem.objects.create(
            collection=collection, product=flour, is_primary=True,
        )
        butter = Product.objects.create(
            sku="MANTEIGA-CUSTO",
            name="Manteiga",
            unit="kg",
            base_price_q=2500,  # R$ 25.00/kg
            is_available=False,
        )
        CollectionItem.objects.create(
            collection=collection, product=butter, is_primary=True,
        )

        recipe = Recipe.objects.create(
            code="cost-recipe",
            name="Recipe with Cost",
            output_ref=croissant.sku,
            batch_size=Decimal("10"),
        )

        RecipeItem.objects.create(
            recipe=recipe,
            input_ref=flour.sku,
            quantity=Decimal("2"),  # 2 kg flour = R$ 10.00
            unit="kg",
        )
        RecipeItem.objects.create(
            recipe=recipe,
            input_ref=butter.sku,
            quantity=Decimal("0.5"),  # 0.5 kg butter = R$ 12.50
            unit="kg",
        )

        # Calculate total cost by resolving input_refs to products
        total_cost = Decimal("0")
        for item in recipe.items.all():
            product = Product.objects.get(sku=item.input_ref)
            ingredient_price = Decimal(product.base_price_q) / 100
            total_cost += item.quantity * ingredient_price

        # Total: R$ 10.00 + R$ 12.50 = R$ 22.50
        assert total_cost == Decimal("22.50")

        # Cost per unit: R$ 22.50 / 10 = R$ 2.25
        cost_per_unit = total_cost / recipe.batch_size
        assert cost_per_unit == Decimal("2.25")


# =============================================================================
# BUNDLE/COMBO PRODUCTION
# =============================================================================


class TestBundleProduction:
    """Tests for producing bundled/combo products."""

    def test_bundle_product_recipe(self, db, collection, croissant):
        """Recipe can produce bundle products."""
        from shopman.offerman.models import CollectionItem

        coffee = Product.objects.create(
            sku="ESPRESSO",
            name="Espresso",
            base_price_q=500,
        )
        CollectionItem.objects.create(
            collection=collection, product=coffee, is_primary=True,
        )

        combo = Product.objects.create(
            sku="COMBO-MANHA",
            name="Combo Café da Manhã",
            base_price_q=1100,
        )
        CollectionItem.objects.create(
            collection=collection, product=combo, is_primary=True,
        )

        ProductComponent.objects.create(
            parent=combo,
            component=croissant,
            qty=Decimal("1"),
        )
        ProductComponent.objects.create(
            parent=combo,
            component=coffee,
            qty=Decimal("1"),
        )

        recipe = Recipe.objects.create(
            code="combo-manha",
            name="Combo Café da Manhã",
            output_ref=combo.sku,
            batch_size=Decimal("1"),
        )

        # Recipe produces the combo product
        product = Product.objects.get(sku=recipe.output_ref)
        assert product == combo
        assert combo.is_bundle is True
        assert combo.components.count() == 2


# =============================================================================
# PRODUCTION WORKFLOW
# =============================================================================


class TestProductionWorkflow:
    """Tests for full production workflow with Offering products."""

    def test_work_order_for_offering_product(
        self, work_order, recipe, croissant, position_loja, today
    ):
        """WorkOrder should reference recipe that produces Offering product."""
        assert work_order.recipe == recipe
        product = Product.objects.get(sku=work_order.recipe.output_ref)
        assert product == croissant

    def test_work_order_completion_with_product(
        self, work_order, croissant, today
    ):
        """Completing WorkOrder tracks production of Offering product."""
        from django.utils import timezone

        # WorkOrder starts as OPEN
        assert work_order.status == WorkOrder.Status.OPEN

        # Start work order
        work_order.started_at = timezone.now()
        work_order.save(update_fields=["started_at"])

        # Complete work order
        work_order.produced = Decimal("48")
        work_order.status = WorkOrder.Status.DONE
        work_order.finished_at = timezone.now()
        work_order.save(update_fields=["produced", "status", "finished_at"])

        # Verify product reference
        product = Product.objects.get(sku=work_order.recipe.output_ref)
        assert product == croissant
        assert work_order.produced == Decimal("48")

    def test_product_price_vs_production_cost(
        self, db, collection, croissant, ingredient
    ):
        """Compare product sale price with production cost."""
        recipe = Recipe.objects.create(
            code="cost-analysis",
            name="Cost Analysis Recipe",
            output_ref=croissant.sku,
            batch_size=Decimal("10"),
        )

        RecipeItem.objects.create(
            recipe=recipe,
            input_ref=ingredient.sku,
            quantity=Decimal("0.5"),  # 0.5 kg = R$ 2.50
            unit="kg",
        )

        # Calculate production cost
        ingredient_cost = (
            Decimal(ingredient.base_price_q) / 100 * Decimal("0.5")
        )  # R$ 2.50
        cost_per_unit = ingredient_cost / recipe.batch_size  # R$ 0.25

        # Sale price
        sale_price = Decimal(croissant.base_price_q) / 100  # R$ 8.00

        # Margin
        margin = sale_price - cost_per_unit
        margin_percent = (margin / sale_price) * 100

        assert cost_per_unit == Decimal("0.25")
        assert sale_price == Decimal("8.00")
        assert margin == Decimal("7.75")
        assert margin_percent > Decimal("96")


# =============================================================================
# CATALOG QUERIES FOR PRODUCTION
# =============================================================================


class TestCatalogQueriesForProduction:
    """Tests for using Offering catalog queries in production context."""

    def test_find_available_products(self, product, croissant, ingredient):
        """Find available products that need production."""
        available = Product.objects.filter(is_available=True)

        assert product in available
        assert croissant in available
        assert ingredient not in available

    def test_find_products_with_recipes(self, recipe, croissant, product):
        """Find products that have recipes."""
        products_with_recipes = Product.objects.filter(
            sku__in=Recipe.objects.values_list("output_ref", flat=True)
        )

        assert croissant in products_with_recipes
        assert product not in products_with_recipes

    def test_find_ingredients_for_planning(self, ingredient, recipe):
        """Find all ingredients needed for production planning."""
        # Get all unique ingredient refs from all recipes
        ingredient_refs = RecipeItem.objects.values_list(
            "input_ref", flat=True
        ).distinct()

        ingredients = Product.objects.filter(sku__in=ingredient_refs)

        assert ingredient in ingredients
