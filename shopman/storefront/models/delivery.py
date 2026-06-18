"""Entrega configurável — faixa de distância (motor) + zona CEP/bairro (exceção)."""

from __future__ import annotations

from django.db import models


class DeliveryZone(models.Model):
    """
    Zona de entrega por CEP/bairro — a camada de EXCEÇÃO da precificação.

    A taxa primária vem da faixa de distância (`DeliveryDistanceBand`); a zona é a
    exceção que o raio não captura, em dois modos (`mode`):

    - ``override`` — taxa FIXA para este CEP/bairro, sobrepõe a faixa de distância
      (ex.: um bairro com frete grátis ou tabelado).
    - ``exclude`` — NÃO entregamos aqui; bloqueia o checkout (`delivery_zone_error`),
      independente da distância.

    Pertence a uma Shop (singleton). Gerenciada como inline no ShopAdmin.

    Matching order (prioridade):
      1. cep_prefix  — prefixo do CEP (ex: "860" cobre 860xx-xxx)
      2. neighborhood — bairro exato (case-insensitive)

    fee_q == 0 → entrega grátis (só relevante no modo ``override``).
    """

    ZONE_TYPE_CEP_PREFIX = "cep_prefix"
    ZONE_TYPE_NEIGHBORHOOD = "neighborhood"

    ZONE_TYPE_CHOICES = [
        (ZONE_TYPE_CEP_PREFIX, "Prefixo de CEP"),
        (ZONE_TYPE_NEIGHBORHOOD, "Bairro"),
    ]

    MODE_OVERRIDE = "override"
    MODE_EXCLUDE = "exclude"

    MODE_CHOICES = [
        (MODE_OVERRIDE, "Sobrepor taxa (fixa)"),
        (MODE_EXCLUDE, "Não entregar (bloquear)"),
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
    mode = models.CharField(
        "modo",
        max_length=20,
        choices=MODE_CHOICES,
        default=MODE_OVERRIDE,
        help_text=(
            "'Sobrepor taxa': usa a taxa fixa abaixo no lugar da faixa de distância. "
            "'Não entregar': bloqueia o checkout para este CEP/bairro."
        ),
    )
    fee_q = models.PositiveIntegerField(
        "taxa de entrega (centavos)",
        default=0,
        help_text="Taxa em centavos no modo 'Sobrepor taxa'. 0 = entrega grátis.",
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


class DeliveryDistanceBand(models.Model):
    """
    Faixa de distância — o MOTOR de precificação da entrega.

    A taxa sai da distância geográfica loja→endereço (haversine sobre
    ``Shop.latitude/longitude`` × lat/lng do endereço). Cada faixa cobre até
    ``max_distance_km`` (limite superior inclusivo); a menor faixa cujo limite
    alcança a distância vence. Distância além de todas as faixas ativas → fora da
    área de entrega (``delivery_zone_error``).

    A ``DeliveryZone`` (CEP/bairro) é a camada de exceção que sobrepõe/exclui.
    fee_q == 0 → entrega grátis nessa faixa.
    """

    shop = models.ForeignKey(
        "shop.Shop",
        on_delete=models.CASCADE,
        related_name="delivery_distance_bands",
        verbose_name="loja",
    )
    max_distance_km = models.DecimalField(
        "distância máxima (km)",
        max_digits=6,
        decimal_places=2,
        help_text="Limite superior inclusivo da faixa, em km (ex.: 3.00 cobre até 3 km).",
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
        help_text="Desempate entre faixas com o mesmo limite. Menor = maior prioridade.",
    )

    class Meta:
        ordering = ["max_distance_km", "sort_order"]
        verbose_name = "faixa de distância de entrega"
        verbose_name_plural = "faixas de distância de entrega"

    def __str__(self) -> str:
        fee_label = "grátis" if self.fee_q == 0 else f"R$ {self.fee_q / 100:.2f}"
        return f"até {self.max_distance_km} km — {fee_label}"

    @classmethod
    def match(cls, distance_km: float) -> DeliveryDistanceBand | None:
        """Menor faixa ativa cujo limite superior alcança ``distance_km``, ou None."""
        for band in cls.objects.filter(is_active=True).order_by("max_distance_km", "sort_order"):
            if distance_km <= float(band.max_distance_km):
                return band
        return None
