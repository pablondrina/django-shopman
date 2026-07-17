"""Admin for POS terminals, CashShift, and CashMovement."""

from __future__ import annotations

from decimal import Decimal

from django import forms
from django.contrib import admin
from shopman.utils import unfold_badge, unfold_badge_numeric
from shopman.utils.monetary import format_money
from unfold.admin import ModelAdmin
from unfold.widgets import UnfoldAdminDecimalFieldWidget

from shopman.backstage.models import CashMovement, CashShift, POSTerminal


class CashMovementInline(admin.TabularInline):
    model = CashMovement
    extra = 0
    readonly_fields = ("movement_type", "amount_display", "reason", "created_by", "created_at")
    fields = ("movement_type", "amount_display", "reason", "created_by", "created_at")

    def amount_display(self, obj):
        return f"R$ {format_money(obj.amount_q)}"
    amount_display.short_description = "Valor"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CashShift)
class CashShiftAdmin(ModelAdmin):
    list_display = ("operator", "terminal", "opened_at", "status_display", "opening_display", "closing_display", "difference_display")
    list_filter = ("status", "terminal", "opened_at")
    search_fields = ("operator", "terminal__ref", "terminal__label")
    # ``notes`` é editável (gerente anota/corrige um turno fechado); a alteração
    # fica registrada no histórico do admin (LogEntry: quem/quando). Os valores
    # financeiros permanecem read-only (mutados só via PDV/serviço).
    readonly_fields = (
        "terminal", "operator", "opened_at", "closed_at", "status",
        "opening_display", "closing_display", "expected_display", "difference_display",
    )
    inlines = [CashMovementInline]
    ordering = ["-opened_at"]
    list_fullwidth = True
    compressed_fields = True

    def status_display(self, obj):
        if obj.status == CashShift.Status.OPEN:
            return unfold_badge("aberto", "yellow")
        return unfold_badge("fechado", "green")
    status_display.short_description = "Status"

    def opening_display(self, obj):
        return unfold_badge_numeric(f"R$ {format_money(obj.opening_amount_q)}", "base")
    opening_display.short_description = "Abertura"

    def closing_display(self, obj):
        if obj.blind_closing_amount_q is None:
            return "—"
        return unfold_badge_numeric(f"R$ {format_money(obj.blind_closing_amount_q)}", "base")
    closing_display.short_description = "Fechamento"

    def expected_display(self, obj):
        if obj.expected_amount_q is None:
            return "—"
        return f"R$ {format_money(obj.expected_amount_q)}"
    expected_display.short_description = "Esperado"

    def difference_display(self, obj):
        if obj.difference_q is None:
            return "—"
        sign = "+" if obj.difference_q >= 0 else ""
        color = "green" if obj.difference_q == 0 else "yellow"
        return unfold_badge_numeric(f"{sign}R$ {format_money(obj.difference_q)}", color)
    difference_display.short_description = "Diferença"

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_pos")


class CashMovementForm(forms.ModelForm):
    """Add-form for cash movements — valor em Reais (convertido p/ centavos)."""

    amount_reais = forms.DecimalField(
        label="Valor (R$)",
        min_value=Decimal("0.01"),
        max_digits=10,
        decimal_places=2,
        widget=UnfoldAdminDecimalFieldWidget,
        help_text="Valor do movimento em Reais (sempre positivo).",
    )

    class Meta:
        model = CashMovement
        fields = ("shift", "movement_type", "amount_reais", "reason")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.amount_q:
            self.fields["amount_reais"].initial = Decimal(self.instance.amount_q) / 100

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.amount_q = int((self.cleaned_data["amount_reais"] * 100).to_integral_value())
        if commit:
            instance.save()
        return instance


@admin.register(CashMovement)
class CashMovementAdmin(ModelAdmin):
    """Registro auditado de sangria/suprimento/ajuste (inclusive pós-fechamento).

    Existentes são imutáveis (trilha de auditoria); só é possível adicionar novos,
    com ``created_by`` carimbado pelo operador logado.
    """

    form = CashMovementForm
    list_display = ("shift", "movement_type", "amount_display", "reason", "created_by", "created_at")
    list_filter = ("movement_type", "created_at")
    search_fields = ("shift__operator", "reason", "created_by")
    readonly_fields = ("created_by", "created_at")
    ordering = ["-created_at"]
    compressed_fields = True

    def amount_display(self, obj):
        return f"R$ {format_money(obj.amount_q)}"
    amount_display.short_description = "Valor"

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return request.user.has_perm("backstage.operate_pos")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_pos")

    def has_module_permission(self, request):
        return request.user.has_perm("backstage.operate_pos")

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by:
            obj.created_by = request.user.get_username()
        super().save_model(request, obj, form, change)


@admin.register(POSTerminal)
class POSTerminalAdmin(ModelAdmin):
    list_display = ("ref", "label", "channel_ref", "health_display", "is_active")
    list_filter = ("is_active", "channel_ref")
    search_fields = ("ref", "label", "channel_ref")
    readonly_fields = ("health_display",)
    fields = ("ref", "label", "channel_ref", "location_ref", "is_active", "metadata", "health_display")
    compressed_fields = True

    _HEALTH = {
        "ready": ("pronto", "green"),
        "warning": ("atenção", "yellow"),
        "error": ("erro", "red"),
    }

    def health_display(self, obj):
        if obj is None:
            return "—"
        from shopman.backstage.services.pos_terminal import runtime_profile

        profile = runtime_profile(obj)
        label, color = self._HEALTH.get(profile.status, (profile.status, "base"))
        return unfold_badge(label, color)
    health_display.short_description = "saúde"
