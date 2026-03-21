"""CustomerInsight model (calculated metrics)."""

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _


class CustomerInsight(models.Model):
    """Calculated customer insights."""

    customer = models.OneToOneField(
        "attending.Customer",
        on_delete=models.CASCADE,
        related_name="insight",
        verbose_name=_("cliente"),
    )

    # Order metrics
    total_orders = models.IntegerField(_("total de pedidos"), default=0)
    total_spent_q = models.BigIntegerField(
        _("total gasto (centavos)"),
        default=0,
        help_text=_("Total gasto em centavos"),
    )
    average_ticket_q = models.BigIntegerField(
        _("ticket médio (centavos)"),
        default=0,
        help_text=_("Ticket médio em centavos"),
    )

    # Frequency
    first_order_at = models.DateTimeField(_("primeiro pedido em"), null=True, blank=True)
    last_order_at = models.DateTimeField(_("último pedido em"), null=True, blank=True)
    days_since_last_order = models.IntegerField(
        _("dias desde último pedido"),
        null=True,
        blank=True,
    )
    average_days_between_orders = models.DecimalField(
        _("média de dias entre pedidos"),
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
    )

    # Temporal patterns
    preferred_weekday = models.IntegerField(
        _("dia da semana preferido"),
        null=True,
        blank=True,
        help_text=_("0=Segunda, 6=Domingo"),
    )
    preferred_hour = models.IntegerField(
        _("hora preferida"),
        null=True,
        blank=True,
        help_text=_("Hora preferida (0-23)"),
    )

    # Favorite products (top 5 SKUs)
    favorite_products = models.JSONField(
        _("produtos favoritos"),
        default=list,
        help_text=_("Lista de {sku, nome, qtd, ultimo_pedido}"),
    )

    # Channels
    preferred_channel = models.CharField(
        _("canal preferido"),
        max_length=50,
        blank=True,
    )
    channels_used = models.JSONField(
        _("canais utilizados"),
        default=list,
        help_text=_("Lista de canais utilizados"),
    )

    # Automatic segmentation (RFM)
    rfm_recency = models.IntegerField(
        _("RFM recência"),
        null=True,
        blank=True,
        help_text=_("Score de recência RFM (1-5)"),
    )
    rfm_frequency = models.IntegerField(
        _("RFM frequência"),
        null=True,
        blank=True,
        help_text=_("Score de frequência RFM (1-5)"),
    )
    rfm_monetary = models.IntegerField(
        _("RFM monetário"),
        null=True,
        blank=True,
        help_text=_("Score monetário RFM (1-5)"),
    )
    rfm_segment = models.CharField(
        _("segmento RFM"),
        max_length=50,
        blank=True,
        help_text=_("Segmento RFM (ex: 'campeão', 'em_risco', 'novo')"),
    )

    # Churn risk
    churn_risk = models.DecimalField(
        _("risco de churn"),
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("0.00 a 1.00"),
    )

    # Lifetime Value
    predicted_ltv_q = models.BigIntegerField(
        _("LTV previsto (centavos)"),
        null=True,
        blank=True,
        help_text=_("LTV previsto em centavos"),
    )

    # Extension metadata
    metadata = models.JSONField(_("metadados"), default=dict, blank=True)

    # Calculation control
    calculated_at = models.DateTimeField(_("calculado em"), auto_now=True)
    calculation_version = models.CharField(
        _("versão do cálculo"),
        max_length=20,
        default="v1",
        help_text=_("Versão do algoritmo de cálculo"),
    )

    class Meta:
        verbose_name = _("insight do cliente")
        verbose_name_plural = _("insights dos clientes")

    def __str__(self):
        return f"Insight: {self.customer.ref}"

    @property
    def total_spent(self) -> Decimal:
        return Decimal(self.total_spent_q) / 100

    @property
    def average_ticket(self) -> Decimal:
        return Decimal(self.average_ticket_q) / 100

    @property
    def is_vip(self) -> bool:
        """Customer is VIP (champion in RFM)."""
        return self.rfm_segment in ("champion", "loyal_customer")

    @property
    def is_at_risk(self) -> bool:
        """Customer at churn risk."""
        return self.churn_risk is not None and self.churn_risk > Decimal("0.7")
