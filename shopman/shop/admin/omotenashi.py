"""Admin for OmotenashiCopy — override UI strings without editing code."""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from shopman.shop.models import OmotenashiCopy
from shopman.shop.omotenashi.copy import (
    AUDIENCE_CHOICES,
    MOMENT_CHOICES,
    all_keys,
    default_for,
)


class OmotenashiCopyForm(forms.ModelForm):
    """Form with dropdowns for key/moment/audience sourced from code defaults."""

    class Meta:
        model = OmotenashiCopy
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["key"] = forms.ChoiceField(
            label="chave",
            choices=sorted((k, k) for k in all_keys()),
            help_text="Cópias disponíveis estão definidas no código (omotenashi/copy.py).",
        )
        self.fields["moment"] = forms.ChoiceField(label="momento", choices=MOMENT_CHOICES)
        self.fields["audience"] = forms.ChoiceField(label="público", choices=AUDIENCE_CHOICES)


@admin.register(OmotenashiCopy)
class OmotenashiCopyAdmin(ModelAdmin):
    form = OmotenashiCopyForm
    list_display = ("key", "moment", "audience", "title_short", "active")
    list_filter = ("key", "moment", "audience", "active")
    list_editable = ("active",)
    search_fields = ("key", "title", "message")
    ordering = ("key", "moment", "audience")
    fieldsets = (
        (
            None,
            {
                "fields": ("key", "moment", "audience", "active"),
                "description": (
                    "Este registro sobrescreve o texto-padrão definido no código. "
                    'Moment e público "*" valem para qualquer valor.'
                ),
            },
        ),
        ("Cópia", {"fields": ("title", "message", "default_preview")}),
    )
    readonly_fields = ("default_preview",)
    actions = ("reset_to_default",)

    @admin.display(description="título")
    def title_short(self, obj: OmotenashiCopy) -> str:
        t = obj.title or obj.message
        return (t[:60] + "…") if len(t) > 60 else t

    @admin.display(description="padrão no código")
    def default_preview(self, obj: OmotenashiCopy) -> str:
        """Show the code-level default side by side so the operator sees what's being overridden."""
        if not obj.key:
            return "—"
        entry = default_for(obj.key, obj.moment or "*", obj.audience or "*")
        if not entry:
            return format_html('<em style="color:#a16207">sem padrão no código</em>')
        return format_html(
            '<div style="font-size:0.85rem;line-height:1.5">'
            '<div><strong>Título:</strong> {}</div>'
            '<div><strong>Mensagem:</strong> {}</div>'
            "</div>",
            entry.title or "—",
            entry.message or "—",
        )

    @admin.action(description="Resetar para padrão (desativar)")
    def reset_to_default(self, request, queryset):
        # QuerySet.update() skips post_save, so we invalidate the in-process
        # resolver cache explicitly to make the default take effect immediately.
        from shopman.shop.omotenashi.copy import invalidate_cache

        updated = queryset.update(active=False)
        invalidate_cache()
        self.message_user(request, f"{updated} cópia(s) desativada(s) — voltam ao padrão do código.")
