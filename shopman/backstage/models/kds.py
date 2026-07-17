"""KDS (Kitchen Display System) models."""

from __future__ import annotations

from django.db import models


class KDSInstance(models.Model):
    """Estação KDS: Prep (preparo), Picking (separação) ou Expedition (despacho)."""

    TYPE_CHOICES = [
        ("prep", "Preparo"),
        ("picking", "Separação"),
        ("expedition", "Expedição"),
    ]

    ref = models.SlugField("ref", max_length=50, unique=True)
    name = models.CharField("nome", max_length=200)
    type = models.CharField("tipo", max_length=20, choices=TYPE_CHOICES)
    collections = models.ManyToManyField(
        "offerman.Collection",
        blank=True,
        verbose_name="coleções",
        help_text="Categorias de produto que esta estação processa. Vazio = catch-all.",
    )
    target_time_minutes = models.PositiveIntegerField(
        "tempo alvo (min)", default=10,
        help_text="Timer fica amarelo após este tempo, vermelho após 2x.",
    )
    sound_enabled = models.BooleanField("som ativo", default=True)
    is_active = models.BooleanField("ativa", default=True)
    config = models.JSONField(
        "configurações", default=dict, blank=True,
        help_text="text_size, dark_mode, refresh_interval, etc.",
    )

    class Meta:
        verbose_name = "estação KDS"
        verbose_name_plural = "estações KDS"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class KDSTicket(models.Model):
    """Ticket despachado para uma estação KDS com items de uma venda.

    Ancora em ``session_key`` (ref textual estável, não FK). A mesma chave
    resolve para a Session aberta (comanda em andamento) antes do commit e
    para o Order selado depois — ``Order.session_key`` é copiado verbatim no
    commit. Isso unifica o KDS para qualquer canal e permite disparo
    progressivo (prato-a-prato) a partir da comanda, sem re-apontar tickets.
    """

    STATUS_CHOICES = [
        ("pending", "Pendente"),
        ("in_progress", "Em andamento"),
        ("done", "Concluído"),
        ("cancelled", "Cancelado"),
    ]

    session_key = models.CharField(
        "chave da venda", max_length=64, db_index=True,
        help_text="Resolve para a Session aberta (comanda) ou o Order selado.",
    )
    kds_instance = models.ForeignKey(
        KDSInstance,
        on_delete=models.CASCADE,
        related_name="tickets",
        verbose_name="estação KDS",
    )
    items = models.JSONField(
        "items", default=list,
        help_text='[{"sku", "name", "qty", "notes", "checked": false}]',
    )
    status = models.CharField(
        "status", max_length=20, choices=STATUS_CHOICES, default="pending",
    )
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    completed_at = models.DateTimeField("concluído em", null=True, blank=True)
    cancelled_at = models.DateTimeField("cancelado em", null=True, blank=True)
    acknowledged_at = models.DateTimeField(
        "ciente em", null=True, blank=True,
        help_text="Operador deu baixa no card cancelado — sai do board.",
    )

    class Meta:
        verbose_name = "ticket KDS"
        verbose_name_plural = "tickets KDS"
        ordering = ["created_at"]
        permissions = [("operate_kds", "Pode operar telas KDS (check, done, expedition)")]

    def __str__(self):
        return f"KDS #{self.pk} — {self.session_key} → {self.kds_instance.ref}"
