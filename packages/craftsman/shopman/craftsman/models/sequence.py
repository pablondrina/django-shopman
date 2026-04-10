"""
Ref sequence for atomic WorkOrder ref generation.

Replaces the fragile SELECT MAX(ref) + retry approach with
an atomic counter using SELECT FOR UPDATE.
"""

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _


class RefSequence(models.Model):
    """
    Atomic counter for generating sequential refs.

    One row per (prefix), e.g. "WO-2026" → last_value = 42.
    Thread-safe via SELECT FOR UPDATE.

    Usage (internal to WorkOrder.save):
        seq_val = RefSequence.next_value("WO-2026")
        # Returns 1, 2, 3... atomically
    """

    prefix = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("Prefixo"),
    )
    last_value = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Último valor"),
    )

    class Meta:
        db_table = "crafting_code_sequence"
        verbose_name = _("Sequência de Referência")
        verbose_name_plural = _("Sequências de Referência")

    def __str__(self) -> str:
        return f"{self.prefix} → {self.last_value}"

    @classmethod
    def next_value(cls, prefix: str) -> int:
        """
        Atomically increment and return the next value for a prefix.

        Thread-safe: uses SELECT FOR UPDATE to prevent race conditions.
        """
        with transaction.atomic():
            seq, created = cls.objects.select_for_update().get_or_create(
                prefix=prefix, defaults={"last_value": 0}
            )
            seq.last_value += 1
            seq.save(update_fields=["last_value"])
            return seq.last_value
