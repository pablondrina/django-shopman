"""
Batch model — lot/batch traceability for products with expiry.

Usage:
    batch = Batch.objects.create(
        ref="LOT-2026-0223-A",
        sku='CROISSANT',
        production_date=date.today(),
        expiry_date=date.today() + timedelta(days=3),
        supplier="Fornecedor ABC",
    )

    stock.receive(50, 'CROISSANT', vitrine, batch=batch)
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class BatchQuerySet(models.QuerySet):
    """Custom QuerySet for Batch with convenience filters."""

    def active(self):
        """Batches with remaining stock (at least one non-empty quant)."""
        return self.filter(quants___quantity__gt=0).distinct()

    def expiring_before(self, date):
        """Batches expiring on or before the given date."""
        return self.filter(expiry_date__lte=date, expiry_date__isnull=False)

    def expired(self):
        """Batches past their expiry date."""
        from datetime import date as date_cls
        return self.expiring_before(date_cls.today())

    def for_sku(self, sku: str):
        """Filter batches for a specific SKU."""
        return self.filter(sku=sku)


class Batch(models.Model):
    """
    Batch/lot for traceability of products with expiry.

    A Batch groups stock by production lot. Each Quant can optionally
    reference a Batch via FK (Quant.batch → Batch).
    """

    ref = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_('Referência do Lote'),
        help_text=_('Identificador único do lote (ex: CRO-20260319-M).'),
    )

    sku = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name=_('SKU'),
    )

    # Dates
    production_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('Data de Produção'),
    )
    expiry_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_('Data de Validade'),
        help_text=_('Último dia em que o lote pode ser vendido/utilizado'),
    )

    # Supplier / origin
    supplier = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name=_('Fornecedor'),
    )

    # Notes
    notes = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Observações'),
    )

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Criado em'))

    objects = BatchQuerySet.as_manager()

    class Meta:
        verbose_name = _('Lote')
        verbose_name_plural = _('Lotes')
        ordering = ['expiry_date', 'production_date']
        indexes = [
            models.Index(fields=['sku'], name='stocking_ba_sku_idx'),
            models.Index(fields=['expiry_date'], name='stocking_ba_expiry_idx'),
        ]

    @property
    def is_expired(self) -> bool:
        """Is this batch past its expiry date?"""
        if self.expiry_date is None:
            return False
        from datetime import date
        return date.today() > self.expiry_date

    def __str__(self) -> str:
        expiry = f" (val:{self.expiry_date})" if self.expiry_date else ""
        return f"Lote {self.ref}{expiry}"
