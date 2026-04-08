"""
StockAlert model — configurable min stock trigger per SKU.

Usage:
    StockAlert.objects.create(
        sku='PAO-FORMA',
        position=vitrine, min_quantity=10,
    )

    # Check alerts (in a periodic task or after stock changes)
    from shopman.stockman.services.alerts import check_alerts
    triggered = check_alerts()
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class StockAlert(models.Model):
    """
    Configurable stock alert per product (optionally per position).

    When available quantity drops below min_quantity, the alert is
    considered triggered.
    """

    sku = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name=_('SKU'),
    )

    # Optional position filter (None = all positions combined)
    position = models.ForeignKey(
        'stockman.Position',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alerts',
        verbose_name=_('Posição'),
        help_text=_('Vazio = soma de todas as posições'),
    )

    # Threshold
    min_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name=_('Quantidade Mínima'),
        help_text=_('Alerta dispara quando disponível < este valor'),
    )

    # Configuration
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Ativo'),
    )

    # Tracking
    last_triggered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Último disparo'),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Criado em'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Atualizado em'))

    class Meta:
        verbose_name = _('Alerta de Estoque')
        verbose_name_plural = _('Alertas de Estoque')
        constraints = [
            models.UniqueConstraint(
                fields=['sku', 'position'],
                name='unique_stock_alert_per_sku_position',
            ),
        ]
        indexes = [
            models.Index(fields=['sku'], name='stocking_sa_sku_idx'),
            models.Index(fields=['is_active'], name='stocking_sa_active_idx'),
        ]

    def __str__(self) -> str:
        pos = f" @ {self.position.ref}" if self.position else ""
        return f"Alert: {self.sku}{pos} < {self.min_quantity}"
