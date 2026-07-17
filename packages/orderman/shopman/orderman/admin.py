from __future__ import annotations

import logging
from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.db import models
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from shopman.orderman.integrations import get_shop_channel_model

# Unfold is optional - fallback to standard Django admin if not installed
try:
    from unfold.admin import ModelAdmin as UnfoldModelAdmin
    from unfold.contrib.filters.admin.choice_filters import ChoicesRadioFilter
    from unfold.contrib.filters.admin.datetime_filters import RangeDateFilter
    from unfold.contrib.filters.admin.numeric_filters import RangeNumericFilter
    from unfold.decorators import action as unfold_action
    from unfold.decorators import display as unfold_display
    from unfold.enums import ActionVariant
    from unfold.sections import TableSection

    UNFOLD_AVAILABLE = True
    ModelAdmin = UnfoldModelAdmin

    # Use unfold decorators
    def action(func=None, **kwargs):
        return unfold_action(func, **kwargs) if func else unfold_action(**kwargs)

    def display(**kwargs):
        return unfold_display(**kwargs)

except ImportError:
    UNFOLD_AVAILABLE = False
    ModelAdmin = admin.ModelAdmin

    class ActionVariant:
        DEFAULT = "default"
        SUCCESS = "success"
        DANGER = "danger"
        WARNING = "warning"

    class TableSection:
        pass

    # Fallback for filters — must inherit FieldListFilter for tuple-style
    # list_filter entries like ("field", ChoicesRadioFilter) to pass
    # Django 5.x system checks (admin.E115).
    class RangeDateFilter(admin.FieldListFilter):
        """Fallback date range filter."""
        pass

    class RangeNumericFilter(admin.FieldListFilter):
        """Fallback numeric range filter."""
        pass

    class ChoicesRadioFilter(admin.FieldListFilter):
        """Fallback filter when Unfold is not available.

        Standard Django FieldListFilter — renders as default dropdown.
        Unfold's version renders radio buttons, but behavior is identical.
        """
        pass

    # Fallback decorators that work with standard Django admin
    def action(func=None, **kwargs):
        """Fallback action decorator."""
        django_kwargs = {}
        if "description" in kwargs:
            django_kwargs["description"] = kwargs["description"]
        if func:
            return admin.action(**django_kwargs)(func)
        return admin.action(**django_kwargs)

    def display(**kwargs):
        """Fallback display decorator."""
        django_kwargs = {}
        if "description" in kwargs:
            django_kwargs["description"] = kwargs["description"]
        if "ordering" in kwargs:
            django_kwargs["ordering"] = kwargs["ordering"]
        if "boolean" in kwargs:
            django_kwargs["boolean"] = kwargs["boolean"]
        return admin.display(**django_kwargs)

from shopman.orderman import registry
from shopman.orderman.models import (
    Directive,
    Fulfillment,
    FulfillmentItem,
    IdempotencyKey,
    Order,
    OrderEvent,
    OrderItem,
    Session,
    SessionEvent,
)
from shopman.utils.monetary import format_money

logger = logging.getLogger(__name__)


# =============================================================================
# ACTIONS DETAIL (botões no nível do breadcrumb)
# =============================================================================


def history_action(modeladmin, request, object_id):
    """Action que redireciona para o histórico do objeto."""
    url = reverse(
        f"admin:{modeladmin.model._meta.app_label}_{modeladmin.model._meta.model_name}_history",
        args=[object_id],
    )
    return HttpResponseRedirect(url)


def _format_admin_qty(value: Decimal) -> str:
    quantized = Decimal(value).quantize(Decimal("0.001")).normalize()
    return format(quantized, "f")


class SalesChannelFilter(admin.SimpleListFilter):
    title = _("canal")
    parameter_name = "channel_ref"

    def lookups(self, request, model_admin):
        Channel = get_shop_channel_model()
        if Channel is None:
            return []
        qs = Channel.objects.filter(is_active=True).order_by(
            "display_order", "name", "ref"
        )
        return [(c.ref, c.name or c.ref) for c in qs]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        return queryset.filter(channel_ref=value)


