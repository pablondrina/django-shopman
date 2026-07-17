"""ChannelAdmin — Canal de venda com configuração integrada."""

from __future__ import annotations

import json
import logging

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.widgets import UnfoldAdminTextareaWidget

from shopman.shop.config import ChannelConfig, deep_merge
from shopman.shop.models import Channel

logger = logging.getLogger(__name__)


def _aspect_widget(rows: int) -> UnfoldAdminTextareaWidget:
    return UnfoldAdminTextareaWidget(attrs={"rows": rows})


# Cada aspecto é um override avançado (JSON). Vazio = herda da Configuração da
# Loja. As notas abaixo explicam, em pt-BR, o que cada knob controla.
_INHERIT = "Vazio = herda da loja."


class ChannelForm(forms.ModelForm):
    """Form com campos de config por aspecto."""

    confirmation = forms.CharField(
        label="Confirmação",
        widget=_aspect_widget(4),
        required=False,
        help_text=f"Como o pedido é aceito. JSON: mode (immediate/auto_confirm/auto_cancel/manual), timeout_minutes. {_INHERIT}",
    )
    payment = forms.CharField(
        label="Pagamento",
        widget=_aspect_widget(5),
        required=False,
        help_text=f"Como e quando o cliente paga. JSON: method, timing, timeout_minutes. {_INHERIT}",
    )
    fulfillment = forms.CharField(
        label="Preparo e entrega",
        widget=_aspect_widget(3),
        required=False,
        help_text=f"Quando preparar/despachar. JSON: timing, auto_sync. {_INHERIT}",
    )
    stock = forms.CharField(
        label="Estoque",
        widget=_aspect_widget(4),
        required=False,
        help_text=f"Reserva de estoque. JSON: hold_ttl_minutes, safety_margin, check_on_commit, allowed_positions. {_INHERIT}",
    )
    notifications = forms.CharField(
        label="Notificações",
        widget=_aspect_widget(3),
        required=False,
        help_text=f"Por onde avisamos o cliente. JSON: backend, fallback_chain, routing. {_INHERIT}",
    )
    pricing = forms.CharField(
        label="Preços",
        widget=_aspect_widget(2),
        required=False,
        help_text=f'Origem do preço. JSON: policy ("internal" = backend, "external" = marketplace). {_INHERIT}',
    )
    editing = forms.CharField(
        label="Edição de itens",
        widget=_aspect_widget(2),
        required=False,
        help_text=f'Itens podem ser editados? JSON: policy ("open" ou "locked"). {_INHERIT}',
    )
    rules = forms.CharField(
        label="Regras",
        widget=_aspect_widget(4),
        required=False,
        help_text=f"Quais validações/modificadores de preço ativar. JSON: validators, modifiers, checks. {_INHERIT}",
    )

    class Meta:
        model = Channel
        fields = ("ref", "name", "shop", "display_order", "is_active")

    _ASPECTS = (
        "confirmation", "payment", "fulfillment", "stock",
        "notifications", "pricing", "editing", "rules",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            data = self.instance.config or {}
            for aspect in self._ASPECTS:
                value = data.get(aspect, {})
                self.fields[aspect].initial = json.dumps(value, indent=2, ensure_ascii=False) if value else ""

    def clean(self):
        cleaned = super().clean()
        config = {}
        for aspect in self._ASPECTS:
            raw = cleaned.get(aspect, "").strip()
            if not raw:
                cleaned[aspect] = {}
                continue
            try:
                cleaned[aspect] = json.loads(raw)
            except json.JSONDecodeError as e:
                self.add_error(aspect, f"JSON inválido: {e}")
                continue
            config[aspect] = cleaned[aspect]
        try:
            resolved = ChannelConfig.from_dict(
                deep_merge(ChannelConfig.defaults(), config)
            )
            resolved.validate()
        except ValueError as e:
            raise ValidationError(f"ChannelConfig inválido: {e}") from e
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        config = instance.config or {}
        for aspect in self._ASPECTS:
            value = self.cleaned_data.get(aspect, {})
            if value:
                config[aspect] = value
            else:
                config.pop(aspect, None)
        instance.config = config
        if commit:
            instance.save()
        return instance


@admin.register(Channel)
class ChannelAdmin(ModelAdmin):
    """Admin para canais de venda com configuração por aspecto."""

    form = ChannelForm
    # Ordem de exibição dos canais = lista arrastável (Unfold).
    ordering_field = "display_order"
    hide_ordering_field = True
    list_display = ("ref", "name", "status_badge")
    list_filter = ("is_active",)
    search_fields = ("ref", "name")
    ordering = ("display_order", "ref")

    @display(description="situação", label={"Ativo": "success", "Inativo": "warning"})
    def status_badge(self, obj):
        return "Ativo" if obj.is_active else "Inativo"

    fieldsets = (
        (None, {
            "fields": ("ref", "name", "shop", "display_order", "is_active"),
            "description": (
                "Os aspectos nas abas abaixo são overrides avançados deste canal. "
                "Deixe um aspecto vazio para herdar a Configuração da Loja — a aba "
                "“Config resolvida” mostra o resultado final da cascata."
            ),
        }),
        ("Confirmação", {"fields": ("confirmation",), "classes": ("tab",)}),
        ("Pagamento", {"fields": ("payment",), "classes": ("tab",)}),
        ("Preparo e entrega", {"fields": ("fulfillment",), "classes": ("tab",)}),
        ("Estoque", {"fields": ("stock",), "classes": ("tab",)}),
        ("Notificações", {"fields": ("notifications",), "classes": ("tab",)}),
        ("Preços", {"fields": ("pricing",), "classes": ("tab",)}),
        ("Edição de itens", {"fields": ("editing",), "classes": ("tab",)}),
        ("Regras", {"fields": ("rules",), "classes": ("tab",)}),
        ("Config resolvida", {"fields": ("resolved_config_display",), "classes": ("tab",)}),
    )
    readonly_fields = ("resolved_config_display",)

    @admin.display(description="Config resolvida (cascata)")
    def resolved_config_display(self, obj):
        if not obj.pk:
            return "-"
        try:
            config = ChannelConfig.for_channel(obj)
            data = config.to_dict()
            formatted = json.dumps(data, indent=2, ensure_ascii=False)
            # format_html escapa o JSON (evita injeção de HTML); classes do Unfold,
            # sem style inline — mesmo padrão do bloco JSON do SessionAdmin.
            return format_html(
                '<pre class="bg-base-50 border border-base-200 dark:bg-base-800 '
                'dark:border-base-700 font-mono overflow-x-auto p-3 rounded-default '
                'text-sm">{}</pre>',
                formatted,
            )
        except Exception:
            logger.debug("channel.resolved_config_display degraded; using fallback", exc_info=True)
            return "-"
