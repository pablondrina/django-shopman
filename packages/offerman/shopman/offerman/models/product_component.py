"""ProductComponent model."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class ProductComponent(models.Model):
    """
    Component of a product.

    If a Product has components, it IS a bundle/combo.
    There is no separate Bundle model - the composition defines the bundle.
    """

    parent = models.ForeignKey(
        "offerman.Product",
        on_delete=models.CASCADE,
        related_name="components",
        verbose_name=_("produto pai"),
    )
    component = models.ForeignKey(
        "offerman.Product",
        on_delete=models.PROTECT,
        related_name="used_in_bundles",
        verbose_name=_("componente"),
    )
    qty = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal("1"),
        verbose_name=_("quantidade"),
        validators=[MinValueValidator(Decimal('0.001'))],
    )

    class Meta:
        verbose_name = _("Componente de Produto")
        verbose_name_plural = _("Componentes de Produto")
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "component"],
                name="unique_parent_component",
            ),
        ]

    def __str__(self):
        return f"{self.qty}x {self.component.sku} em {self.parent.sku}"

    def clean(self):
        """Validation: cannot be component of itself, no cycles, max depth."""
        from shopman.offerman.conf import offerman_settings

        if self.parent_id == self.component_id:
            raise ValidationError("Product cannot be component of itself")

        # Check for circular reference and depth
        is_circular, depth = self._check_depth_and_cycles()
        if is_circular:
            raise ValidationError("Circular component reference detected")

        if depth > offerman_settings.BUNDLE_MAX_DEPTH:
            raise ValidationError(
                f"Max bundle depth ({offerman_settings.BUNDLE_MAX_DEPTH}) exceeded."
            )

    def _check_depth_and_cycles(self) -> tuple[bool, int]:
        """Check for circular references and return max depth."""
        visited = {self.parent_id}
        max_depth = 1

        def check_descendants(product_id, current_depth):
            nonlocal max_depth
            if product_id in visited:
                return True
            visited.add(product_id)
            max_depth = max(max_depth, current_depth)

            # Get components of this product
            components = ProductComponent.objects.filter(parent_id=product_id)
            for comp in components:
                if check_descendants(comp.component_id, current_depth + 1):
                    return True
            return False

        # Check if parent appears in component's descendants
        is_circular = check_descendants(self.component_id, 2)
        return is_circular, max_depth

    def _has_circular_reference(self) -> bool:
        """Check if adding this component creates a circular reference."""
        is_circular, _ = self._check_depth_and_cycles()
        return is_circular

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
