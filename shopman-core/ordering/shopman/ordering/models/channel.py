from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

# Keys recognised by the kernel. Anything else triggers a validation warning.
KNOWN_CONFIG_KEYS = frozenset({
    "preset",
    "icon",
    "required_checks_on_commit",
    "checks",
    "post_commit_directives",
    "order_flow",
    "notifications",
    "notification_routing",
    "terminology",
    "status_flow",
    "confirmation_flow",
    "stock",
    "payment",
    "opening_hours",
    "safety_margin",
})


class Channel(models.Model):
    """
    Canal de origem do pedido (PDV, e-commerce, iFood, etc.)

    Config convencionais (não interpretadas pelo Kernel):
    {
      "icon": "point_of_sale",
      "required_checks_on_commit": ["stock"],
      "terminology": {"order": "Comanda", "order_plural": "Comandas"},
      "status_flow": ["NEW", "IN_PROGRESS", "READY", "COMPLETED"]
    }
    """

    ref = models.CharField(_("código"), max_length=64, unique=True)
    name = models.CharField(_("nome"), max_length=128, blank=True, default="")

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
    config = models.JSONField(_("configuração"), default=dict, blank=True)
    is_active = models.BooleanField(_("ativo"), default=True)

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        app_label = "ordering"
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
