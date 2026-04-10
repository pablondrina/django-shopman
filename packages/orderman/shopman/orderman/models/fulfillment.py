from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class Fulfillment(models.Model):
    """
    Fulfillment de um pedido (ou parte dele).

    Lifecycle: pending → in_progress → dispatched → delivered (ou cancelled)
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("pendente")
        IN_PROGRESS = "in_progress", _("em andamento")
        DISPATCHED = "dispatched", _("despachado")
        DELIVERED = "delivered", _("entregue")
        CANCELLED = "cancelled", _("cancelado")

    TRANSITIONS = {
        Status.PENDING: [Status.IN_PROGRESS, Status.CANCELLED],
        Status.IN_PROGRESS: [Status.DISPATCHED, Status.CANCELLED],
        Status.DISPATCHED: [Status.DELIVERED],
        Status.DELIVERED: [],
        Status.CANCELLED: [],
    }

    order = models.ForeignKey(
        "orderman.Order",
        verbose_name=_("pedido"),
        on_delete=models.CASCADE,
        related_name="fulfillments",
    )

    status = models.CharField(
        _("status"),
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    tracking_code = models.CharField(_("código de rastreio"), max_length=128, blank=True, default="")
    tracking_url = models.URLField(_("URL de rastreio"), blank=True, default="")
    carrier = models.CharField(_("transportadora"), max_length=64, blank=True, default="")
    notes = models.TextField(_("observações"), blank=True, default="")
    meta = models.JSONField(
        _("metadados"), default=dict, blank=True,
        help_text=_('Metadados de entrega. Ex: {"tracking_code": "BR123", "carrier": "correios"}'),
    )

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)
    dispatched_at = models.DateTimeField(_("despachado em"), null=True, blank=True)
    delivered_at = models.DateTimeField(_("entregue em"), null=True, blank=True)

    class Meta:
        app_label = "orderman"
        verbose_name = _("fulfillment")
        verbose_name_plural = _("fulfillments")
        ordering = ("-created_at",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_status = self.status

    def __str__(self) -> str:
        return f"Fulfillment #{self.pk} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if self.pk and self.status != self._original_status:
            from shopman.orderman.exceptions import InvalidTransition

            allowed = self.TRANSITIONS.get(self._original_status, [])
            if self.status not in allowed:
                raise InvalidTransition(
                    code="invalid_transition",
                    message=f"Fulfillment: {self._original_status} → {self.status} não permitida",
                    context={
                        "current_status": self._original_status,
                        "requested_status": self.status,
                        "allowed_transitions": [str(s) for s in allowed],
                    },
                )

            # Auto-set timestamps on transition
            from django.utils import timezone

            if self.status == self.Status.DISPATCHED and not self.dispatched_at:
                self.dispatched_at = timezone.now()
            elif self.status == self.Status.DELIVERED and not self.delivered_at:
                self.delivered_at = timezone.now()

        super().save(*args, **kwargs)
        self._original_status = self.status


class FulfillmentItem(models.Model):
    """Item incluído em um fulfillment."""

    fulfillment = models.ForeignKey(
        Fulfillment,
        verbose_name=_("fulfillment"),
        on_delete=models.CASCADE,
        related_name="items",
    )
    order_item = models.ForeignKey(
        "orderman.OrderItem",
        verbose_name=_("item do pedido"),
        on_delete=models.CASCADE,
        related_name="fulfillment_items",
    )
    qty = models.DecimalField(_("quantidade"), max_digits=12, decimal_places=3)

    class Meta:
        app_label = "orderman"
        verbose_name = _("item do fulfillment")
        verbose_name_plural = _("itens do fulfillment")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(qty__gt=0),
                name="ord_fulfillment_item_qty_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order_item.sku} x {self.qty}"
