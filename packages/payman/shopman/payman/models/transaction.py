from django.db import models
from django.utils.translation import gettext_lazy as _


class PaymentTransaction(models.Model):
    """
    Movimentação financeira vinculada a um PaymentIntent.

    Imutável: uma vez criada, não pode ser atualizada nem deletada.
    Correções são feitas via nova Transaction (ex: refund parcial adicional).
    Segue o mesmo padrão de Stocking.Move.
    """

    class Type(models.TextChoices):
        CAPTURE = "capture", _("Captura")
        REFUND = "refund", _("Reembolso")
        CHARGEBACK = "chargeback", _("Chargeback")

    intent = models.ForeignKey(
        "payman.PaymentIntent",
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    amount_q = models.BigIntegerField()
    gateway_id = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "payman"
        ordering = ["-created_at"]
        verbose_name = _("transação de pagamento")
        verbose_name_plural = _("transações de pagamento")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError(
                "Transações são imutáveis. "
                "Para corrigir, crie uma nova Transaction."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(
            "Transações são imutáveis. "
            "Para estornar, crie uma Transaction de refund."
        )

    def __str__(self) -> str:
        return f"{self.type} {self.amount_q}q → {self.intent.ref}"