@admin.register(Session)
class SessionAdmin(ModelAdmin):
    change_form_template = "orderman/admin/session_change_form.html"
    list_display = (
        "session_key",
        "channel_ref",
        "handle_type",
        "handle_ref",
        "state_badge",
        "rev",
        "updated_at",
    )
    list_filter = (SalesChannelFilter, ("state", ChoicesRadioFilter))
    search_fields = ("session_key", "channel_ref", "handle_type", "handle_ref")
    ordering = ("-updated_at", "-id")
    date_hierarchy = "updated_at"
    list_filter_submit = True
    list_fullwidth = True
    compressed_fields = True
    warn_unsaved_form = True

    # Todos os campos são readonly - Sessões são imutáveis após criação.
    # A operação (finalizar, resolver problemas) vive no POS e no Gestor.
    readonly_fields = (
        "channel_ref",
        "session_key",
        "session_key_content",
        "session_key_display",
        "state",
        "handle_type",
        "handle_ref",
        "opened_at",
        "updated_at",
        "committed_at",
        "rev",
        "items_display",
        "audit_timeline",
        "data",
        "commit_token",
    )

    @display(description=_("chave da sessão"))
    def session_key_content(self, obj: Session) -> str:
        """Exibe session_key na aba Conteúdo (repetido propositalmente para consistência visual)."""
        return obj.session_key if obj else "-"

    @display(description=_("chave da sessão"))
    def session_key_display(self, obj: Session) -> str:
        """Exibe session_key na aba Auditoria (repetido propositalmente para consistência com FrontDeskAdmin)."""
        return obj.session_key if obj else "-"

    @display(description=_("itens"))
    def items_display(self, obj: Session) -> str:
        """Exibe items formatado de forma legível, igual ao campo Dados."""
        if not obj or not obj.items:
            return "-"
        import json
        try:
            formatted = json.dumps(obj.items, indent=2, ensure_ascii=False, sort_keys=False)
            return format_html('<pre class="bg-base-50 border border-base-200 dark:bg-base-800 dark:border-base-700 font-mono overflow-x-auto p-3 rounded-default text-sm">{}</pre>', formatted)
        except Exception:
            logger.debug("JSON format failed for Session.items pk=%s", obj.pk, exc_info=True)
            return str(obj.items)

    @display(description=_("trilha de auditoria"))
    def audit_timeline(self, obj: Session) -> str:
        """Linha do tempo unificada por ``session_key``: eventos da fase comanda
        (``SessionEvent``) + da fase pedido (``OrderEvent`` do Order de mesmo
        session_key). Append-only — conferência anti-fraude."""
        if not obj:
            return "-"
        from django.utils.html import format_html_join
        from shopman.orderman.models import Order, SessionEvent

        rows = []
        for ev in SessionEvent.objects.filter(session_key=obj.session_key).order_by("seq"):
            rows.append((ev.created_at, _("comanda"), ev.type, ev.actor, ev.payload))
        order = Order.objects.filter(session_key=obj.session_key).order_by("created_at").first()
        if order is not None:
            for ev in order.events.all().order_by("seq"):
                rows.append((ev.created_at, _("pedido"), ev.type, ev.actor, ev.payload))
        rows.sort(key=lambda row: (row[0] is None, row[0]))
        if not rows:
            return format_html('<p class="text-base-500 text-sm">{}</p>', _("Sem eventos registrados."))

        body = format_html_join(
            "",
            '<li class="border-b border-base-200 dark:border-base-700 py-1.5 text-sm">'
            '<span class="font-mono text-base-500">{}</span> '
            '<span class="rounded-default bg-base-100 dark:bg-base-800 px-1.5 py-0.5 text-xs">{}</span> '
            '<strong>{}</strong> '
            '<span class="text-base-500">· {} · {}</span>'
            "</li>",
            (
                (
                    created_at.strftime("%d/%m %H:%M:%S") if created_at else "—",
                    phase,
                    event_type,
                    actor or "—",
                    self._audit_summary(payload),
                )
                for created_at, phase, event_type, actor, payload in rows
            ),
        )
        return format_html('<ul class="divide-base-200 dark:divide-base-700 divide-y">{}</ul>', body)

    @staticmethod
    def _audit_summary(payload: dict) -> str:
        """Compact human summary of an audit event payload."""
        if not payload:
            return ""
        if isinstance(payload.get("items"), list):
            base = f'{payload.get("item_count", len(payload["items"]))} itens'
            return base + (" · estava na cozinha" if payload.get("was_fired") else "")
        if isinstance(payload.get("lines"), list):
            return ", ".join(f'{ln.get("name") or ln.get("sku")}×{ln.get("qty")}' for ln in payload["lines"][:4])
        if "qty_before" in payload:
            return f'{payload.get("name") or payload.get("sku")}: {payload["qty_before"]}→{payload["qty_after"]}'
        if "sku" in payload:
            name = payload.get("name") or payload.get("sku")
            return f"{name}" + (f' ×{payload["qty"]}' if payload.get("qty") is not None else "")
        if "order_ref" in payload:
            total = f' · R$ {int(payload["total_q"]) / 100:.2f}' if payload.get("total_q") else ""
            return f'pedido {payload["order_ref"]}{total}'
        if "from_ref" in payload:
            return f'{payload.get("from_ref")} → {payload.get("to_ref")}'
        if "new_status" in payload:
            return f'→ {payload["new_status"]}'
        return ", ".join(f"{key}={value}" for key, value in list(payload.items())[:3])

    actions_detail = ["history_detail_action"]

    @action(description=_("Histórico"), url_path="history-action", icon="history")
    def history_detail_action(self, request, object_id):
        return history_action(self, request, object_id)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        """Remove botões extras de submit."""
        # Remove botões "Salvar e adicionar outro" e "Salvar e continuar editando"
        context["show_save_and_add_another"] = False
        context["show_save_and_continue"] = False
        return super().render_change_form(request, context, add, change, form_url, obj)

    fieldsets = (
        (
            _("Identidade"),
            {"fields": ("session_key", "channel_ref", "handle_type", "handle_ref"), "classes": ("tab",)},
        ),
        (_("Conteúdo"), {"fields": ("session_key_content", "items_display", "data"), "classes": ("tab",)}),
        (
            _("Auditoria"),
            {
                "fields": ("session_key_display", "state", "opened_at", "updated_at", "rev"),
                "classes": ("tab",),
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request).prefetch_related("items")
        return qs.order_by("-updated_at", "-id")

    # Cores de referência BADGES:
    # - Azul=#5EB1EF (info), Amarelo=#E2A336 (warning), Verde=#5BB98B (success), Vermelho=#EB8E90 (danger), Cinza=secondary
    # - aberta=azul, fechada=cinza, abandonada=vermelho
    @display(
        description=_("status"),
        label={"aberta": "info", "fechada": "secondary", "abandonada": "danger"},
    )
    def state_badge(self, obj: Session) -> str:
        return obj.get_state_display()

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            obj = self.get_object(request, object_id)
            if obj:
                extra_context["issue_actions"] = obj.data.get("issues", [])
        extra_context.setdefault("issue_actions", [])
        return super().changeform_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        # UX: tab padrão = "Abertas" quando não há nenhum filtro explícito.
        if request.method == "GET" and not request.GET:
            return HttpResponseRedirect(f"{request.path}?state__exact=open")

        # UX: date_hierarchy default = hoje quando o operador não escolheu data.
        if request.method == "GET" and self.date_hierarchy:
            field = str(self.date_hierarchy)
            year_p = f"{field}__year"
            month_p = f"{field}__month"
            day_p = f"{field}__day"
            if not any(p in request.GET for p in (year_p, month_p, day_p)):
                today = timezone.localdate()
                q = request.GET.copy()
                q[year_p] = str(today.year)
                q[month_p] = str(today.month)
                q[day_p] = str(today.day)
                return HttpResponseRedirect(f"{request.path}?{q.urlencode()}")

        # Supra-filtro por canal (barra rápida) — preserva contexto e mantém intenção do status (tabs).
        extra_context = extra_context or {}

        Channel = get_shop_channel_model()
        channels = (
            list(
                Channel.objects.filter(is_active=True).order_by(
                    "display_order", "name", "ref"
                )
            )
            if Channel is not None
            else []
        )

        def _qs_for_channel(channel_id: str | None) -> str:
            q = request.GET.copy()
            # Status (tabs): se não houver status explícito, default é "Abertas"
            if "state__exact" not in request.GET:
                q["state__exact"] = "open"
            q.pop("p", None)
            if channel_id:
                q["channel__id__exact"] = str(channel_id)
            else:
                q.pop("channel__id__exact", None)
            return q.urlencode()

        extra_context["channel_quick_filters"] = [
            {
                "id": c.pk,
                "label": c.name or c.ref,
                "ref": c.ref,
                "querystring": _qs_for_channel(str(c.pk)),
            }
            for c in channels
        ]
        extra_context["channel_quick_filters_all"] = _qs_for_channel(None)

        return super().changelist_view(request, extra_context=extra_context)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "line_id",
        "sku",
        "name",
        "qty",
        "unit_price_q",
        "line_total_q",
        "meta",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    readonly_fields = ("type", "actor", "payload", "created_at")
    can_delete = False
    ordering = ("-created_at", "-id")

    def has_add_permission(self, request, obj=None):
        return False


class FulfillmentOrderInline(admin.TabularInline):
    """Read-only view of the order's fulfillments (carrier, tracking, dates)."""

    model = Fulfillment
    extra = 0
    fields = ("status", "carrier", "tracking_code", "dispatched_at", "delivered_at")
    readonly_fields = ("status", "carrier", "tracking_code", "dispatched_at", "delivered_at")
    can_delete = False
    verbose_name = _("fulfillment")
    verbose_name_plural = _("fulfillments")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SessionEvent)
class SessionEventAdmin(ModelAdmin):
    """Read-only audit trail of session-phase actions (anti-fraud conference).

    Append-only by design: creation happens only via ``Session.emit_event``;
    add/change/delete are all disabled so the trail cannot be tampered with
    through the Admin (same posture as ``OrderEvent``, taken to fully read-only
    because this log defends against the operators who use the system)."""

    list_display = ("created_at", "session_key", "seq", "type", "actor", "summary")
    list_filter = ("type", "actor")
    search_fields = ("session_key", "actor", "type")
    ordering = ("-created_at", "-id")
    date_hierarchy = "created_at"
    list_filter_submit = True
    list_fullwidth = True
    readonly_fields = ("session_key", "seq", "type", "actor", "payload", "created_at")

    @display(description=_("resumo"))
    def summary(self, obj: SessionEvent) -> str:
        return SessionAdmin._audit_summary(obj.payload or {})

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


if UNFOLD_AVAILABLE:
    class OrderItemSection(TableSection):
        related_name = "items"
        fields = ["sku", "name", "qty", "unit_price_q", "line_total_q"]
        verbose_name = _("Itens do Pedido")

        def unit_price_q(self, obj):
            return f"R$ {format_money(obj.unit_price_q)}"
        unit_price_q.short_description = _("Preço Unit.")

        def line_total_q(self, obj):
            return f"R$ {format_money(obj.line_total_q)}"
        line_total_q.short_description = _("Total")


class PreorderFilter(admin.SimpleListFilter):
    """Filter orders by preorder status (delivery_date in the future)."""
    title = _("encomenda")
    parameter_name = "preorder"

    def lookups(self, request, model_admin):
        return [
            ("yes", _("Encomendas")),
            ("no", _("Pedidos normais")),
        ]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(data__is_preorder=True)
        if self.value() == "no":
            return queryset.exclude(data__is_preorder=True)
        return queryset


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    # Changelist Unfold padrão (history/auditoria). A operação de pedidos vive no app
    # Nuxt dedicado (Gestor); o template custom anterior era chrome do console removido.
    list_display = (
        "ref",
        "channel_ref",
        "handle_ref",
        "status_badge",
        "delivery_date_display",
        "items_count_display",
        "units_count_display",
        "production_wait_display",
        "total_display",
        "operation_link_display",
        "created_at",
    )
    list_filter = (
        SalesChannelFilter,
        ("status", ChoicesRadioFilter),
        PreorderFilter,
        ("created_at", RangeDateFilter),
        ("total_q", RangeNumericFilter),
    )
    search_fields = ("ref", "channel_ref", "session_key", "handle_ref", "external_ref")
    ordering = ("-created_at", "-id")
    date_hierarchy = "created_at"
    list_filter_submit = True
    list_fullwidth = True
    compressed_fields = True
    warn_unsaved_form = True

    inlines = [OrderItemInline, OrderEventInline, FulfillmentOrderInline]

    actions_detail = ["history_detail_action"]
    list_sections = [OrderItemSection] if UNFOLD_AVAILABLE else []

    @action(description=_("Histórico"), url_path="history-action", icon="history")
    def history_detail_action(self, request, object_id):
        return history_action(self, request, object_id)

    fieldsets = (
        (
            _("Identidade"),
            {
                "fields": ("ref", "channel_ref", "status", "external_ref"),
                "classes": ("tab",),
            },
        ),
        (
            _("Origem"),
            {"fields": ("session_key", "handle_type", "handle_ref"), "classes": ("tab",)},
        ),
        (_("Valores"), {"fields": ("currency", "total_q"), "classes": ("tab",)}),
        (_("Dados"), {"fields": ("data",), "classes": ("tab",)}),
        (_("Snapshot"), {"fields": ("snapshot",), "classes": ("tab",)}),
        (_("Auditoria"), {"fields": ("created_at", "updated_at"), "classes": ("tab",)}),
    )
    # Todos os campos são readonly - Pedidos são imutáveis após criação.
    # A operação (avançar, cancelar) vive no Gestor de pedidos.
    readonly_fields = (
        "ref",
        "channel_ref",
        "session_key",
        "handle_type",
        "handle_ref",
        "external_ref",
        "status",
        "data",
        "snapshot",
        "currency",
        "total_q",
        "created_at",
        "updated_at",
    )

    # Cores de referência BADGES:
    # - Azul=#5EB1EF (info), Amarelo=#E2A336 (warning), Verde=#5BB98B (success), Vermelho=#EB8E90 (danger), Cinza=secondary
    # Status canônicos: new, confirmed, preparing, ready, dispatched, delivered, completed, cancelled, returned
    @display(
        description=_("status"),
        label={
            "novo": "info",
            "confirmado": "info",
            "em preparo": "warning",
            "pronto": "success",
            "despachado": "warning",
            "entregue": "success",
            "concluído": "secondary",
            "cancelado": "danger",
            "devolvido": "danger",
        },
    )
    def status_badge(self, obj: Order) -> str:
        return obj.get_status_display()

    @display(description=_("entrega"))
    def delivery_date_display(self, obj: Order) -> str:
        delivery_date = (obj.data or {}).get("delivery_date")
        if not delivery_date:
            return "-"
        is_preorder = (obj.data or {}).get("is_preorder", False)
        time_slot = (obj.data or {}).get("delivery_time_slot", "")
        label = delivery_date
        if time_slot:
            label += f" ({time_slot})"
        if is_preorder:
            return format_html('<span style="color:#E2A336;font-weight:600">{}</span>', label)
        return label

    @display(description=_("linhas"))
    def items_count_display(self, obj: Order) -> str:
        count = obj.items.count()
        return str(count) if count else "-"

    @display(description=_("un."))
    def units_count_display(self, obj: Order) -> str:
        total = sum((item.qty or Decimal("0")) for item in obj.items.all())
        return _format_admin_qty(total) if total else "-"

    @display(description=_("produção"))
    def production_wait_display(self, obj: Order) -> str:
        refs = tuple(dict.fromkeys((obj.data or {}).get("awaiting_wo_refs") or ()))
        if not refs:
            return "-"
        label = f"{len(refs)} OP"
        return format_html(
            '<span class="font-medium text-amber-700 dark:text-amber-400" title="{}">{}</span>',
            ", ".join(refs),
            label,
        )

    @display(description=_("total"))
    def total_display(self, obj: Order) -> str:
        if obj.total_q:
            return f"{obj.currency} {obj.total_q / 100:.2f}"
        return "-"

    @display(description=_("ação"))
    def operation_link_display(self, obj: Order) -> str:
        active_statuses = {
            Order.Status.NEW,
            Order.Status.CONFIRMED,
            Order.Status.PREPARING,
            Order.Status.READY,
            Order.Status.DISPATCHED,
            Order.Status.DELIVERED,
        }
        if obj.status not in active_statuses:
            return "-"
        url = reverse("admin_console_order_detail", args=[obj.ref])
        return format_html(
            '<a class="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400" href="{}">Fila</a>',
            url,
        )

    def changelist_view(self, request, extra_context=None):
        # UX: tab padrão = "Novos" quando não há nenhum filtro explícito.
        # Mas preserva filtros existentes (ex: ref=) se presentes
        if request.method == "GET" and not request.GET:
            return HttpResponseRedirect(f"{request.path}?status__exact=new")
        elif request.method == "GET" and "ref" in request.GET and "status__exact" not in request.GET:
            # Se há filtro por ref mas não há status, adiciona status=new preservando ref
            q = request.GET.copy()
            q["status__exact"] = "new"
            return HttpResponseRedirect(f"{request.path}?{q.urlencode()}")

        # UX: date_hierarchy default = hoje quando o operador não escolheu data.
        if request.method == "GET" and self.date_hierarchy:
            field = str(self.date_hierarchy)
            year_p = f"{field}__year"
            month_p = f"{field}__month"
            day_p = f"{field}__day"
            if not any(p in request.GET for p in (year_p, month_p, day_p)):
                today = timezone.localdate()
                q = request.GET.copy()
                q[year_p] = str(today.year)
                q[month_p] = str(today.month)
                q[day_p] = str(today.day)
                return HttpResponseRedirect(f"{request.path}?{q.urlencode()}")

        # Supra-filtro por canal (barra rápida) — preserva contexto e mantém intenção do status (tabs).
        extra_context = extra_context or {}

        Channel = get_shop_channel_model()
        channels = (
            list(
                Channel.objects.filter(is_active=True).order_by(
                    "display_order", "name", "ref"
                )
            )
            if Channel is not None
            else []
        )

        def _qs_for_channel(channel_id: str | None) -> str:
            q = request.GET.copy()
            if "status__exact" not in request.GET:
                q["status__exact"] = "new"
            # remove alias possível
            q.pop("status", None)
            q.pop("p", None)
            if channel_id:
                q["channel__id__exact"] = str(channel_id)
            else:
                q.pop("channel__id__exact", None)
            return q.urlencode()

        extra_context["channel_quick_filters"] = [
            {
                "id": c.pk,
                "label": c.name or c.ref,
                "ref": c.ref,
                "querystring": _qs_for_channel(str(c.pk)),
            }
            for c in channels
        ]
        extra_context["channel_quick_filters_all"] = _qs_for_channel(None)

        return super().changelist_view(request, extra_context=extra_context)


class HighAttemptsFilter(admin.SimpleListFilter):
    title = "tentativas"
    parameter_name = "high_attempts"

    def lookups(self, request, model_admin):
        return [("yes", "≥ 3 tentativas")]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(attempts__gte=3)
        return queryset


@admin.register(Directive)
class DirectiveAdmin(ModelAdmin):
    list_display = ("topic", "status_badge", "error_code", "attempts", "available_at", "started_at", "created_at")
    list_filter = (("status", ChoicesRadioFilter), "topic", "error_code", HighAttemptsFilter)
    search_fields = (
        "topic",
        "payload",
        "payload__session_key",
        "payload__order_ref",
        "payload__channel_ref",
        "payload__holds__hold_id",
        "dedupe_key",
    )
    list_filter_submit = True
    ordering = ("-created_at", "-id")
    date_hierarchy = "created_at"
    list_fullwidth = True
    compressed_fields = True
    warn_unsaved_form = True

    actions = ["execute_now_action"]
    actions_row = ["execute_row"]

    fieldsets = (
        (
            _("Diretiva"),
            {"fields": ("topic", "status", "payload", "dedupe_key"), "classes": ("tab",)},
        ),
        (
            _("Execução"),
            {"fields": ("attempts", "available_at", "started_at", "error_code", "last_error"), "classes": ("tab",)},
        ),
        (_("Auditoria"), {"fields": ("created_at", "updated_at"), "classes": ("tab",)}),
    )
    # Todos os campos são readonly - Diretivas são criadas e gerenciadas automaticamente pelo sistema
    # Apenas ações podem modificar o estado (ex: "Executar agora")
    readonly_fields = (
        "topic",
        "status",
        "payload",
        "dedupe_key",
        "attempts",
        "available_at",
        "started_at",
        "error_code",
        "last_error",
        "created_at",
        "updated_at",
    )

    actions_detail = ["history_detail_action"]
    actions_submit_line = ["execute_now_detail_action"]

    @action(description=_("Histórico"), url_path="history-action", icon="history")
    def history_detail_action(self, request, object_id):
        return history_action(self, request, object_id)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        """Remove botões extras de submit."""
        # Remove botões "Salvar e adicionar outro" e "Salvar e continuar editando"
        context["show_save_and_add_another"] = False
        context["show_save_and_continue"] = False
        return super().render_change_form(request, context, add, change, form_url, obj)

    def _execute_directive(self, request, directive: Directive) -> tuple[bool, str | None]:
        """
        Executa a diretiva usando o handler registrado.

        Returns:
            (ok, error_message)
        """
        handler = registry.get_directive_handler(directive.topic)
        if handler is None:
            return False, _("Nenhum handler registrado para este tópico.")

        now = timezone.now()
        if directive.status not in ("queued", "failed"):
            return False, _("A diretiva não está em fila ou com erro.")
        if directive.available_at and directive.available_at > now:
            return False, _("A diretiva ainda não está disponível para execução.")

        Directive.objects.filter(pk=directive.pk).update(
            status="running",
            attempts=models.F("attempts") + 1,
            started_at=now,
            updated_at=now,
        )
        directive.refresh_from_db()

        try:
            handler.handle(
                message=directive,
                ctx={"actor": getattr(getattr(request, "user", None), "username", None) or "admin"},
            )
        except Exception as exc:  # pragma: no cover - logging side-effect
            logger.exception("Falha ao executar diretiva %s #%s", directive.topic, directive.pk)
            directive.status = "failed"
            directive.last_error = str(exc)
            directive.save(update_fields=["status", "last_error", "updated_at"])
            return False, str(exc)

        # Fallback: se o handler não marcou status, finalize como done.
        directive.refresh_from_db()
        if directive.status == "running":
            directive.status = "done"
            directive.last_error = ""
            directive.save(update_fields=["status", "last_error", "updated_at"])
        return True, None

    @action(description=_("Executar agora"), url_path="execute-now", icon="play_arrow")
    def execute_now_detail_action(self, request, object_id):
        directive = self.get_object(request, object_id)
        if directive is None:
            self.message_user(request, _("Diretiva não encontrada."), level="error")
            return HttpResponseRedirect(reverse("admin:orderman_directive_changelist"))

        ok, err = self._execute_directive(request, directive)
        if ok:
            self.message_user(request, _("Diretiva executada."))
        else:
            self.message_user(request, err or _("Falha ao executar diretiva."), level="error")

        return HttpResponseRedirect(reverse("admin:orderman_directive_change", args=[object_id]))

    @action(
        description=_("Executar ▸"),
        url_path="execute-row",
        icon="play_arrow",
        variant=ActionVariant.SUCCESS,
    )
    def execute_row(self, request, object_id):
        directive = self.get_object(request, object_id)
        if directive is None:
            messages.error(request, _("Diretiva não encontrada."))
            return HttpResponseRedirect(reverse("admin:orderman_directive_changelist"))

        if directive.status not in ("queued", "failed"):
            messages.warning(request, _("Diretiva não está em fila ou com erro."))
            return HttpResponseRedirect(reverse("admin:orderman_directive_changelist"))

        ok, err = self._execute_directive(request, directive)
        if ok:
            messages.success(request, _("Diretiva executada."))
        else:
            messages.error(request, err or _("Falha ao executar diretiva."))

        return HttpResponseRedirect(reverse("admin:orderman_directive_changelist"))

    @admin.action(description=_("Executar agora"))
    def execute_now_action(self, request, queryset):
        ok_count = 0
        skip_count = 0
        fail_count = 0

        for directive in queryset:
            ok, err = self._execute_directive(request, directive)
            if ok:
                ok_count += 1
            else:
                if err and "handler" in str(err).lower():
                    skip_count += 1
                else:
                    fail_count += 1

        if ok_count:
            self.message_user(request, _("Diretivas executadas: %(n)s") % {"n": ok_count})
        if skip_count:
            self.message_user(request, _("Diretivas ignoradas (sem handler): %(n)s") % {"n": skip_count}, level="warning")
        if fail_count:
            self.message_user(request, _("Diretivas com erro: %(n)s") % {"n": fail_count}, level="error")

    # Cores de referência BADGES:
    # - Azul=#5EB1EF (info), Amarelo=#E2A336 (warning), Verde=#5BB98B (success), Vermelho=#EB8E90 (danger), Cinza=secondary
    # - em fila=azul, em execução=amarelo, concluído=verde, com erro=vermelho
    @display(
        description=_("status"),
        label={
            "em fila": "info",
            "em execução": "warning",
            "concluído": "success",
            "falhou": "danger",
        },
    )
    def status_badge(self, obj: Directive) -> str:
        return obj.get_status_display()

    # Banner explicativo antes do formulário (hook do Unfold), como no demo v0.5.2
    change_form_before_template = "orderman/admin/directive_before.html"

    # Form customizado removido - todos os campos são readonly agora
    # Se precisar criar novas diretivas manualmente no futuro, pode adicionar form customizado

    def changelist_view(self, request, extra_context=None):
        # UX: tab padrão = "Em fila" quando não há nenhum filtro explícito.
        if request.method == "GET" and not request.GET:
            return HttpResponseRedirect(f"{request.path}?status__exact=queued")

        # UX: date_hierarchy default = hoje quando o operador não escolheu data.
        if request.method == "GET" and self.date_hierarchy:
            field = str(self.date_hierarchy)
            year_p = f"{field}__year"
            month_p = f"{field}__month"
            day_p = f"{field}__day"
            if not any(p in request.GET for p in (year_p, month_p, day_p)):
                today = timezone.localdate()
                q = request.GET.copy()
                q[year_p] = str(today.year)
                q[month_p] = str(today.month)
                q[day_p] = str(today.day)
                return HttpResponseRedirect(f"{request.path}?{q.urlencode()}")

        return super().changelist_view(request, extra_context=extra_context)


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(ModelAdmin):
    list_display = (
        "scope",
        "key",
        "status_badge",
        "response_code",
        "expires_at",
        "created_at",
    )
    list_filter = (("status", ChoicesRadioFilter), "scope")
    search_fields = ("scope", "key")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_filter_submit = True
    list_fullwidth = True
    compressed_fields = True

    fieldsets = (
        (_("Chave"), {"fields": ("scope", "key", "status"), "classes": ("tab",)}),
        (
            _("Resposta"),
            {"fields": ("response_code", "response_body"), "classes": ("tab",)},
        ),
        (_("Auditoria"), {"fields": ("expires_at", "created_at"), "classes": ("tab",)}),
    )
    readonly_fields = ("scope", "key", "response_code", "response_body", "created_at")

    actions_detail = ["history_detail_action"]

    @action(description=_("Histórico"), url_path="history-action", icon="history")
    def history_detail_action(self, request, object_id):
        return history_action(self, request, object_id)

    @display(
        description=_("status"),
        label={"em andamento": "warning", "concluído": "success", "falhou": "danger"},
    )
    def status_badge(self, obj: IdempotencyKey) -> str:
        return obj.get_status_display()


# =============================================================================
# FULFILLMENT ADMIN
# =============================================================================


class FulfillmentItemInline(admin.TabularInline):
    model = FulfillmentItem
    extra = 0
    readonly_fields = ("order_item", "qty")
    fields = ("order_item", "qty")


class FulfillmentAdminForm(forms.ModelForm):
    tracking_url = forms.URLField(label=_("URL de rastreio"), required=False, assume_scheme="https")

    class Meta:
        model = Fulfillment
        fields = "__all__"


@admin.register(Fulfillment)
class FulfillmentAdmin(ModelAdmin):
    form = FulfillmentAdminForm
    list_display = ("id", "order", "status_badge", "carrier", "tracking_code", "created_at")
    list_filter = (("status", ChoicesRadioFilter),)
    search_fields = ("order__ref", "tracking_code", "carrier")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_filter_submit = True
    list_fullwidth = True
    compressed_fields = True
    inlines = [FulfillmentItemInline]

    fieldsets = (
        (_("Pedido"), {"fields": ("order", "status"), "classes": ("tab",)}),
        (
            _("Rastreio"),
            {"fields": ("carrier", "tracking_code", "tracking_url"), "classes": ("tab",)},
        ),
        (_("Detalhes"), {"fields": ("notes", "meta"), "classes": ("tab",)}),
        (
            _("Datas"),
            {"fields": ("created_at", "dispatched_at", "delivered_at"), "classes": ("tab",)},
        ),
    )
    readonly_fields = ("created_at",)

    actions_detail = ["history_detail_action"]

    @action(description=_("Histórico"), url_path="history-action", icon="history")
    def history_detail_action(self, request, object_id):
        return history_action(self, request, object_id)

    @display(
        description=_("status"),
        label={
            "pendente": "info",
            "em andamento": "warning",
            "enviado": "info",
            "entregue": "success",
            "cancelado": "danger",
        },
    )
    def status_badge(self, obj: Fulfillment) -> str:
        return obj.get_status_display()
