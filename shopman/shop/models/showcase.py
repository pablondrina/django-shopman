"""
Showcase (UI: "Expositor") — exibe um conjunto de coleções PARA FORA, sem transacionar.

Separa a exibição/feed da venda: um Canal (Channel) é ponto de venda transacional;
um Expositor apenas MOSTRA um recorte curado do catálogo num alvo de exibição —
📺 menuboard (TV na loja) ou 🛰 feed (Google/Meta). Compõe N ``Collection`` (por ref),
que viram as SEÇÕES do menuboard e os segmentos/``custom_label`` do feed. Não polui o
espaço transacional (não aparece em pedido/POS/regra) e reusa as coleções reais em vez
de exigir uma coleção-guarda-chuva.

Acoplamento frouxo por ref (como Listing↔Channel): ``collections`` é uma lista de refs
de coleção, resolvida em tempo de leitura (ordem de exibição = ``Collection.sort_order``).
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class Showcase(models.Model):
    KIND_MENUBOARD = "menuboard"
    KIND_GOOGLE = "google"
    KIND_META = "meta"
    KIND_CHOICES = [
        (KIND_MENUBOARD, _("📺 Menuboard (TV na loja)")),
        (KIND_GOOGLE, _("🛰 Feed Google")),
        (KIND_META, _("🛰 Feed Meta")),
    ]

    ref = models.SlugField(_("referência"), max_length=64, unique=True)
    name = models.CharField(_("nome"), max_length=128)
    kind = models.CharField(_("tipo"), max_length=20, choices=KIND_CHOICES, default=KIND_MENUBOARD)
    # Refs das coleções que compõem o expositor (seções/segmentos). Ordem de exibição
    # = sort_order de cada coleção. Vazio = nada a mostrar.
    collections = models.JSONField(_("coleções"), default=list, blank=True)
    is_active = models.BooleanField(_("ativo"), default=True)
    # Opções por tipo (layout do menuboard, rótulos do feed, etc.) — extensível sem migração.
    options = models.JSONField(_("opções"), default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "shop"
        verbose_name = _("expositor")
        verbose_name_plural = _("expositores")
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name or self.ref

    @property
    def is_feed(self) -> bool:
        return self.kind in (self.KIND_GOOGLE, self.KIND_META)

    def collection_refs(self) -> list[str]:
        """Lista limpa de refs de coleção (ignora entradas vazias)."""
        return [str(r).strip() for r in (self.collections or []) if str(r).strip()]
