"""
ChannelConfigRecord — storage for per-channel ChannelConfig overrides.

Prefixo _ = detalhe de implementação interna do framework.
Não é um model de negócio; é o mecanismo de persistência do cascate
canal ← loja ← defaults do ChannelConfig.

Schema do JSONField `data`: mesmo schema do ChannelConfig.to_dict().
Chaves ausentes herdam do nível superior na cascata.
"""

from django.db import models


class ChannelConfigRecord(models.Model):
    """Storage interno para ChannelConfig canal-level.

    Detalhe de implementação do framework — não é um model de domínio público.
    Cada canal pode ter um registro aqui com overrides de config.
    A cascata é: canal (este model) ← loja (Shop.defaults) ← defaults hardcoded.
    """

    channel_ref = models.CharField(
        "ref do canal",
        max_length=64,
        unique=True,
        help_text="Ref do canal (deve corresponder a Channel.ref no Omniman).",
    )
    data = models.JSONField(
        "configuração",
        default=dict,
        blank=True,
        help_text=(
            "Override de ChannelConfig para este canal. "
            "Mesmo schema do ChannelConfig.to_dict(). "
            "Apenas as chaves presentes sobrescrevem os defaults da loja."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "shopman"
        verbose_name = "config de canal"
        verbose_name_plural = "configs de canais"
        ordering = ["channel_ref"]

    def __str__(self):
        return f"ChannelConfig:{self.channel_ref}"
