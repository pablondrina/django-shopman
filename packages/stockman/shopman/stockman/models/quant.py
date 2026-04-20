"""
Quant model — Quantity cache at space-time coordinate.

IMPORTANT: `_quantity` is a denormalised cache — it MUST equal Σ(moves.delta).
The only correct way to change stock is through the Move ledger (stock.receive,
stock.issue, stock.adjust, etc.). Never bypass it with `.update(_quantity=...)`.

See: docs/guides/stockman.md § Integridade de `_quantity`
"""

import logging
from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from shopman.refs.fields import RefField

logger = logging.getLogger('shopman.stockman')


class QuantQuerySet(models.QuerySet):
    """
    QuerySet that guards against direct `_quantity` writes.

    `.update(_quantity=X)` bypasses the Move ledger and silently breaks the
    cache invariant.  Pass `_allow_quantity_update=True` only from trusted
    internals (Move.save, Quant.recalculate) that own the ledger.
    """

    def update(self, **kwargs):
        allow = kwargs.pop('_allow_quantity_update', False)
        if '_quantity' in kwargs and not allow:
            raise ValueError(
                "Quant._quantity é cache de Σ(moves.delta). "
                "Use stock.receive/issue/adjust em vez de .update(). "
                "Se você sabe o que está fazendo, passe _allow_quantity_update=True."
            )
        return super().update(**kwargs)


class QuantManager(models.Manager):
    """Manager with helper methods for Quant queries."""

    def get_queryset(self):
        return QuantQuerySet(self.model, using=self._db)

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

    INVARIANT: _quantity == Σ(moves.delta)
    - `_quantity` is a denormalised cache for O(1) availability reads.
    - It MUST NOT be written directly. All changes flow through Move.save().
    - Use recalculate() to audit or correct divergence.
    - Use `recompute_quant_quantities` management command in cron for health checks.
    """

    sku = RefField(
        ref_type="SKU",
        verbose_name=_('SKU'),
        max_length=100,
        db_index=True,
    )

    # Space-time coordinates
    position = models.ForeignKey(
        'stockman.Position',
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

    # Quantity cache — updated atomically by Move only. Never write directly.
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
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=models.Q(_quantity__gte=0),
                name='stk_quant_quantity_non_negative',
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
    # VALIDATION
    # ══════════════════════════════════════════════════════════════

    def clean(self):
        """
        Validate quantity cache consistency against Move ledger.

        Raises ValidationError in development when _quantity ≠ Σ(moves.delta).
        Not called automatically on save (performance); available for testing
        tools and `recompute_quant_quantities --dry-run`.
        """
        from django.core.exceptions import ValidationError

        computed = self._compute_quantity()
        if computed != self._quantity:
            raise ValidationError(
                f"Quant#{self.pk} _quantity ({self._quantity}) diverge de "
                f"Σ(moves.delta) ({computed}). "
                "Execute recompute_quant_quantities --apply para corrigir."
            )

    # ══════════════════════════════════════════════════════════════
    # METHODS
    # ══════════════════════════════════════════════════════════════

    def _compute_quantity(self) -> Decimal:
        """Compute expected quantity from Move ledger (no side-effects)."""
        return self.moves.aggregate(
            t=Coalesce(Sum('delta'), Decimal('0'))
        )['t']

    def recalculate(self) -> Decimal:
        """
        Recompute _quantity from Moves and persist if divergent.

        Use for:
        - Integrity audit (management command)
        - Correction after detected inconsistency
        - Debug

        Returns:
            Recomputed quantity (Σ moves.delta)
        """
        total = self._compute_quantity()

        if total != self._quantity:
            old = self._quantity
            self._quantity = total
            # model-level save bypasses QuantQuerySet.update guard — intentional
            self.save(update_fields=['_quantity', 'updated_at'])

            logger.error(
                "quant.quantity_mismatch",
                extra={
                    "pk": self.pk,
                    "sku": self.sku,
                    "position": str(self.position_id),
                    "current": float(old),
                    "computed": float(total),
                    "delta": float(total - old),
                },
            )

        return total

    def __str__(self) -> str:
        pos = self.position_id if self.position_id else '?'
        date_str = f"@{self.target_date}" if self.target_date else ""
        return f"Quant#{self.pk} [{self.sku} pos={pos}{date_str}]: {self._quantity}"
