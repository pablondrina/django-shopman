from __future__ import annotations

from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class PaymentIntent(models.Model):
    """
    Intenção de pagamento vinculada a um pedido via order_ref (string, sem FK).

    Lifecycle:
        pending → authorized → captured
        pending → failed
        pending → cancelled
        authorized → cancelled
        authorized → failed
        captured → refunded (via PaymentTransaction)

    Domain contracts:
        - Capture is single-shot: once CAPTURED, no further capture is allowed.
          Partial capture means the uncaptured balance is abandoned.
        - REFUNDED means "at least one refund exists", NOT "fully refunded".
          Use ``PaymentService.refunded_total(ref)`` for the actual refund amount.
        - Multiple partial refunds are allowed while captured balance remains.
        - All mutations must go through ``PaymentService``, not direct model saves.
          ``transition_status()`` is an internal concurrency helper only.

    Inspiração: Stripe PaymentIntent + Orderman Order status machine.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pendente")
        AUTHORIZED = "authorized", _("Autorizado")
        CAPTURED = "captured", _("Capturado")
        FAILED = "failed", _("Falhou")
        CANCELLED = "cancelled", _("Cancelado")
        REFUNDED = "refunded", _("Reembolsado")

    class Method(models.TextChoices):
        PIX = "pix", _("PIX")
        CASH = "cash", _("Dinheiro")
        CARD = "card", _("Cartão")
        EXTERNAL = "external", _("Externo")

    TRANSITIONS = {
        Status.PENDING: [Status.AUTHORIZED, Status.FAILED, Status.CANCELLED],
        Status.AUTHORIZED: [Status.CAPTURED, Status.CANCELLED, Status.FAILED],
        Status.CAPTURED: [Status.REFUNDED],
        Status.FAILED: [],
        Status.CANCELLED: [],
        Status.REFUNDED: [],
    }

    TERMINAL_STATUSES = [Status.FAILED, Status.CANCELLED, Status.REFUNDED]

    STATUS_TIMESTAMP_FIELDS = {
        Status.AUTHORIZED: "authorized_at",
        Status.CAPTURED: "captured_at",
        Status.CANCELLED: "cancelled_at",
    }

    ref = models.CharField(unique=True, max_length=64)
    order_ref = models.CharField(max_length=64, db_index=True)
    method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    amount_q = models.BigIntegerField()
    currency = models.CharField(max_length=3, default="BRL")
    gateway = models.CharField(max_length=50, blank=True, default="")
    gateway_id = models.CharField(max_length=200, blank=True, default="")
    gateway_data = models.JSONField(
        default=dict, blank=True,
        help_text=_('Dados de resposta do gateway. Populado automaticamente. Ex: {"pix_qr_code": "00020126...", "txid": "abc123"}'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    authorized_at = models.DateTimeField(null=True, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        app_label = "payman"
        ordering = ["-created_at"]
        verbose_name = _("intenção de pagamento")
        verbose_name_plural = _("intenções de pagamento")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_q__gt=0),
                name="pay_intent_amount_q_positive",
            ),
            models.UniqueConstraint(
                fields=["gateway", "gateway_id"],
                condition=~models.Q(gateway_id=""),
                name="pay_intent_gateway_id_unique",
            ),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_status = self.status

    def __str__(self) -> str:
        return f"{self.ref} ({self.method}/{self.status})"

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATUSES

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.TRANSITIONS.get(self.status, [])

    def save(self, *args, **kwargs):
        status_changed = self.pk and self.status != self._original_status

        if status_changed:
            from shopman.payman.exceptions import PaymentError

            allowed = self.TRANSITIONS.get(self._original_status, [])
            if self.status not in allowed:
                raise PaymentError(
                    code="invalid_transition",
                    message=f"Transição {self._original_status} → {self.status} não permitida",
                    context={
                        "current_status": self._original_status,
                        "requested_status": self.status,
                        "allowed_transitions": [str(s) for s in allowed],
                    },
                )

            ts_field = self.STATUS_TIMESTAMP_FIELDS.get(self.status)
            if ts_field and getattr(self, ts_field) is None:
                setattr(self, ts_field, timezone.now())

        super().save(*args, **kwargs)
        self._original_status = self.status

    @transaction.atomic
    def transition_status(self, new_status: str) -> None:
        """
        Transiciona o status com select_for_update() para segurança concorrente.

        Raises:
            PaymentError: Se a transição não for permitida
        """
        locked = PaymentIntent.objects.select_for_update().get(pk=self.pk)
        locked.status = new_status
        locked.save()

        for field in self._meta.get_fields():
            if hasattr(field, "attname"):
                setattr(self, field.attname, getattr(locked, field.attname))
        self._original_status = locked._original_status
