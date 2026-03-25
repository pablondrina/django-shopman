from __future__ import annotations

from django.core.cache import cache
from django.db import models

SHOP_CACHE_KEY = "shop_singleton"
SHOP_CACHE_TTL = 60  # seconds


class Shop(models.Model):
    """O estabelecimento. Singleton."""

    # ── Identidade ──
    name = models.CharField("nome fantasia", max_length=200)
    legal_name = models.CharField("razão social", max_length=200, blank=True)
    document = models.CharField("CNPJ/CPF", max_length=20, blank=True)

    # ── Localização ──
    address = models.TextField("endereço", blank=True)
    city = models.CharField("cidade", max_length=100, blank=True)
    state = models.CharField("UF", max_length=2, blank=True)
    postal_code = models.CharField("CEP", max_length=10, blank=True)
    phone = models.CharField("telefone", max_length=20, blank=True)
    default_ddd = models.CharField("DDD padrão", max_length=4, default="11")

    # ── Operação ──
    currency = models.CharField("moeda", max_length=3, default="BRL")
    timezone = models.CharField("fuso horário", max_length=50, default="America/Sao_Paulo")
    opening_hours = models.JSONField(
        "horários",
        default=dict,
        blank=True,
        help_text=(
            'Horários por dia da semana. Exemplo: '
            '{"monday": {"open": "06:00", "close": "20:00"}, '
            '"tuesday": {"open": "06:00", "close": "20:00"}, ...}. '
            'Dias: monday, tuesday, wednesday, thursday, friday, saturday, sunday.'
        ),
    )

    # ── Branding ──
    brand_name = models.CharField("marca", max_length=100, blank=True)
    short_name = models.CharField("nome curto (PWA)", max_length=30, blank=True)
    tagline = models.CharField("tagline", max_length=200, blank=True)
    description = models.TextField("descrição", blank=True)
    primary_color = models.CharField("cor primária", max_length=7, default="#9E833E")
    background_color = models.CharField("cor de fundo", max_length=7, default="#F5F0EB")
    logo_url = models.URLField("logo", max_length=500, blank=True)

    # ── Redes e contatos ──
    website = models.URLField("site", blank=True)
    instagram = models.CharField("Instagram", max_length=100, blank=True)
    whatsapp = models.CharField("WhatsApp", max_length=20, blank=True)

    # ── Defaults de negócio (cascata: canal ← AQUI ← hardcoded) ──
    defaults = models.JSONField(
        "configurações padrão",
        default=dict,
        blank=True,
        help_text="Mesmo schema do ChannelConfig. Canais herdam se não sobreescreverem.",
    )

    class Meta:
        verbose_name = "loja"
        verbose_name_plural = "loja"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(SHOP_CACHE_KEY)

    @classmethod
    def load(cls) -> Shop | None:
        shop = cache.get(SHOP_CACHE_KEY)
        if shop is None:
            shop = cls.objects.first()
            if shop is not None:
                cache.set(SHOP_CACHE_KEY, shop, SHOP_CACHE_TTL)
        return shop

    # ── Propriedades de compatibilidade (usadas nos templates) ──

    @property
    def theme_color(self) -> str:
        return self.primary_color

    @property
    def default_city(self) -> str:
        return self.city

    @property
    def location(self) -> str:
        if self.city and self.state:
            return f"{self.city} — {self.state}"
        return self.city or self.state or ""

    @property
    def whatsapp_number(self) -> str:
        return self.whatsapp

    @property
    def whatsapp_url(self) -> str:
        return f"https://wa.me/{self.whatsapp}" if self.whatsapp else "#"

    @property
    def description_html(self) -> str:
        return self.description.replace("\n", "<br>")


# ── Promotion & Coupon ──


class Promotion(models.Model):
    """Promoção automática — aplica desconto a itens que atendem os critérios."""

    PERCENT = "percent"
    FIXED = "fixed"
    TYPE_CHOICES = [(PERCENT, "Percentual"), (FIXED, "Valor fixo")]

    name = models.CharField("nome", max_length=200)
    type = models.CharField("tipo", max_length=10, choices=TYPE_CHOICES)
    value = models.IntegerField(
        "valor",
        help_text="Percentual (0-100) ou valor fixo em centavos",
    )
    valid_from = models.DateTimeField("válido de")
    valid_until = models.DateTimeField("válido até")
    skus = models.JSONField(
        "SKUs",
        default=list,
        blank=True,
        help_text='SKUs afetados (vazio = todos). Ex: ["PAO-FRANCES", "CROISSANT"]',
    )
    collections = models.JSONField(
        "coleções",
        default=list,
        blank=True,
        help_text='Collection refs afetados (vazio = todos). Ex: ["paes-artesanais", "confeitaria"]',
    )
    min_order_q = models.IntegerField(
        "pedido mínimo (centavos)",
        default=0,
        help_text="Valor mínimo do pedido em centavos (0 = sem mínimo)",
    )
    is_active = models.BooleanField("ativa", default=True)

    class Meta:
        verbose_name = "promoção"
        verbose_name_plural = "promoções"
        ordering = ["-valid_from"]

    def __str__(self):
        return self.name


class Coupon(models.Model):
    """Cupom — código que ativa uma promoção."""

    code = models.CharField("código", max_length=50, unique=True, db_index=True)
    promotion = models.ForeignKey(
        Promotion,
        on_delete=models.CASCADE,
        related_name="coupons",
        verbose_name="promoção",
    )
    max_uses = models.PositiveIntegerField(
        "usos máximos",
        default=0,
        help_text="0 = ilimitado",
    )
    uses_count = models.PositiveIntegerField("usos realizados", default=0)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "cupom"
        verbose_name_plural = "cupons"

    def __str__(self):
        return self.code

    @property
    def is_available(self) -> bool:
        return self.is_active and (self.max_uses == 0 or self.uses_count < self.max_uses)
