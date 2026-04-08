"""TimelineEvent model — unified interaction log per customer."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class EventType(models.TextChoices):
    """Timeline event types."""

    ORDER = "order", _("Pedido")
    CONTACT = "contact", _("Contato")
    NOTE = "note", _("Nota")
    VISIT = "visit", _("Visita")
    LOYALTY = "loyalty", _("Fidelidade")
    SYSTEM = "system", _("Sistema")


class TimelineEvent(models.Model):
    """
    Single interaction in a customer's timeline.

    Every meaningful touchpoint is recorded: orders, contacts, visits,
    internal notes, loyalty events, and system events. Provides a
    unified chronological view per customer.

    Used for:
        - CRM interaction history ("what happened with this customer?")
        - Context for customer service agents
        - AI-powered personalization via get_customer_context()
    """

    customer = models.ForeignKey(
        "guestman.Customer",
        on_delete=models.CASCADE,
        related_name="timeline_events",
        verbose_name=_("cliente"),
    )

    event_type = models.CharField(
        _("tipo"),
        max_length=20,
        choices=EventType.choices,
        db_index=True,
    )
    title = models.CharField(
        _("título"),
        max_length=200,
        help_text=_("Resumo curto do evento"),
    )
    description = models.TextField(
        _("descrição"),
        blank=True,
        help_text=_("Detalhes adicionais do evento"),
    )

    # Context
    channel = models.CharField(
        _("canal"),
        max_length=50,
        blank=True,
        help_text=_("Canal de origem (whatsapp, pdv, ecommerce, etc.)"),
    )
    reference = models.CharField(
        _("referência"),
        max_length=100,
        blank=True,
        help_text=_("ID externo (ex: order:123, ticket:456)"),
    )

    # Extension
    metadata = models.JSONField(
        _("metadados"),
        default=dict,
        blank=True,
        help_text=_("Dados extras do evento (JSON livre)"),
    )

    # Audit
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True, db_index=True)
    created_by = models.CharField(
        _("criado por"),
        max_length=100,
        blank=True,
        help_text=_("Usuário ou sistema que criou o evento"),
    )

    class Meta:
        verbose_name = _("evento da timeline")
        verbose_name_plural = _("eventos da timeline")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["customer", "event_type"]),
        ]

    def __str__(self):
        return f"[{self.event_type}] {self.title}"
