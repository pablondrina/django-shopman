from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

# Keys recognised by ChannelConfig (7 aspects). Anything else triggers a validation warning.
KNOWN_CONFIG_KEYS = frozenset({
    "confirmation",
    "payment",
    "stock",
    "pipeline",
    "notifications",
    "rules",
    "flow",
})


class Channel(models.Model):
    """
    Canal de origem do pedido (PDV, e-commerce, iFood, etc.)

    Config segue o schema do ChannelConfig dataclass (7 aspectos):
    confirmation, payment, stock, pipeline, notifications, rules, flow.
    Use presets: pos(), remote(), marketplace() para templates comuns.
    """

    ref = models.CharField(_("código"), max_length=64, unique=True)
    name = models.CharField(_("nome"), max_length=128, blank=True, default="")
    listing_ref = models.CharField(
        _("listagem"),
        max_length=50,
        blank=True,
        default="",
        help_text=_("Ref da Listing que serve como catálogo deste canal"),
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
    config = models.JSONField(
        _("configuração"),
        default=dict,
        blank=True,
        help_text=_(
            "ChannelConfig schema (7 aspectos). Chaves: "
            "confirmation {mode, timeout_minutes}, "
            "payment {method, timeout_minutes}, "
            "stock {hold_ttl_minutes, safety_margin, planned_hold_ttl_hours}, "
            "pipeline {on_commit, on_confirmed, on_cancelled, ...} (listas de topics), "
            "notifications {backend, fallback, routing}, "
            "rules {validators, modifiers, checks}, "
            "flow {transitions, terminal_statuses, auto_transitions, auto_sync_fulfillment}. "
            "Use presets: pos(), remote(), marketplace()."
        ),
    )
    is_active = models.BooleanField(_("ativo"), default=True)

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        app_label = "omniman"
        verbose_name = _("canal")
        verbose_name_plural = _("canais")
        ordering = ("display_order", "id")

    def __str__(self) -> str:
        return self.name or self.ref

    def clean(self):
        super().clean()
        if self.config:
            from django.core.exceptions import ValidationError

            unknown = set(self.config.keys()) - KNOWN_CONFIG_KEYS
            if unknown:
                raise ValidationError(
                    {
                        "config": (
                            f"Keys desconhecidas: {', '.join(sorted(unknown))}. "
                            f"Keys válidas: {', '.join(sorted(KNOWN_CONFIG_KEYS))}. "
                            f"Se são intencionais, ignore este aviso."
                        ),
                    },
                )
