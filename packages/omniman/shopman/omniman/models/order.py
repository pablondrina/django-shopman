from __future__ import annotations

from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .session import DecimalEncoder


class Order(models.Model):
    """
    Pedido canônico (selado, imutável).

    Status Canônicos:
    - new: Pedido criado pelo sistema. Em modo immediate: estado de microssegundos antes de confirmar.
           Em modo optimistic/pessimistic: aguarda operador confirmar ou timeout.
    - confirmed: Confirmado pelo operador ou auto-confirmado. Pagamento iniciado se digital.
    - preparing: Pedido em montagem na cozinha. KDS tickets ativos. NÃO é produção em lote
                 (WorkOrder). WorkOrders são produção antecipada; este estado = itens sendo
                 montados para este pedido específico.
    - ready: Pronto. Pickup: aguardando retirada no balcão. Delivery: aguardando motoboy.
    - dispatched: Em trânsito (exclusivo para delivery). Jamais alcançável por pedidos de retirada.
    - delivered: Entregue ao destinatário (delivery). Aguarda fechamento fiscal/loyalty.
    - completed: Finalizado. Fiscal emitido, loyalty acumulado. Status interno — cliente não
                 distingue de delivered.
    - cancelled: Cancelado. Terminal.
    - returned: Devolvido pós-entrega. Stock revertido, reembolso efetuado. Terminal.
    """

    class Status(models.TextChoices):
        NEW = "new", _("novo")
        CONFIRMED = "confirmed", _("confirmado")
        PREPARING = "preparing", _("em preparo")
        READY = "ready", _("pronto")
        DISPATCHED = "dispatched", _("despachado")
        DELIVERED = "delivered", _("entregue")
        COMPLETED = "completed", _("concluído")
        CANCELLED = "cancelled", _("cancelado")
        RETURNED = "returned", _("devolvido")

    STATUS_NEW = Status.NEW
    STATUS_CONFIRMED = Status.CONFIRMED
    STATUS_PREPARING = Status.PREPARING
    STATUS_READY = Status.READY
    STATUS_DISPATCHED = Status.DISPATCHED
    STATUS_DELIVERED = Status.DELIVERED
    STATUS_COMPLETED = Status.COMPLETED
    STATUS_CANCELLED = Status.CANCELLED
    STATUS_RETURNED = Status.RETURNED
    STATUS_CHOICES = Status.choices

    DEFAULT_TRANSITIONS = {
        Status.NEW: [Status.CONFIRMED, Status.CANCELLED],
        Status.CONFIRMED: [Status.PREPARING, Status.READY, Status.CANCELLED],
        Status.PREPARING: [Status.READY, Status.CANCELLED],
        Status.READY: [Status.DISPATCHED, Status.COMPLETED],
        Status.DISPATCHED: [Status.DELIVERED, Status.RETURNED],
        Status.DELIVERED: [Status.COMPLETED, Status.RETURNED],
        Status.COMPLETED: [Status.RETURNED],
        Status.CANCELLED: [],
        Status.RETURNED: [],
    }

    TERMINAL_STATUSES = [Status.COMPLETED, Status.CANCELLED, Status.RETURNED]

    ref = models.CharField(_("referência"), max_length=64, unique=True)
    channel_ref = models.CharField(_("canal de venda"), max_length=64, db_index=True, default="")
    session_key = models.CharField(_("chave da sessão"), max_length=64, db_index=True, default="")

    handle_type = models.CharField(_("tipo de identificação"), max_length=32, null=True, blank=True)
    handle_ref = models.CharField(_("identificador"), max_length=64, null=True, blank=True)
    external_ref = models.CharField(_("referência externa"), max_length=128, null=True, blank=True, db_index=True)

    status = models.CharField(
        _("status"),
        max_length=32,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )

    snapshot = models.JSONField(
        _("snapshot"), default=dict, blank=True, encoder=DecimalEncoder,
        help_text=_("Snapshot selado do pedido no momento da criação. Não editar manualmente."),
    )
    data = models.JSONField(
        _("dados extras"), default=dict, blank=True, encoder=DecimalEncoder,
        help_text=_('Dados extras do pedido. Formato livre. Ex: {"notes": "Sem cebola", "delivery_address": "Rua X, 123"}'),
    )

    currency = models.CharField(_("moeda"), max_length=3, default="BRL")
    total_q = models.BigIntegerField(_("total (q)"), default=0)

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)
    confirmed_at = models.DateTimeField(_("confirmado em"), null=True, blank=True)
    preparing_at = models.DateTimeField(_("em preparo em"), null=True, blank=True)
    ready_at = models.DateTimeField(_("pronto em"), null=True, blank=True)
    dispatched_at = models.DateTimeField(_("despachado em"), null=True, blank=True)
    delivered_at = models.DateTimeField(_("entregue em"), null=True, blank=True)
    completed_at = models.DateTimeField(_("concluído em"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelado em"), null=True, blank=True)
    returned_at = models.DateTimeField(_("devolvido em"), null=True, blank=True)

    class Meta:
        app_label = "omniman"
        verbose_name = _("pedido")
        verbose_name_plural = _("pedidos")
        ordering = ("-created_at", "id")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_status = self.status
        self._transition_actor: str | None = None

    def __str__(self) -> str:
        if self.handle_ref and self.handle_type:
            handle_type = (
                str(self.handle_type)
                .replace("_", " ")
                .replace("-", " ")
                .strip()
                .title()
            )
            return f"{handle_type}: {self.handle_ref}"
        return self.ref

    # ------------------------------------------------------------------ status

    def get_transitions(self) -> dict[str, list[str]]:
        """Retorna o mapa de transições baked no snapshot ou o padrão."""
        lifecycle = (self.snapshot or {}).get("lifecycle", {})
        return lifecycle.get("transitions") or self.DEFAULT_TRANSITIONS

    def get_terminal_statuses(self) -> list[str]:
        """Retorna os status terminais baked no snapshot ou o padrão."""
        lifecycle = (self.snapshot or {}).get("lifecycle", {})
        return lifecycle.get("terminal_statuses") or self.TERMINAL_STATUSES

    def get_allowed_transitions(self) -> list[str]:
        """Retorna os próximos status válidos a partir do status atual."""
        transitions = self.get_transitions()
        return transitions.get(self.status, [])

    def can_transition_to(self, new_status: str) -> bool:
        """Verifica se a transição para new_status é permitida."""
        return new_status in self.get_allowed_transitions()

    STATUS_TIMESTAMP_FIELDS = {
        STATUS_CONFIRMED: "confirmed_at",
        STATUS_PREPARING: "preparing_at",
        STATUS_READY: "ready_at",
        STATUS_DISPATCHED: "dispatched_at",
        STATUS_DELIVERED: "delivered_at",
        STATUS_COMPLETED: "completed_at",
        STATUS_CANCELLED: "cancelled_at",
        STATUS_RETURNED: "returned_at",
    }

    def save(self, *args, **kwargs):
        status_changed = self.pk and self.status != self._original_status
        old_status = self._original_status

        if status_changed:
            from shopman.omniman.exceptions import InvalidTransition

            transitions = self.get_transitions()
            allowed = transitions.get(old_status, [])
            if self.status not in allowed:
                raise InvalidTransition(
                    code="invalid_transition",
                    message=f"Transição {old_status} → {self.status} não permitida",
                    context={
                        "current_status": old_status,
                        "requested_status": self.status,
                        "allowed_transitions": allowed,
                    },
                )

            # Domain invariant: dispatched is exclusive to delivery orders.
            # Guard uses fulfillment_type (canonical key) with fallback to legacy delivery_method.
            if self.status == self.Status.DISPATCHED:
                ft = self.data.get("fulfillment_type") or self.data.get("delivery_method", "")
                if ft and ft != "delivery":
                    raise InvalidTransition(
                        code="dispatched_requires_delivery",
                        message="Transição para 'dispatched' requer pedido de delivery",
                        context={"fulfillment_type": ft},
                    )

            ts_field = self.STATUS_TIMESTAMP_FIELDS.get(self.status)
            if ts_field and getattr(self, ts_field) is None:
                setattr(self, ts_field, timezone.now())

        super().save(*args, **kwargs)
        self._original_status = self.status

        if status_changed:
            actor = self._transition_actor or "direct"
            self._transition_actor = None

            self.emit_event(
                event_type="status_changed",
                actor=actor,
                payload={
                    "old_status": old_status,
                    "new_status": self.status,
                },
            )

            from shopman.omniman.signals import order_changed
            order_changed.send(
                sender=Order,
                order=self,
                event_type="status_changed",
                actor=actor,
            )

    @transaction.atomic
    def transition_status(self, new_status: str, actor: str = "system") -> None:
        """
        Transiciona o status do pedido validando regras do canal.

        Usa select_for_update() para segurança concorrente.
        O save() cuida de validação, timestamp, evento e signal.

        Raises:
            InvalidTransition: Se a transição não for permitida
        """
        order = Order.objects.select_for_update().get(pk=self.pk)
        order.status = new_status
        order._transition_actor = actor
        order.save()

        # Sync self from the locked row
        for field in self._meta.get_fields():
            if hasattr(field, "attname"):
                setattr(self, field.attname, getattr(order, field.attname))
        self._original_status = order._original_status

    def emit_event(self, event_type: str, actor: str = "system", payload: dict | None = None) -> OrderEvent:
        """
        Emite um evento no audit log do pedido.

        Calcula seq automaticamente como MAX(seq) + 1 para este order.
        Usa select_for_update() para evitar condição de corrida em criações concorrentes.
        """
        from django.db import transaction
        from django.db.models import Max, Value
        from django.db.models.functions import Coalesce

        with transaction.atomic():
            last_seq = self.events.select_for_update().aggregate(
                m=Coalesce(Max("seq"), Value(-1))
            )["m"]

            return OrderEvent.objects.create(
                order=self,
                seq=last_seq + 1,
                type=event_type,
                actor=actor,
                payload=payload or {},
            )


class OrderItem(models.Model):
    """Item de um pedido."""

    order = models.ForeignKey(Order, verbose_name=_("pedido"), on_delete=models.CASCADE, related_name="items")

    line_id = models.CharField(_("ID da linha"), max_length=64)
    sku = models.CharField(_("SKU"), max_length=64)
    name = models.CharField(_("nome"), max_length=200, blank=True, default="")

    qty = models.DecimalField(_("quantidade"), max_digits=12, decimal_places=3)
    unit_price_q = models.BigIntegerField(_("preço unitário (q)"))
    line_total_q = models.BigIntegerField(_("total da linha (q)"))

    meta = models.JSONField(
        _("metadados"), default=dict, blank=True,
        help_text=_('Metadados do item. Ex: {"customization": "sem gluten", "gift_wrap": true}'),
    )

    class Meta:
        app_label = "omniman"
        verbose_name = _("item do pedido")
        verbose_name_plural = _("itens do pedido")
        constraints = [
            models.UniqueConstraint(
                fields=["order", "line_id"],
                name="ord_uniq_order_item_line_id",
            ),
            models.CheckConstraint(
                condition=models.Q(qty__gt=0),
                name="ord_order_item_qty_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sku} x {self.qty}"


class OrderEvent(models.Model):
    """
    Audit log append-only para pedidos.

    Ordenado por seq (sequência monotônica por order).
    """

    order = models.ForeignKey(Order, verbose_name=_("pedido"), on_delete=models.CASCADE, related_name="events")

    seq = models.PositiveIntegerField(_("sequência"), default=0)
    type = models.CharField(_("tipo"), max_length=64, db_index=True)
    actor = models.CharField(_("ator"), max_length=128)
    payload = models.JSONField(
        _("payload"), default=dict,
        help_text=_('Dados do evento. Ex: {"new_status": "confirmed"} ou {"error": "motivo"}'),
    )

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        app_label = "omniman"
        verbose_name = _("evento do pedido")
        verbose_name_plural = _("eventos do pedido")
        ordering = ("seq",)
        constraints = [
            models.UniqueConstraint(
                fields=["order", "seq"],
                name="ord_uniq_order_event_seq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type} #{self.seq} @ {self.created_at}"
