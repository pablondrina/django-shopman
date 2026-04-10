"""
Models para contrib/refs.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class Ref(models.Model):
    """
    Localizador/etiqueta associada a uma Session ou Order.

    Refs permitem associar identificadores externos (mesa, comanda, senha,
    número do pedido, IDs de integrações) aos objetos internos do sistema.

    A unicidade e lifecycle são controlados pelo RefType correspondente.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ref_type = models.CharField(
        max_length=32,
        db_index=True,
        verbose_name=_("tipo de referência"),
        help_text="Slug do RefType (ex: POS_TABLE, ORDER_NUMBER)",
    )

    target_kind = models.CharField(
        max_length=8,
        choices=[("SESSION", "Session"), ("ORDER", "Order")],
        verbose_name=_("tipo de alvo"),
        help_text="Tipo do target associado",
    )

    target_id = models.UUIDField(
        db_index=True,
        verbose_name=_("ID do alvo"),
        help_text="ID do target (Session.id ou Order.id)",
    )

    value = models.CharField(
        max_length=64,
        db_index=True,
        verbose_name=_("valor"),
        help_text="Valor normalizado do localizador (ex: '12', '001', 'ABC123')",
    )

    scope = models.JSONField(
        default=dict,
        verbose_name=_("escopo"),
        help_text="Scope de unicidade (ex: {store_id: 1, business_date: '2025-12-19'})",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("ativo"),
        help_text="Se False, Ref está desativada (não resolve)",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("criado em"))

    class Meta:
        app_label = "refs"
        verbose_name = _("Referência")
        verbose_name_plural = _("Referências")
        indexes = [
            models.Index(
                fields=["ref_type", "value", "is_active"],
                name="ref_type_value_active_idx",
            ),
            models.Index(
                fields=["target_kind", "target_id", "is_active"],
                name="ref_target_active_idx",
            ),
        ]

    def __str__(self):
        status = "active" if self.is_active else "inactive"
        return f"{self.ref_type}:{self.value} -> {self.target_kind}:{self.target_id} ({status})"

    def deactivate(self) -> None:
        """Desativa esta Ref."""
        if self.is_active:
            self.is_active = False
            self.save(update_fields=["is_active"])


class RefSequence(models.Model):
    """
    Controle de sequências para geração automática de valores.

    Usado por RefTypes que precisam de valores sequenciais (ex: senhas, tickets).
    Cada combinação (sequence_name, scope_hash) tem seu próprio contador.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    sequence_name = models.CharField(
        max_length=32,
        db_index=True,
        verbose_name=_("nome da sequência"),
        help_text="Nome da sequência (geralmente o RefType.slug)",
    )

    scope_hash = models.CharField(
        max_length=64,
        db_index=True,
        verbose_name=_("hash do escopo"),
        help_text="Hash do scope para particionamento",
    )

    scope = models.JSONField(
        default=dict,
        verbose_name=_("escopo"),
        help_text="Scope original (para debug/auditoria)",
    )

    last_value = models.PositiveIntegerField(
        default=0,
        verbose_name=_("último valor"),
        help_text="Último valor gerado nesta sequência",
    )

    class Meta:
        app_label = "refs"
        verbose_name = _("Sequência de Referência")
        verbose_name_plural = _("Sequências de Referência")
        constraints = [
            models.UniqueConstraint(
                fields=["sequence_name", "scope_hash"],
                name="unique_sequence_scope",
            ),
        ]

    def __str__(self):
        return f"{self.sequence_name}:{self.scope_hash} = {self.last_value}"
