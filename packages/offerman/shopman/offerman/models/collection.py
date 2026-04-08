"""Collection and CollectionItem models."""

import uuid as uuid_lib

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Collection(models.Model):
    """
    Unified product grouping.

    Can behave as Category (hierarchical) or Collection (flat, temporal).
    """

    uuid = models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True, verbose_name=_("UUID"))

    slug = models.SlugField(max_length=50, unique=True, verbose_name=_("slug"))
    name = models.CharField(max_length=100, verbose_name=_("nome"))
    description = models.TextField(blank=True, verbose_name=_("descrição"))

    # Hierarchy (optional)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
        verbose_name=_("coleção pai"),
    )

    # Temporality
    valid_from = models.DateField(null=True, blank=True, verbose_name=_("válido de"))
    valid_until = models.DateField(null=True, blank=True, verbose_name=_("válido até"))

    sort_order = models.IntegerField(default=0, verbose_name=_("ordem"))
    is_active = models.BooleanField(default=True, verbose_name=_("ativo"))

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("criado em"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("atualizado em"))

    class Meta:
        verbose_name = _("Coleção")
        verbose_name_plural = _("Coleções")
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def is_valid(self, date=None) -> bool:
        """Check if collection is valid for a given date."""
        if not self.is_active:
            return False
        date = date or timezone.now().date()
        if self.valid_from and date < self.valid_from:
            return False
        if self.valid_until and date > self.valid_until:
            return False
        return True

    def clean(self):
        """Validate no circular parent reference and enforce max depth."""
        from shopman.offerman.conf import offering_settings

        if self.parent_id:
            visited = {self.pk}
            current = self.parent
            depth = 1
            while current:
                if current.pk in visited:
                    raise ValidationError({"parent": "Circular reference detected."})
                visited.add(current.pk)
                depth += 1
                current = current.parent

            if depth > offering_settings.MAX_COLLECTION_DEPTH:
                raise ValidationError(
                    {"parent": f"Max collection depth ({offering_settings.MAX_COLLECTION_DEPTH}) exceeded."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def full_path(self) -> str:
        """Returns full path: 'Category > Subcategory > Collection'."""
        if self.parent:
            return f"{self.parent.full_path} > {self.name}"
        return self.name

    @property
    def depth(self) -> int:
        """Returns depth in hierarchy (0 for root)."""
        if self.parent:
            return self.parent.depth + 1
        return 0

    def get_ancestors(self, max_depth: int | None = None) -> list["Collection"]:
        """Returns list of ancestors from root to parent."""
        if max_depth is None:
            from shopman.offerman.conf import offering_settings

            max_depth = offering_settings.MAX_COLLECTION_DEPTH
        ancestors = []
        current = self.parent
        depth = 0
        while current and depth < max_depth:
            ancestors.insert(0, current)
            current = current.parent
            depth += 1
        return ancestors

    def get_descendants(self, max_depth: int | None = None, _depth: int = 0) -> list["Collection"]:
        """Returns all descendants (children, grandchildren, etc.)."""
        if max_depth is None:
            from shopman.offerman.conf import offering_settings

            max_depth = offering_settings.MAX_COLLECTION_DEPTH
        if _depth >= max_depth:
            return []
        children = list(self.children.all())
        descendants = list(children)
        for child in children:
            descendants.extend(child.get_descendants(max_depth=max_depth, _depth=_depth + 1))
        return descendants


class CollectionItem(models.Model):
    """Product membership in a collection."""

    collection = models.ForeignKey(
        Collection,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("coleção"),
    )
    product = models.ForeignKey(
        "offerman.Product",
        on_delete=models.CASCADE,
        related_name="collection_items",
        verbose_name=_("produto"),
    )

    is_primary = models.BooleanField(
        default=False,
        help_text=_("Coleção principal para este produto"),
        verbose_name=_("principal"),
    )
    sort_order = models.IntegerField(default=0, verbose_name=_("ordem"))

    class Meta:
        verbose_name = _("Item de Coleção")
        verbose_name_plural = _("Itens de Coleção")
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "product"],
                name="unique_collection_product",
            ),
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_primary=True),
                name="unique_primary_collection_per_product",
            ),
        ]
        ordering = ["sort_order"]

    def __str__(self):
        primary = " (principal)" if self.is_primary else ""
        return f"{self.product.sku} em {self.collection.slug}{primary}"

    def save(self, *args, **kwargs):
        if self.is_primary:
            # Ensure only one primary collection per product
            CollectionItem.objects.filter(
                product=self.product,
                is_primary=True,
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)
