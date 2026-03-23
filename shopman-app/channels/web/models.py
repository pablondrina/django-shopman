from __future__ import annotations

from django.core.cache import cache
from django.db import models


STOREFRONT_CONFIG_CACHE_KEY = "storefront_config"
STOREFRONT_CONFIG_CACHE_TTL = 60  # seconds


class StorefrontConfig(models.Model):
    brand_name = models.CharField(max_length=100, default="Nelson Boulangerie", verbose_name="Nome da marca")
    short_name = models.CharField(max_length=30, default="Nelson", verbose_name="Nome curto")
    tagline = models.CharField(max_length=200, blank=True, default="Padaria Artesanal", verbose_name="Tagline")
    description = models.TextField(
        blank=True,
        default="Padaria artesanal premium.\nFermentação natural, tradição francesa e japonesa.",
        verbose_name="Descrição",
    )
    theme_color = models.CharField(max_length=7, default="#C5A55A", verbose_name="Cor principal")
    background_color = models.CharField(max_length=7, default="#F5F0EB", verbose_name="Cor de fundo")
    default_ddd = models.CharField(max_length=3, default="43", verbose_name="DDD padrão")
    default_city = models.CharField(max_length=100, default="Londrina", verbose_name="Cidade padrão")
    location = models.CharField(max_length=200, blank=True, default="Londrina — PR", verbose_name="Localização")
    whatsapp_number = models.CharField(max_length=20, blank=True, default="5543999999999", verbose_name="WhatsApp")

    class Meta:
        verbose_name = "Configuração do Storefront"
        verbose_name_plural = "Configuração do Storefront"

    def __str__(self):
        return self.brand_name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(STOREFRONT_CONFIG_CACHE_KEY)

    @classmethod
    def load(cls) -> StorefrontConfig:
        config = cache.get(STOREFRONT_CONFIG_CACHE_KEY)
        if config is None:
            config = cls.objects.first()
            if config is None:
                config = cls()
            cache.set(STOREFRONT_CONFIG_CACHE_KEY, config, STOREFRONT_CONFIG_CACHE_TTL)
        return config

    @property
    def whatsapp_url(self) -> str:
        return f"https://wa.me/{self.whatsapp_number}" if self.whatsapp_number else "#"

    @property
    def description_html(self) -> str:
        return self.description.replace("\n", "<br>")
