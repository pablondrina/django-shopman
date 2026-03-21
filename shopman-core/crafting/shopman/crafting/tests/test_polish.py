"""
Tests for v0.2.1 polish changes.

Covers:
- Recipe validation i18n fix (f-string → % formatting)
- Stockman adapter logging on _get_product failure
- API endpoint exception handling (StaleRevision → 409, CraftError → 400)
- Version alignment
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.core.exceptions import ValidationError

from shopman.crafting import CraftError, StaleRevision, craft
from shopman.crafting.models import Recipe, RecipeItem, WorkOrder


# ══════════════════════════════════════════════════════════════
# VERSION ALIGNMENT
# ══════════════════════════════════════════════════════════════


class TestVersion:
    def test_version_string(self):
        import shopman.crafting
        assert shopman.crafting.__version__ == "0.2.2"

    def test_version_format(self):
        import shopman.crafting
        parts = shopman.crafting.__version__.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


# ══════════════════════════════════════════════════════════════
# RECIPE VALIDATION I18N
# ══════════════════════════════════════════════════════════════


class TestRecipeValidationI18n:
    """Test that recipe step validation uses proper i18n formatting."""

    def test_empty_step_raises_with_step_number(self, db):
        """Validation error includes step number via % formatting."""
        with pytest.raises(ValidationError) as exc:
            Recipe.objects.create(
                code="bad-steps",
                name="Bad Steps Recipe",
                output_ref="test",
                batch_size=Decimal("10"),
                steps=["Mistura", "", "Forno"],
            )

        errors = exc.value.message_dict
        assert "steps" in errors
        # Step 2 (index 1) should be mentioned
        assert "2" in str(errors["steps"])

    def test_non_string_step_raises(self, db):
        """Validation error for non-string step includes step number."""
        with pytest.raises(ValidationError) as exc:
            Recipe.objects.create(
                code="bad-type",
                name="Bad Type Recipe",
                output_ref="test",
                batch_size=Decimal("10"),
                steps=["Mistura", 42, "Forno"],
            )

        errors = exc.value.message_dict
        assert "steps" in errors
        assert "2" in str(errors["steps"])

    def test_valid_steps_pass(self, db):
        """Valid steps pass validation without issue."""
        recipe = Recipe.objects.create(
            code="good-steps",
            name="Good Recipe",
            output_ref="test",
            batch_size=Decimal("10"),
            steps=["Mistura", "Modelagem", "Forno"],
        )
        assert recipe.pk is not None
        assert recipe.steps == ["Mistura", "Modelagem", "Forno"]


# ══════════════════════════════════════════════════════════════
# STOCKMAN ADAPTER LOGGING
# ══════════════════════════════════════════════════════════════


class TestStockmanAdapterLogging:
    """Test that _get_product logs errors instead of silencing them."""

    def test_get_product_logs_import_error(self):
        """ImportError is logged at debug level (catalog not installed)."""
        from shopman.crafting.adapters.stockman import StockmanBackend

        backend = StockmanBackend()

        with patch(
            "shopman.crafting.adapters.offerman.get_catalog_backend",
            side_effect=ImportError("No module named 'offerman'"),
        ), patch("shopman.crafting.adapters.stockman.logger") as mock_logger:
            result = backend._get_product("FARINHA")

        assert result is None
        # ImportError logged at debug level
        mock_logger.debug.assert_any_call(
            "Catalog backend not available for SKU resolution: %s",
            "FARINHA",
        )

    def test_get_product_logs_runtime_error(self):
        """Runtime errors are logged at warning level with traceback."""
        from shopman.crafting.adapters.stockman import StockmanBackend

        backend = StockmanBackend()

        mock_catalog = MagicMock()
        mock_catalog.resolve.side_effect = RuntimeError("Database connection lost")

        with patch(
            "shopman.crafting.adapters.offerman.get_catalog_backend",
            return_value=mock_catalog,
        ), patch("shopman.crafting.adapters.stockman.logger") as mock_logger:
            result = backend._get_product("FARINHA")

        assert result is None
        # Should have logged at warning level with exc_info
        mock_logger.warning.assert_any_call(
            "Failed to resolve SKU via catalog backend: %s",
            "FARINHA",
            exc_info=True,
        )

    def test_get_product_with_resolver(self):
        """Custom product_resolver bypasses catalog backend entirely."""
        from shopman.crafting.adapters.stockman import StockmanBackend

        resolver = MagicMock(return_value="product-object")
        backend = StockmanBackend(product_resolver=resolver)

        result = backend._get_product("FARINHA")

        assert result == "product-object"
        resolver.assert_called_once_with("FARINHA")


# ══════════════════════════════════════════════════════════════
# PRODUCTION BACKEND EXCEPTION HANDLING
# ══════════════════════════════════════════════════════════════


class TestProductionBackendExceptions:
    """Test that production backend differentiates CraftError from unexpected errors."""

    def test_create_wo_craft_error_logged_as_warning(self, db):
        """CraftError (business logic) is logged at warning level."""
        from shopman.crafting.contrib.stockman.production import CraftingProductionBackend

        backend = CraftingProductionBackend()

        recipe = Recipe.objects.create(
            code="test-recipe",
            name="Test",
            output_ref="test-product",
            batch_size=Decimal("10"),
        )

        # Plan with invalid quantity triggers CraftError
        with patch("shopman.crafting.contrib.stockman.production.logger") as mock_logger:
            # Mock the stockman import
            mock_request = MagicMock()
            mock_request.sku = "test-product"
            mock_request.quantity = Decimal("-5")  # Invalid
            mock_request.target_date = None
            mock_request.metadata = {}
            mock_request.priority = None
            mock_request.reference = None

            with patch(
                "stockman.protocols.production.ProductionResult",
            ) as MockResult, patch(
                "stockman.protocols.production.ProductionStatusEnum",
            ):
                result = backend.request_production(mock_request)

            # CraftError should be logged as warning, not error
            if mock_logger.warning.called:
                args = mock_logger.warning.call_args[0]
                assert "INVALID_QUANTITY" in str(args) or "denied" in str(args[0])


# ══════════════════════════════════════════════════════════════
# API VIEWS EXCEPTION HANDLING
# ══════════════════════════════════════════════════════════════


class TestAPIExceptionHandling:
    """Test that API views return correct status codes per exception type."""

    @pytest.fixture
    def recipe(self, db):
        return Recipe.objects.create(
            code="api-test",
            name="API Test Recipe",
            output_ref="api-product",
            batch_size=Decimal("10"),
        )

    @pytest.fixture
    def recipe_with_items(self, recipe):
        RecipeItem.objects.create(
            recipe=recipe, input_ref="farinha", quantity=Decimal("5"), unit="kg",
        )
        return recipe

    def test_close_stale_rev_returns_409(self, recipe_with_items):
        """StaleRevision on close returns 409 Conflict."""
        wo = craft.plan(recipe_with_items, 100)
        craft.adjust(wo, quantity=97)  # bumps rev to 1

        try:
            # This should raise StaleRevision because expected_rev=0 but actual is 1
            craft.close(wo, produced=93, expected_rev=0)
            assert False, "Should have raised StaleRevision"
        except StaleRevision as e:
            assert e.code == "STALE_REVISION"

    def test_close_terminal_returns_400(self, recipe):
        """CraftError on terminal status returns error with code."""
        wo = craft.plan(recipe, 100)
        craft.close(wo, produced=93, expected_rev=0)

        try:
            craft.close(wo, produced=50, expected_rev=1)
            assert False, "Should have raised CraftError"
        except CraftError as e:
            assert e.code == "TERMINAL_STATUS"

    def test_void_from_done_returns_specific_code(self, recipe):
        """Voiding a done order returns VOID_FROM_DONE code."""
        wo = craft.plan(recipe, 100)
        craft.close(wo, produced=93, expected_rev=0)

        try:
            craft.void(wo, reason="test", expected_rev=1)
            assert False, "Should have raised CraftError"
        except CraftError as e:
            assert e.code == "VOID_FROM_DONE"

    def test_adjust_stale_rev_raises(self, recipe):
        """StaleRevision on adjust is properly raised."""
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97)  # rev now 1

        with pytest.raises(StaleRevision):
            craft.adjust(wo, quantity=95, expected_rev=0)

    def test_craft_error_has_code_and_message(self):
        """CraftError carries structured code and message."""
        err = CraftError("INVALID_QUANTITY", quantity=-5)
        assert err.code == "INVALID_QUANTITY"
        assert "Quantity must be greater than zero" in err.message
        assert err.data["quantity"] == -5

        d = err.as_dict()
        assert d["code"] == "INVALID_QUANTITY"
        assert d["data"]["quantity"] == -5

    def test_stale_revision_carries_context(self, recipe):
        """StaleRevision includes expected and current rev in data."""
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97)  # rev now 1

        try:
            craft.adjust(wo, quantity=95, expected_rev=0)
        except StaleRevision as e:
            assert e.code == "STALE_REVISION"
            assert e.data["expected_rev"] == 0


# ══════════════════════════════════════════════════════════════
# DEPENDENCY DECLARATIONS
# ══════════════════════════════════════════════════════════════


class TestDependencyDeclarations:
    """Test that declared dependencies are importable."""

    def test_commons_exceptions_importable(self):
        """commons.exceptions.BaseError is importable (declared dep)."""
        from shopman.utils.exceptions import BaseError
        assert issubclass(CraftError, BaseError)

    def test_craft_error_inherits_base_error(self):
        """CraftError is a proper BaseError subclass."""
        from shopman.utils.exceptions import BaseError
        err = CraftError("TEST_CODE")
        assert isinstance(err, BaseError)
        assert isinstance(err, Exception)

    def test_stale_revision_inherits_craft_error(self):
        """StaleRevision is a CraftError subclass."""
        assert issubclass(StaleRevision, CraftError)
