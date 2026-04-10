"""
Move model — Immutable ledger of quantity changes.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Move(models.Model):
    """
    Immutable record of quantity change.
    
    Rules:
    - NEVER update() or delete()
    - Corrections are new Moves with inverse delta
    - Updates Quant._quantity atomically on save()
    
    This is the ONLY model that changes quantity.
    """
    
    quant = models.ForeignKey(
        'stockman.Quant',
        on_delete=models.PROTECT,
        related_name='moves',
        verbose_name=_('Saldo'),
    )
    
    delta = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name=_('Variação'),
        help_text=_('Positivo = entrada, Negativo = saída'),
    )
    
    reason = models.CharField(
        max_length=255,
        verbose_name=_('Motivo'),
        help_text=_('Obrigatório. Ex: "Produção manhã", "Venda #123"'),
    )
    metadata = models.JSONField(
        default=dict, blank=True, verbose_name=_('Metadados'),
        help_text=_('Metadados do movimento. Ex: {"reason_detail": "Ajuste de inventário"}'),
    )
    
    timestamp = models.DateTimeField(default=timezone.now, db_index=True, verbose_name=_('Data/Hora'))
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Usuário'),
    )
    
    class Meta:
        verbose_name = _('Movimento')
        verbose_name_plural = _('Movimentos')
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['quant', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]
    
    def save(self, *args, **kwargs):
        """Save move and update quant cache atomically."""
        # Immutability check
        if self.pk:
            raise ValueError(
                "Movimentos são imutáveis. "
                "Para corrigir, crie um novo Move com delta inverso."
            )
        
        # Validations
        if not self.reason:
            raise ValueError("Motivo é obrigatório")
        
        # Save and update cache atomically
        with transaction.atomic():
            super().save(*args, **kwargs)
            
            # Import here to avoid circular import
            from shopman.stockman.models.quant import Quant
            
            # Update Quant cache using F() for atomicity
            Quant.objects.filter(pk=self.quant_id).update(
                _quantity=F('_quantity') + self.delta,
                updated_at=timezone.now()
            )

            # Verify non-negative invariant (catch before DB constraint)
            if self.delta < 0:
                new_qty = Quant.objects.values_list('_quantity', flat=True).get(
                    pk=self.quant_id
                )
                if new_qty < 0:
                    from shopman.stockman.exceptions import StockError
                    raise StockError(
                        'INSUFFICIENT_QUANTITY',
                        available=new_qty - self.delta,
                        requested=abs(self.delta),
                    )
    
    def delete(self, *args, **kwargs):
        """Prevent deletion — moves are immutable."""
        raise ValueError(
            "Movimentos são imutáveis. "
            "Para estornar, crie um novo Move com delta inverso."
        )
    
    def __str__(self) -> str:
        signal = '+' if self.delta > 0 else ''
        return f"{signal}{self.delta} | {self.reason}"


