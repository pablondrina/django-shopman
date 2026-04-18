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
        verbose_name = "instância KDS"
        verbose_name_plural = "instâncias KDS"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class KDSTicket(models.Model):
    """Ticket despachado para uma estação KDS com items de um pedido."""

    STATUS_CHOICES = [
        ("pending", "Pendente"),
        ("in_progress", "Em andamento"),
        ("done", "Concluído"),
    ]

    order = models.ForeignKey(
        "orderman.Order",
        on_delete=models.CASCADE,
        related_name="kds_tickets",
        verbose_name="pedido",
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

    class Meta:
        verbose_name = "ticket KDS"
        verbose_name_plural = "tickets KDS"
        ordering = ["created_at"]
        permissions = [("operate_kds", "Pode operar telas KDS (check, done, expedition)")]

    def __str__(self):
        return f"KDS #{self.pk} — {self.order.ref} → {self.kds_instance.ref}"
