"""Admin for RuleConfig — configurable rules via Unfold.

Regras de preço conhecidas (happy_hour, d1_discount, employee_discount) editam
``params`` como campos tipados (percentual, horários); o JSON cru fica só para
regras sem schema. Os modifiers continuam lendo ``params`` igual — só a EDIÇÃO
muda. Ver ``shopman/shop/rules/params_schema.py``.
"""

from __future__ import annotations

from datetime import time

from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.widgets import (
    UnfoldAdminIntegerFieldWidget,
    UnfoldAdminTimeWidget,
)

from shopman.shop.models import RuleConfig
from shopman.shop.rules.params_schema import PERCENT, TIME, schema_for

# Campos tipados de params declarados no nível da classe (união entre schemas);
# o __init__ mantém só os relevantes ao ``code`` da regra.
PARAM_FIELD_PREFIX = "param_"


def _param_field_name(param_name: str) -> str:
    return f"{PARAM_FIELD_PREFIX}{param_name}"


def _format_time(value) -> str:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    raw = str(value or "").strip()
    return raw[:5]


class RuleTypeFilter(admin.SimpleListFilter):
    """Filter rules by type (modifier/validator) based on rule_path."""

    title = "tipo"
    parameter_name = "rule_type"

    def lookups(self, request, model_admin):
        return [
            ("modifier", "Modifier (pricing)"),
            ("validator", "Validator"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "modifier":
            return queryset.filter(rule_path__contains=".pricing.")
        if self.value() == "validator":
            return queryset.filter(rule_path__contains=".validation.")
        return queryset


class RuleConfigForm(forms.ModelForm):
    param_discount_percent = forms.IntegerField(
        label="Desconto (%)",
        required=False,
        min_value=0,
        max_value=100,
        widget=UnfoldAdminIntegerFieldWidget,
    )
    param_start = forms.TimeField(
        label="Início",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    param_end = forms.TimeField(
        label="Fim",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )

    class Meta:
        model = RuleConfig
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._schema = schema_for(getattr(self.instance, "code", None))
        if self._schema is None:
            # Regra sem schema → edita params como JSON; remove os campos tipados.
            for param_name in ("discount_percent", "start", "end"):
                self.fields.pop(_param_field_name(param_name), None)
            return

        # Regra conhecida → campos tipados; esconde o JSON cru.
        self.fields.pop("params", None)
        params = self.instance.params if isinstance(self.instance.params, dict) else {}
        schema_keys = {p.name for p in self._schema.params}
        for param_name in ("discount_percent", "start", "end"):
            if param_name not in schema_keys:
                self.fields.pop(_param_field_name(param_name), None)
        for param in self._schema.params:
            field = self.fields[_param_field_name(param.name)]
            field.label = param.label
            field.help_text = param.help_text
            if param.kind == TIME:
                field.initial = _format_time(params.get(param.name))
            else:
                field.initial = params.get(param.name)

    def clean(self):
        cleaned = super().clean()
        if self._schema is None:
            return cleaned
        # Happy hour: início precisa ser anterior ao fim.
        start = cleaned.get("param_start")
        end = cleaned.get("param_end")
        if start and end and start >= end:
            self.add_error("param_end", "O fim da janela precisa ser depois do início.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self._schema is not None:
            params = dict(instance.params) if isinstance(instance.params, dict) else {}
            for param in self._schema.params:
                value = self.cleaned_data.get(_param_field_name(param.name))
                if param.kind == PERCENT:
                    params[param.name] = int(value) if value is not None else 0
                elif param.kind == TIME:
                    params[param.name] = _format_time(value) if value else ""
            instance.params = params
        if commit:
            instance.save()
            self.save_m2m()
        return instance


@admin.register(RuleConfig)
class RuleConfigAdmin(ModelAdmin):
    form = RuleConfigForm
    # Prioridade de avaliação = lista arrastável (menor = avaliada primeiro).
    ordering_field = "priority"
    hide_ordering_field = True
    list_display = ("label", "code", "enabled", "rule_type_display", "params_summary")
    list_filter = ("enabled", RuleTypeFilter)
    search_fields = ("label", "code")
    list_editable = ("enabled",)
    ordering = ("priority",)
    filter_horizontal = ("channels",)
    actions = ["enable_rules", "disable_rules"]

    def get_fieldsets(self, request, obj=None):
        schema = schema_for(getattr(obj, "code", None)) if obj else None
        if schema is not None:
            param_fields = tuple(_param_field_name(p.name) for p in schema.params)
            params_section = (
                "Parâmetros",
                {
                    "fields": param_fields,
                    "description": "Parâmetros desta regra, editados como campos.",
                },
            )
        else:
            params_section = (
                "Parâmetros",
                {
                    "fields": ("params",),
                    "description": (
                        "Parâmetros JSON da regra. Regras de preço conhecidas "
                        "(happy hour, D-1, funcionário) ganham campos tipados ao salvar."
                    ),
                },
            )
        return [
            (None, {"fields": ("code", "label", "rule_path", "enabled", "priority")}),
            params_section,
            ("Canais", {
                "fields": ("channels",),
                "description": "Canais onde esta regra se aplica. Vazio = todos os canais.",
            }),
        ]

    def has_add_permission(self, request):
        return request.user.has_perm("shop.manage_rules")

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("shop.manage_rules")

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("shop.manage_rules")

    @admin.display(description="tipo")
    def rule_type_display(self, obj):
        if ".pricing." in obj.rule_path:
            return "Modifier"
        if ".validation." in obj.rule_path:
            return "Validator"
        return "—"

    @admin.display(description="parâmetros")
    def params_summary(self, obj):
        params = obj.params if isinstance(obj.params, dict) else {}
        if not params:
            return "—"
        return ", ".join(f"{k}={v}" for k, v in params.items())

    @admin.action(description="Ativar regras selecionadas")
    def enable_rules(self, request, queryset):
        updated = queryset.update(enabled=True)
        self.message_user(request, f"{updated} regra(s) ativada(s).")

    @admin.action(description="Desativar regras selecionadas")
    def disable_rules(self, request, queryset):
        updated = queryset.update(enabled=False)
        self.message_user(request, f"{updated} regra(s) desativada(s).")
