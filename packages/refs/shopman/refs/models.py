"""
Ref and RefSequence models.

Ref     — persistent link between a (ref_type, value) pair and any system entity.
RefSequence — monotonic counter per (sequence_name, scope_hash) for auto-generation.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class Ref(models.Model):
    """
    A named locator attached to a system entity.

    A Ref resolves the question: "given this type+value+scope, which entity does it name?"
    It is the DNS of the domain — links without coupling.

    target_type uses "{app_label}.{ModelName}" format (e.g. "orderman.Session"),
    mirroring Django's ContentType convention but WITHOUT a GenericForeignKey dependency.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # What
    ref_type = models.CharField(max_length=32, db_index=True, verbose_name=_("tipo"))
    value = models.CharField(max_length=128, db_index=True, verbose_name=_("valor"))

    # To whom (generic, no contenttypes dependency)
    target_type = models.CharField(
        max_length=64,
        verbose_name=_("tipo do alvo"),
        help_text='"{app_label}.{ModelName}" — ex: "orderman.Session"',
    )
    target_id = models.CharField(max_length=64, verbose_name=_("ID do alvo"))

    # Where (uniqueness scope)
    scope = models.JSONField(default=dict, blank=True, verbose_name=_("escopo"))

    # State
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("ativo"))

    # Audit
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("criado em"))
    actor = models.CharField(
        max_length=128, blank=True, verbose_name=_("ator"),
        help_text='"system", "user:42", "lifecycle:commit"',
    )
    deactivated_at = models.DateTimeField(null=True, blank=True, verbose_name=_("desativado em"))
    deactivated_by = models.CharField(max_length=128, blank=True, verbose_name=_("desativado por"))

    # Extensible
    metadata = models.JSONField(default=dict, blank=True, verbose_name=_("metadados"))

    class Meta:
        app_label = "refs"
        verbose_name = _("Referencia")
        verbose_name_plural = _("Referencias")
        indexes = [
            models.Index(fields=["ref_type", "value", "is_active"], name="ref_type_val_active_idx"),
            models.Index(fields=["target_type", "target_id", "is_active"], name="ref_target_active_idx"),
        ]

    def __str__(self) -> str:
        status = "active" if self.is_active else "inactive"
        return f"{self.ref_type}:{self.value} -> {self.target_type}:{self.target_id} ({status})"


class RefSequence(models.Model):
    """
    Monotonic counter per (sequence_name, scope_hash).

    Provides a locked, per-scope integer sequence for auto-value generators.
    Always accessed with select_for_update() to prevent races.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    sequence_name = models.CharField(max_length=32, db_index=True, verbose_name=_("nome da sequencia"))
    scope_hash = models.CharField(max_length=64, db_index=True, verbose_name=_("hash do escopo"))
    scope = models.JSONField(default=dict, verbose_name=_("escopo"))
    last_value = models.PositiveIntegerField(default=0, verbose_name=_("ultimo valor"))

    class Meta:
        app_label = "refs"
        verbose_name = _("Sequencia de Referencia")
        verbose_name_plural = _("Sequencias de Referencia")
        constraints = [
            models.UniqueConstraint(
                fields=["sequence_name", "scope_hash"],
                name="refs_unique_sequence_scope",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sequence_name}:{self.scope_hash} = {self.last_value}"
