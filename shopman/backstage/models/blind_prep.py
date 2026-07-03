"""BlindPrepCode — código diário de pesagem cega por preparo.

O colaborador pesa com etiquetas que carregam SÓ o código do dia (1 letra +
1 número, sem 0/1/O/I — ultra legível e memorizável); o mapa código↔preparo é
visão de gestor. A linha persiste a alocação do dia — o código não muda se um
preparo novo entrar no meio da manhã (reimpressão sempre bate). A constraint
garante o dia; a alocação (``blind_prep_code``) amplia a unicidade para a
janela de expediente (dia útil anterior · dia · próximo dia útil), para que
etiquetas de dias adjacentes convivendo na cozinha nunca se confundam.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class BlindPrepCode(models.Model):
    date = models.DateField(_("data"), db_index=True)
    recipe_ref = models.SlugField(_("preparo"), max_length=100)
    code = models.CharField(_("código"), max_length=2)

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        app_label = "backstage"
        verbose_name = _("código de pesagem cega")
        verbose_name_plural = _("códigos de pesagem cega")
        constraints = [
            models.UniqueConstraint(fields=["date", "recipe_ref"], name="blindprep_date_recipe_uq"),
            models.UniqueConstraint(fields=["date", "code"], name="blindprep_date_code_uq"),
        ]

    def __str__(self) -> str:
        return f"{self.code} → {self.recipe_ref} ({self.date})"
