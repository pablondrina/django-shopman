"""DeliveryZone — zonas de entrega configuráveis com taxa por CEP, bairro ou cidade."""

from __future__ import annotations

from django.db import models


class DeliveryZone(models.Model):
    """
    Zona de entrega com taxa.

    Pertence a uma Shop (singleton). Gerenciada como inline no ShopAdmin.

    Matching order (prioridade):
      1. cep_prefix  — prefixo do CEP (ex: "860" cobre 860xx-xxx)
      2. neighborhood — bairro exato (case-insensitive)

    O DeliveryFeeModifier usa esse modelo para calcular a taxa de entrega.
    fee_q == 0 → entrega grátis.
    """

    ZONE_TYPE_CEP_PREFIX = "cep_prefix"
    ZONE_TYPE_NEIGHBORHOOD = "neighborhood"

    ZONE_TYPE_CHOICES = [
        (ZONE_TYPE_CEP_PREFIX, "Prefixo de CEP"),
        (ZONE_TYPE_NEIGHBORHOOD, "Bairro"),
    ]

    shop = models.ForeignKey(
        "shop.Shop",
        on_delete=models.CASCADE,
        related_name="delivery_zones",
        verbose_name="loja",
    )
    name = models.CharField("nome", max_length=100)
    zone_type = models.CharField(
        "tipo de zona",
        max_length=20,
        choices=ZONE_TYPE_CHOICES,
        default=ZONE_TYPE_CEP_PREFIX,
    )
    match_value = models.CharField(
        "valor de correspondência",
        max_length=100,
        help_text=(
            "Para 'Prefixo de CEP': dígitos iniciais sem hífen (ex: '860' cobre 860xx-xxx). "
            "Para 'Bairro': nome exato do bairro (comparação sem maiúsculas/minúsculas). "
        ),
    )
    fee_q = models.PositiveIntegerField(
        "taxa de entrega (centavos)",
        default=0,
        help_text="Taxa em centavos. 0 = entrega grátis.",
    )
    is_active = models.BooleanField("ativo", default=True)
    sort_order = models.PositiveSmallIntegerField(
        "ordem",
        default=0,
        help_text="Menor número = maior prioridade dentro do mesmo tipo.",
    )

    class Meta:
        ordering = ["zone_type", "sort_order", "name"]
        verbose_name = "zona de entrega"
        verbose_name_plural = "zonas de entrega"

    def __str__(self) -> str:
        fee_label = "grátis" if self.fee_q == 0 else f"R$ {self.fee_q / 100:.2f}"
        return f"{self.name} ({self.get_zone_type_display()}: {self.match_value}) — {fee_label}"

    @classmethod
    def match(cls, *, postal_code: str, neighborhood: str) -> DeliveryZone | None:
        """
        Retorna a zona ativa de maior prioridade que coincide com os dados do endereço.

        Prioridade:
          1. cep_prefix  (sort_order, depois name)
          2. neighborhood

        Retorna None se nenhuma zona coincide.
        """
        zones = cls.objects.filter(is_active=True).order_by("sort_order", "name")

        postal_digits = "".join(c for c in (postal_code or "") if c.isdigit())
        neighborhood_lower = (neighborhood or "").strip().lower()

        # 1. CEP prefix
        for zone in zones.filter(zone_type=cls.ZONE_TYPE_CEP_PREFIX):
            prefix = zone.match_value.strip()
            if postal_digits and postal_digits.startswith(prefix):
                return zone

        # 2. Neighborhood
        for zone in zones.filter(zone_type=cls.ZONE_TYPE_NEIGHBORHOOD):
            if neighborhood_lower and zone.match_value.strip().lower() == neighborhood_lower:
                return zone

        return None
