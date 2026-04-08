"""Loyalty models — points, stamps, tiers, and transactions."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class LoyaltyTier(models.TextChoices):
    """Customer loyalty tiers."""

    BRONZE = "bronze", _("Bronze")
    SILVER = "silver", _("Prata")
    GOLD = "gold", _("Ouro")
    PLATINUM = "platinum", _("Platina")


class TransactionType(models.TextChoices):
    """Loyalty transaction types."""

    EARN = "earn", _("Acúmulo")
    REDEEM = "redeem", _("Resgate")
    ADJUST = "adjust", _("Ajuste")
    EXPIRE = "expire", _("Expiração")
    STAMP = "stamp", _("Carimbo")


class LoyaltyAccount(models.Model):
    """
    Customer loyalty account.

    One account per customer. Tracks points balance, lifetime points,
    stamps progress, and tier.

    Supports two program modes:
    - Points: earn and redeem points (like airline miles)
    - Stamps: collect stamps toward a reward (like coffee cards)

    Both can coexist — stamps_current/stamps_target for stamp programs,
    points_balance/lifetime_points for points programs.
    """

    customer = models.OneToOneField(
        "guestman.Customer",
        on_delete=models.CASCADE,
        related_name="loyalty_account",
        verbose_name=_("cliente"),
    )

    # Points program
    points_balance = models.IntegerField(
        _("saldo de pontos"),
        default=0,
        help_text=_("Pontos disponíveis para resgate"),
    )
    lifetime_points = models.IntegerField(
        _("pontos acumulados"),
        default=0,
        help_text=_("Total de pontos já acumulados (nunca decresce)"),
    )

    # Stamps program
    stamps_current = models.IntegerField(
        _("carimbos atuais"),
        default=0,
        help_text=_("Carimbos na cartela atual"),
    )
    stamps_target = models.IntegerField(
        _("meta de carimbos"),
        default=10,
        help_text=_("Carimbos necessários para o prêmio"),
    )
    stamps_completed = models.IntegerField(
        _("cartelas completas"),
        default=0,
        help_text=_("Total de cartelas já completadas"),
    )

    # Tier
    tier = models.CharField(
        _("nível"),
        max_length=20,
        choices=LoyaltyTier.choices,
        default=LoyaltyTier.BRONZE,
    )

    # Status
    is_active = models.BooleanField(_("ativo"), default=True)
    enrolled_at = models.DateTimeField(_("inscrito em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("conta de fidelidade")
        verbose_name_plural = _("contas de fidelidade")

    def __str__(self):
        return f"{self.customer.ref}: {self.points_balance}pts | {self.tier}"

    @property
    def stamps_remaining(self) -> int:
        """Stamps remaining to complete current card."""
        return max(0, self.stamps_target - self.stamps_current)

    @property
    def stamps_progress_percent(self) -> int:
        """Stamp card completion percentage (0-100)."""
        if self.stamps_target <= 0:
            return 100
        return min(100, int(self.stamps_current / self.stamps_target * 100))


class LoyaltyTransaction(models.Model):
    """
    Immutable record of a loyalty transaction.

    Every point earn, redeem, adjustment, or stamp is logged here.
    Transactions are append-only — never modified or deleted.
    """

    account = models.ForeignKey(
        LoyaltyAccount,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name=_("conta"),
    )

    transaction_type = models.CharField(
        _("tipo"),
        max_length=20,
        choices=TransactionType.choices,
    )
    points = models.IntegerField(
        _("pontos"),
        help_text=_("Positivo para acúmulo, negativo para resgate/expiração"),
    )
    balance_after = models.IntegerField(
        _("saldo após"),
        help_text=_("Saldo de pontos após esta transação"),
    )

    description = models.CharField(
        _("descrição"),
        max_length=200,
        help_text=_("Motivo da transação"),
    )
    reference = models.CharField(
        _("referência"),
        max_length=100,
        blank=True,
        help_text=_("ID externo (ex: order:123)"),
    )

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True, db_index=True)
    created_by = models.CharField(
        _("criado por"),
        max_length=100,
        blank=True,
    )

    class Meta:
        verbose_name = _("transação de fidelidade")
        verbose_name_plural = _("transações de fidelidade")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["account", "-created_at"]),
        ]

    def __str__(self):
        sign = "+" if self.points > 0 else ""
        return f"{sign}{self.points}pts — {self.description}"
