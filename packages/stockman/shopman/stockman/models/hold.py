"""
Hold model — Temporary quantity reservation.
"""

from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from shopman.stockman.models.enums import HoldStatus


class HoldQuerySet(models.QuerySet):
    """Custom QuerySet for Hold with convenience filters."""

    def active(self):
        """Active holds: PENDING/CONFIRMED and not expired."""
        now = timezone.now()
        return self.filter(
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gte=now)
        )

    def expired(self):
        """Expired holds: PENDING/CONFIRMED with expires_at in the past."""
        now = timezone.now()
        return self.filter(
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
            expires_at__lt=now,
        )

    def fulfillable(self):
        """Holds ready for fulfillment: CONFIRMED, not expired, with linked quant."""
        return self.active().filter(
            status=HoldStatus.CONFIRMED,
            quant__isnull=False,
        )


class Hold(models.Model):
    """
    Quantity hold for a customer/order.

    LIFECYCLE:

    ┌─────────────────────────────────────────────────────────────┐
    │                                                             │
    │   ┌─────────┐    confirm()    ┌───────────┐    fulfill()   │
    │   │ PENDING │ ──────────────► │ CONFIRMED │ ──────────────►│
    │   └─────────┘                 └───────────┘                │
    │        │                            │                       │
    │        │ release()                  │ release()             │
    │        ▼                            ▼                       │
    │   ┌──────────────────────────────────┐      ┌───────────┐  │
    │   │           RELEASED               │      │ FULFILLED │  │
    │   └──────────────────────────────────┘      └───────────┘  │
    │                                                             │
    └─────────────────────────────────────────────────────────────┘

    TWO OPERATION MODES:

    1. RESERVATION (quant filled):
       - Hold linked to existing Quant
       - Quantity is "locked" for this customer
       - Decrements Quant.available

    2. DEMAND (quant=None):
       - Customer wants, but no stock/production
       - Used for planning ("how many want for Friday?")
       - Auto-links when production is planned (via hook)
    """

    # Product SKU
    sku = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name=_('SKU'),
    )

    # Link to stock (None = demand)
    quant = models.ForeignKey(
        'stockman.Quant',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='holds',
        verbose_name=_('Estoque Vinculado'),
        help_text=_('Vazio = demanda (cliente quer, mas não há estoque)'),
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name=_('Quantidade'),
    )
    target_date = models.DateField(
        db_index=True,
        verbose_name=_('Data Desejada'),
    )

    status = models.CharField(
        max_length=20,
        choices=HoldStatus.choices,
        default=HoldStatus.PENDING,
        db_index=True,
        verbose_name=_('Status'),
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_('Expira em'),
        help_text=_('Se não concluído até esta data, será liberado automaticamente'),
    )

    created_at = models.DateTimeField(default=timezone.now, verbose_name=_('criado em'))
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Resolvido em'),
        help_text=_('Data de fulfillment ou release'),
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name=_('Metadados'))

    objects = HoldQuerySet.as_manager()

    class Meta:
        verbose_name = _('Reserva')
        verbose_name_plural = _('Reservas')
        indexes = [
            models.Index(fields=['status', 'expires_at'], name='stocking_ho_status_exp_idx'),
            models.Index(fields=['sku', 'target_date'], name='stocking_ho_sku_tgt_idx'),
            models.Index(fields=['status', 'quant'], name='stocking_ho_status_qnt_idx'),
        ]

    @property
    def is_demand(self) -> bool:
        """Is this a demand (no linked stock)?"""
        return self.quant is None

    @property
    def is_reservation(self) -> bool:
        """Is this a reservation (with linked stock)?"""
        return self.quant is not None

    @property
    def is_active(self) -> bool:
        """
        Is active (pending or confirmed AND not expired)?

        A hold is only truly active if:
        1. Status is PENDING or CONFIRMED
        2. AND either has no expiration OR expiration is in the future
        """
        if self.status not in [HoldStatus.PENDING, HoldStatus.CONFIRMED]:
            return False
        if self.expires_at is None:
            return True
        return timezone.now() <= self.expires_at

    @property
    def is_expired(self) -> bool:
        """Has expired?"""
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    @property
    def can_fulfill(self) -> bool:
        """Can this hold be fulfilled? Must be CONFIRMED, not expired, with linked quant."""
        return (
            self.status == HoldStatus.CONFIRMED
            and not self.is_expired
            and self.quant is not None
        )

    @property
    def hold_id(self) -> str:
        """Return hold identifier in standard format."""
        return f"hold:{self.pk}"

    def __str__(self) -> str:
        mode = "📋" if self.is_demand else "🔒"
        status_emoji = {
            HoldStatus.PENDING: '⏳',
            HoldStatus.CONFIRMED: '✓',
            HoldStatus.FULFILLED: '✅',
            HoldStatus.RELEASED: '↩',
        }
        emoji = status_emoji.get(self.status, '?')
        return f"{mode}{emoji} {self.quantity}x {self.sku} ({self.target_date})"
