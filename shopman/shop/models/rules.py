"""RuleConfig model — configurable rules via admin."""

from __future__ import annotations

import importlib
import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

logger = logging.getLogger(__name__)


def _allowed_prefixes() -> list[str]:
    return getattr(
        settings,
        "SHOPMAN_RULES_ALLOWED_MODULE_PREFIXES",
        ["shopman.shop.rules.", "shopman.shop.modifiers."],
    )


class RuleConfig(models.Model):
    """Regra configurável via admin — pricing, validation, etc."""

    code = models.CharField("código", max_length=80, unique=True)
    rule_path = models.CharField(
        "caminho da regra", max_length=200,
        help_text="Dotted path to the rule class (e.g. shopman.shop.rules.pricing.D1Rule)",
    )
    label = models.CharField("nome exibido", max_length=120)
    enabled = models.BooleanField("ativa", default=True)
    params = models.JSONField(
        "parâmetros", default=dict, blank=True,
        help_text="Parâmetros da regra (ex: percentual, horários, SKUs)",
    )
    channels = models.ManyToManyField(
        "shop.Channel", blank=True,
        verbose_name="canais",
        help_text="Canais onde esta regra se aplica. Vazio = todos.",
    )
    priority = models.IntegerField(
        "prioridade", default=0,
        help_text="Regras com menor número são avaliadas primeiro",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["priority"]
        verbose_name = "regra configurável"
        verbose_name_plural = "regras configuráveis"
        permissions = [
            ("manage_rules", "Pode gerenciar regras de pricing e validação"),
        ]

    def __str__(self):
        status = "✓" if self.enabled else "✗"
        return f"[{status}] {self.label}"

    def clean(self):
        from shopman.shop.rules import BaseRule

        prefixes = _allowed_prefixes()
        if not any(self.rule_path.startswith(p) for p in prefixes):
            raise ValidationError({
                "rule_path": (
                    "Este caminho de regra não é permitido. "
                    "Use apenas classes dos módulos autorizados."
                ),
            })

        try:
            module_path, class_name = self.rule_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
        except (ImportError, AttributeError, ValueError) as exc:
            raise ValidationError({
                "rule_path": f"Não foi possível importar esta classe: {exc}",
            }) from exc

        if not (isinstance(cls, type) and issubclass(cls, BaseRule)):
            raise ValidationError({
                "rule_path": (
                    f"A classe '{self.rule_path.rsplit('.', 1)[-1]}' "
                    "não herda de BaseRule."
                ),
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        is_new = self.pk is None
        old_path = None
        if not is_new:
            try:
                old_path = RuleConfig.objects.values_list("rule_path", flat=True).get(pk=self.pk)
            except RuleConfig.DoesNotExist:
                pass
        super().save(*args, **kwargs)
        logger.warning(
            "rule_config.changed",
            extra={
                "event": "created" if is_new else "updated",
                "rule_code": self.code,
                "old_path": old_path,
                "new_path": self.rule_path,
                "user_id": None,  # tracked in HistoricalRuleConfig via HistoryRequestMiddleware
            },
        )

    def delete(self, *args, **kwargs):
        logger.warning(
            "rule_config.changed",
            extra={
                "event": "deleted",
                "rule_code": self.code,
                "old_path": self.rule_path,
                "new_path": None,
                "user_id": None,
            },
        )
        super().delete(*args, **kwargs)
