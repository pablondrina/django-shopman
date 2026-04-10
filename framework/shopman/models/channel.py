"""
Channel model — canal de venda (PDV, e-commerce, iFood, etc.)

Vive no framework ao lado de Shop. O `ref` conecta o canal a Listings,
ChannelConfig e qualquer recurso do framework por convenção de nomes.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class Channel(models.Model):
    """
    Canal de origem do pedido (PDV, e-commerce, iFood, etc.)

    O `ref` é o identificador agnóstico que conecta o canal a qualquer
    recurso do framework (ChannelConfig, Listing, etc.) por convenção de nomes.

    O `kind` descreve o tipo comportamental do canal — usado pelo framework
    para resolver a classe de Flow correspondente.

    O `config` armazena overrides de ChannelConfig para este canal.
    Cascata: canal.config ← shop.defaults ← defaults hardcoded.
    """

    ref = models.CharField(_("código"), max_length=64, unique=True)
    name = models.CharField(_("nome"), max_length=128, blank=True, default="")
    kind = models.CharField(
        _("tipo"),
        max_length=32,
        default="base",
        help_text=_(
            "Tipo comportamental do canal. Usado pelo framework para resolver "
            "a classe de Flow: base, local, pos, totem, remote, web, whatsapp, "
            "manychat, marketplace, ifood."
        ),
    )
    shop = models.ForeignKey(
        "shopman.Shop",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="channels",
        verbose_name=_("loja"),
    )
    config = models.JSONField(
        _("configuração"),
        default=dict,
        blank=True,
        help_text=_(
            "Override de ChannelConfig para este canal. "
            "Mesmo schema do ChannelConfig.to_dict(). "
            "Apenas as chaves presentes sobrescrevem os defaults da loja."
        ),
    )
    display_order = models.PositiveIntegerField(_("ordem de exibição"), default=0, db_index=True)
    is_active = models.BooleanField(_("ativo"), default=True)
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        app_label = "shopman"
        verbose_name = _("canal")
        verbose_name_plural = _("canais")
        ordering = ("display_order", "id")

    def __str__(self) -> str:
        return self.name or self.ref

    def get_config(self):
        """Retorna ChannelConfig resolvido para este canal.

        Cascata:
          1. Defaults hardcoded (ChannelConfig())
          2. Shop.defaults (nível loja)
          3. self.config (nível canal)
        """
        from shopman.config import ChannelConfig, deep_merge

        base = ChannelConfig.defaults()

        shop = self.shop
        if shop is None:
            from shopman.models.shop import Shop
            shop = Shop.load()

        if shop and shop.defaults:
            base = deep_merge(base, shop.defaults)

        if self.config:
            base = deep_merge(base, self.config)

        return ChannelConfig.from_dict(base)
