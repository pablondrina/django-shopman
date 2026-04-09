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

    pricing_policy = models.CharField(
        _("política de preço"),
        max_length=16,
        choices=[("internal", _("interna")), ("external", _("externa"))],
        default="internal",
    )
    edit_policy = models.CharField(
        _("política de edição"),
        max_length=16,
        choices=[("open", _("aberta")), ("locked", _("bloqueada"))],
        default="open",
    )

    display_order = models.PositiveIntegerField(_("ordem de exibição"), default=0, db_index=True)
    is_active = models.BooleanField(_("ativo"), default=True)

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        app_label = "omniman"
        verbose_name = _("canal")
        verbose_name_plural = _("canais")
        ordering = ("display_order", "id")

    def __str__(self) -> str:
        return self.name or self.ref
