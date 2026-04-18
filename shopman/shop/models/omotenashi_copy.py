"""OmotenashiCopy — admin-editable overrides for interface copy.

Code-level defaults live in `shopman.shop.omotenashi.copy.OMOTENASHI_DEFAULTS`.
This model lets operators customise any entry without a code change. The
resolver in that module falls back to the code default whenever a row is
missing or inactive, so the app is never broken by an empty table.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


class OmotenashiCopy(models.Model):
    key = models.CharField(
        "chave",
        max_length=64,
        db_index=True,
        help_text="Identificador da cópia (ex: CART_EMPTY, PAYMENT_CONFIRMED).",
    )
    moment = models.CharField(
        "momento",
        max_length=16,
        default="*",
        help_text='Momento do dia ("manha", "almoco", "tarde", "fechando", "fechado", "madrugada") ou "*" para qualquer.',
    )
    audience = models.CharField(
        "público",
        max_length=16,
        default="*",
        help_text='Perfil da pessoa ("anon", "new", "returning", "vip") ou "*" para qualquer.',
    )
    title = models.CharField("título", max_length=120, blank=True)
    message = models.TextField("mensagem", blank=True)
    active = models.BooleanField("ativa", default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cópia omotenashi"
        verbose_name_plural = "cópias omotenashi"
        ordering = ("key", "moment", "audience")
        constraints = [
            models.UniqueConstraint(
                fields=("key", "moment", "audience"),
                name="uniq_omotenashi_copy_triplet",
            ),
        ]
        indexes = [models.Index(fields=("key", "active"))]

    def __str__(self) -> str:
        return f"{self.key} [{self.moment}/{self.audience}]"

    def clean(self) -> None:
        # An active override must actually override something. Desactivate the row
        # (or delete it) if you want the code default to take over.
        if self.active and not (self.title or self.message):
            raise ValidationError(
                "Uma cópia ativa precisa de título ou mensagem. "
                "Para voltar ao padrão do código, desative esta linha."
            )


# ── Cache invalidation ─────────────────────────────────────────────────
#
# The resolver caches DB rows in-process. We invalidate on every write so
# admin edits take effect immediately — no need to restart the process.


@receiver(post_save, sender=OmotenashiCopy)
@receiver(post_delete, sender=OmotenashiCopy)
def _invalidate_copy_cache(sender, **kwargs):
    from shopman.shop.omotenashi.copy import invalidate_cache
    invalidate_cache()
