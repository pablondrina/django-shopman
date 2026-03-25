"""
Quant model — Quantity cache at space-time coordinate.
"""

from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _

from shopman.stocking.models.enums import HoldStatus


class QuantManager(models.Manager):
    """Manager with helper methods for Quant queries."""

    def for_sku(self, sku: str):
        """Filter quants for a specific SKU."""
        return self.filter(sku=sku)

    def physical(self):
        """Only physical stock (target_date=None or past)."""
        today = date.today()
        return self.filter(
            Q(target_date__isnull=True) | Q(target_date__lte=today)
        )

    def planned(self):
        """Only planned production (target_date in future)."""
        return self.filter(target_date__gt=date.today())

    def at_position(self, position):
        """Filter by position."""
        if position is None:
            return self.filter(position__isnull=True)
        return self.filter(position=position)


class Quant(models.Model):
    """
    Quantity of a product at a space-time coordinate.

    Coordinates:
    - position: WHERE (space) — can be null (unspecified)
    - target_date: WHEN (time) — null means "now/physical"

    Performance:
    - _quantity is cache updated atomically by Move
    - Read is O(1), not O(N)
    - Use recalculate() for audit/correction
    """

    sku = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name=_('SKU'),
    )

    # Space-time coordinates
    position = models.ForeignKey(
        'stocking.Position',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='quants',
        verbose_name=_('Posição'),
    )
    target_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_('Data Alvo'),
        help_text=_('Vazio = estoque físico. Data = produção planejada.'),
    )
    batch = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name=_('Lote'),
        help_text=_('Referência do lote (Batch.ref). Vazio = sem lote.'),
    )

    # Quantity cache (updated atomically by Move)
    _quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('0'),
        verbose_name=_('Quantidade'),
    )

    metadata = models.JSONField(
        default=dict, blank=True, verbose_name=_('Metadados'),
        help_text=_('Metadados do quant. Ex: {"batch": "2024-01", "supplier": "Moinho SP"}'),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('criado em'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('atualizado em'))

    objects = QuantManager()

    class Meta:
        verbose_name = _('Saldo')
        verbose_name_plural = _('Saldos')
        constraints = [
            models.UniqueConstraint(
                fields=['sku', 'position', 'target_date', 'batch'],
                name='unique_quant_coordinate',
            ),
        ]
        indexes = [
            models.Index(fields=['sku'], name='stocking_qu_sku_idx'),
            models.Index(fields=['target_date'], name='stocking_qu_target_idx'),
            models.Index(fields=['position', 'target_date'], name='stocking_qu_pos_tgt_idx'),
        ]

    # ══════════════════════════════════════════════════════════════
    # PROPERTIES
    # ══════════════════════════════════════════════════════════════

    @property
    def quantity(self) -> Decimal:
        """Total quantity — O(1) cache read."""
        return self._quantity

    @property
    def held(self) -> Decimal:
        """
        Held quantity — sum of active, non-expired holds.

        IMPORTANT: Ignores expired holds even if status is still PENDING/CONFIRMED.
        This ensures availability is always correct, regardless of cron timing.
        """
        return self.holds.active().aggregate(
            total=Coalesce(Sum('quantity'), Decimal('0'))
        )['total']

    @property
    def available(self) -> Decimal:
        """Available for new holds."""
        return self._quantity - self.held

    @property
    def is_future(self) -> bool:
        """Is planned production (doesn't exist physically yet)?"""
        if self.target_date is None:
            return False
        return self.target_date > date.today()

    # ══════════════════════════════════════════════════════════════
    # METHODS
    # ══════════════════════════════════════════════════════════════

    def recalculate(self) -> Decimal:
        """
        Recalculate quantity from Moves.

        Use for:
        - Integrity audit
        - Correction after detected inconsistency
        - Debug

        Returns:
            New calculated quantity
        """
        import logging

        total = self.moves.aggregate(
            t=Coalesce(Sum('delta'), Decimal('0'))
        )['t']

        if total != self._quantity:
            old = self._quantity
            self._quantity = total
            self.save(update_fields=['_quantity', 'updated_at'])

            logger = logging.getLogger('shopman.stocking')
            logger.warning(
                f"Quant {self.pk} recalculated: {old} → {total} "
                f"(diff: {total - old})"
            )

        return total

    def __str__(self) -> str:
        pos = self.position_id if self.position_id else '?'
        date_str = f"@{self.target_date}" if self.target_date else ""
        return f"Quant#{self.pk} [{self.sku} pos={pos}{date_str}]: {self._quantity}"
