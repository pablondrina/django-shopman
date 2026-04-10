"""ChannelConfigAdmin — per-channel configuration with tabbed aspects."""

from __future__ import annotations

import json

from django import forms
from django.contrib import admin
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin

from shopman.config import ChannelConfig
from shopman.models import ChannelConfigRecord


class ChannelConfigForm(forms.ModelForm):
    """Form that presents ChannelConfig aspects as individual JSON fields."""

    confirmation = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "class": "vLargeTextField"}),
        required=False,
        help_text="JSON: mode (immediate/optimistic/manual), timeout_minutes",
    )
    payment = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 5, "class": "vLargeTextField"}),
        required=False,
        help_text="JSON: method, timing, timeout_minutes",
    )
    fulfillment = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "vLargeTextField"}),
        required=False,
        help_text="JSON: timing, auto_sync",
    )
    stock = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "class": "vLargeTextField"}),
        required=False,
        help_text="JSON: hold_ttl_minutes, safety_margin, check_on_commit, allowed_positions",
    )
    notifications = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "vLargeTextField"}),
        required=False,
        help_text="JSON: backend, fallback_chain, routing",
    )
    pricing = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2, "class": "vLargeTextField"}),
        required=False,
        help_text='JSON: policy ("internal" ou "external")',
    )
    editing = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2, "class": "vLargeTextField"}),
        required=False,
        help_text='JSON: policy ("open" ou "locked")',
    )
    rules = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "class": "vLargeTextField"}),
        required=False,
        help_text="JSON: validators, modifiers, checks",
    )

    class Meta:
        model = ChannelConfigRecord
        fields = ("channel_ref",)

    _ASPECTS = (
        "confirmation", "payment", "fulfillment", "stock",
        "notifications", "pricing", "editing", "rules",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            data = self.instance.data or {}
            for aspect in self._ASPECTS:
                value = data.get(aspect, {})
                self.fields[aspect].initial = json.dumps(value, indent=2, ensure_ascii=False) if value else ""

    def clean(self):
        cleaned = super().clean()
        for aspect in self._ASPECTS:
            raw = cleaned.get(aspect, "").strip()
            if not raw:
                cleaned[aspect] = {}
                continue
            try:
                cleaned[aspect] = json.loads(raw)
            except json.JSONDecodeError as e:
                self.add_error(aspect, f"JSON inválido: {e}")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        data = instance.data or {}
        for aspect in self._ASPECTS:
            value = self.cleaned_data.get(aspect, {})
            if value:
                data[aspect] = value
            else:
                data.pop(aspect, None)
        instance.data = data

        # Validate the resulting config
        try:
            config = ChannelConfig.from_dict(data)
            config.validate()
        except (ValueError, TypeError) as e:
            raise forms.ValidationError(f"Config inválida: {e}") from e

        if commit:
            instance.save()
        return instance


@admin.register(ChannelConfigRecord)
class ChannelConfigAdmin(ModelAdmin):
    """Admin para configuração de canal com abas por aspecto.

    Cada registro sobreescreve a config padrão da loja (Shop.defaults) para um canal.
    Cascata completa: canal (este model) ← loja (Shop.defaults) ← defaults hardcoded.
    """

    form = ChannelConfigForm
    list_display = ("channel_ref", "pricing_display", "editing_display", "updated_at")
    search_fields = ("channel_ref",)
    readonly_fields = ("updated_at", "resolved_config_display")

    fieldsets = (
        (None, {"fields": ("channel_ref",)}),
        ("Confirmação", {"fields": ("confirmation",), "classes": ("tab",)}),
        ("Pagamento", {"fields": ("payment",), "classes": ("tab",)}),
        ("Fulfillment", {"fields": ("fulfillment",), "classes": ("tab",)}),
        ("Estoque", {"fields": ("stock",), "classes": ("tab",)}),
        ("Notificações", {"fields": ("notifications",), "classes": ("tab",)}),
        ("Pricing", {"fields": ("pricing",), "classes": ("tab",)}),
        ("Editing", {"fields": ("editing",), "classes": ("tab",)}),
        ("Regras", {"fields": ("rules",), "classes": ("tab",)}),
        ("Info", {"fields": ("resolved_config_display", "updated_at"), "classes": ("tab",)}),
    )

    @admin.display(description="pricing")
    def pricing_display(self, obj):
        policy = (obj.data or {}).get("pricing", {}).get("policy", "internal")
        color = "green" if policy == "internal" else "red"
        return mark_safe(f'<span style="color:{color}">{policy}</span>')

    @admin.display(description="editing")
    def editing_display(self, obj):
        policy = (obj.data or {}).get("editing", {}).get("policy", "open")
        color = "green" if policy == "open" else "red"
        return mark_safe(f'<span style="color:{color}">{policy}</span>')

    @admin.display(description="Config resolvida (cascata)")
    def resolved_config_display(self, obj):
        if not obj.pk:
            return "-"
        from shopman.omniman.models import Channel

        try:
            channel = Channel.objects.get(ref=obj.channel_ref)
            config = ChannelConfig.for_channel(channel)
            data = config.to_dict()
            formatted = json.dumps(data, indent=2, ensure_ascii=False)
            return mark_safe(f"<pre>{formatted}</pre>")
        except Channel.DoesNotExist:
            return mark_safe("<em>Canal não encontrado</em>")
