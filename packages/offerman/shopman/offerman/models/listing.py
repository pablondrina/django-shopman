"""Listing and ListingItem models."""

import uuid as uuid_lib
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords


class Listing(models.Model):
    """
    Product listing for a channel.

    A Listing defines which products are visible and at what price in a
    given sales channel. The association with Channel is by convention:
    Listing.ref matches Channel.ref (loose coupling, no FK).

    Commercial state per item is controlled at two levels:
    - Product level: Product.is_published, Product.is_sellable
    - Listing level: ListingItem.is_published, ListingItem.is_sellable

    Both levels must agree for a product to be visible and purchasable
    in a channel.

    Temporal validity: valid_from/valid_until gate the listing period.
    is_active gates the listing itself (admin toggle).
    """

    uuid = models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True, verbose_name=_("UUID"))

    ref = models.SlugField(max_length=50, unique=True, verbose_name=_("referência"))
    name = models.CharField(max_length=100, verbose_name=_("nome"))
    description = models.TextField(blank=True, verbose_name=_("descrição"))

    # Validity
    valid_from = models.DateField(null=True, blank=True, verbose_name=_("válido de"))
    valid_until = models.DateField(null=True, blank=True, verbose_name=_("válido até"))

    # Priority (higher = more specific)
    priority = models.IntegerField(default=0, verbose_name=_("prioridade"))

    is_active = models.BooleanField(default=True, verbose_name=_("ativo"))

    # Projection state for external catalog syncs. ``last_projected_skus`` is
    # used to detect removals on incremental sync; adapters may add metadata.
    projection_metadata = models.JSONField(
        _("metadados de projeção"),
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("criado em"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("atualizado em"))

    class Meta:
        verbose_name = _("Listagem")
        verbose_name_plural = _("Listagens")
        ordering = ["-priority", "name"]

    def __str__(self):
        return f"{self.ref} - {self.name}"

    def is_valid(self, date=None) -> bool:
        """Check if listing is valid for a given date."""
        if not self.is_active:
            return False
        date = date or timezone.now().date()
        if self.valid_from and date < self.valid_from:
            return False
        if self.valid_until and date > self.valid_until:
            return False
        return True


class ListingItem(models.Model):
    """Product in a listing with channel-level pricing and commercial state."""

    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("listagem"),
    )
    product = models.ForeignKey(
        "offerman.Product",
        on_delete=models.CASCADE,
        related_name="listing_items",
        verbose_name=_("produto"),
    )

    # Price
    price_q = models.BigIntegerField(
        help_text=_("Preço em centavos"),
        verbose_name=_("preço"),
        validators=[MinValueValidator(0)],
    )

    # Quantity discount (optional)
    min_qty = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal("1"),
        verbose_name=_("quantidade mínima"),
    )

    # Publication and sellability in this listing
    is_published = models.BooleanField(default=True, verbose_name=_("publicado"))
    is_sellable = models.BooleanField(
        default=True,
        verbose_name=_("vendável"),
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("criado em"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("atualizado em"))

    # History tracking (price changes audit)
    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Item de Listagem")
        verbose_name_plural = _("Itens de Listagem")
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "product", "min_qty"],
                name="unique_listing_product_min_qty",
            ),
        ]
        ordering = ["listing", "product__name"]

    def __str__(self):
        return f"{self.product.sku} @ {self.listing.ref}"

    def save(self, *args, **kwargs):
        old_price_q = None
        if not self._state.adding:
            try:
                old = ListingItem.objects.filter(pk=self.pk).values_list("price_q", flat=True).first()
                if old is not None and old != self.price_q:
                    old_price_q = old
            except Exception:
                pass
        super().save(*args, **kwargs)
        if old_price_q is not None:
            from shopman.offerman.signals import price_changed

            price_changed.send(
                sender=self.__class__,
                instance=self,
                listing_ref=self.listing.ref,
                sku=self.product.sku,
                old_price_q=old_price_q,
                new_price_q=self.price_q,
            )

    @property
    def price(self) -> Decimal:
        return Decimal(self.price_q) / 100
