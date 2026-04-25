"""ChannelAdmin — Canal de venda com configuração integrada."""

from __future__ import annotations

import json

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin

from shopman.shop.config import ChannelConfig, deep_merge
from shopman.shop.models import Channel


class ChannelForm(forms.ModelForm):
    """Form com campos de config por aspecto."""

    confirmation = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "class": "vLargeTextField"}),
        required=False,
        help_text="JSON: mode (immediate/auto_confirm/auto_cancel/manual), timeout_minutes",
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
    list_display = ("ref", "name", "is_active", "display_order")
    list_filter = ("is_active",)
    search_fields = ("ref", "name")
    ordering = ("display_order", "ref")
    actions = ("inject_simulated_ifood_order",)

    @admin.action(description="Injetar pedido iFood simulado (DEV)")
    def inject_simulated_ifood_order(self, request, queryset):
        """Dev-only: build a minimal iFood payload and ingest it through the
        canonical entry point. Uses the first real Offerman product as the line
        item so the order clears stock/pricing checks end-to-end. Silently no-ops
        on non-iFood channels in the selection.
        """
        if not settings.DEBUG:
            self.message_user(
                request,
                "Ação disponível apenas com DEBUG=True.",
                level=messages.ERROR,
            )
            return

        from uuid import uuid4

        from django.utils import timezone
        from shopman.offerman.models import Product

        from shopman.shop.services import ifood_ingest

        product = (
            Product.objects.filter(is_published=True, is_sellable=True)
            .exclude(base_price_q=0)
            .first()
        )
        if product is None:
            self.message_user(
                request,
                "Nenhum produto ativo com preço — rode o seed antes.",
                level=messages.ERROR,
            )
            return

        ifood_channels = [c for c in queryset if c.ref == ifood_ingest.IFOOD_CHANNEL_REF]
        if not ifood_channels:
            self.message_user(
                request,
                f"Selecione o canal '{ifood_ingest.IFOOD_CHANNEL_REF}'.",
                level=messages.WARNING,
            )
            return

        created_refs: list[str] = []
        for channel in ifood_channels:
            order_code = f"IFOOD-ADMIN-{uuid4().hex[:8].upper()}"
            payload = {
                "order_code": order_code,
                "merchant_id": "mock-merchant",
                "created_at": timezone.now().isoformat(),
                "customer": {
                    "name": "Cliente iFood Simulado (Admin)",
                    "phone": "",
                },
                "delivery": {
                    "type": "DELIVERY",
                    "address": "Rua Simulada, 123 — Bairro iFood",
                },
                "items": [
                    {
                        "sku": product.sku,
                        "name": product.name,
                        "qty": 1,
                        "unit_price_q": product.base_price_q,
                    },
                ],
                "notes": "[SIMULAÇÃO] Pedido injetado via admin action",
            }
            try:
                order = ifood_ingest.ingest(payload, channel_ref=channel.ref)
                created_refs.append(order.ref)
            except ifood_ingest.IFoodIngestError as e:
                self.message_user(
                    request,
                    f"Falha ao injetar em {channel.ref}: {e.message}",
                    level=messages.ERROR,
                )

        if created_refs:
            self.message_user(
                request,
                f"Pedidos iFood simulados criados: {', '.join(created_refs)}.",
                level=messages.SUCCESS,
            )

    fieldsets = (
        (None, {"fields": ("ref", "name", "shop", "display_order", "is_active")}),
        ("Confirmação", {"fields": ("confirmation",), "classes": ("tab",)}),
        ("Pagamento", {"fields": ("payment",), "classes": ("tab",)}),
        ("Fulfillment", {"fields": ("fulfillment",), "classes": ("tab",)}),
        ("Estoque", {"fields": ("stock",), "classes": ("tab",)}),
        ("Notificações", {"fields": ("notifications",), "classes": ("tab",)}),
        ("Pricing", {"fields": ("pricing",), "classes": ("tab",)}),
        ("Editing", {"fields": ("editing",), "classes": ("tab",)}),
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
            return mark_safe(f"<pre>{formatted}</pre>")
        except Exception:
            return "-"
