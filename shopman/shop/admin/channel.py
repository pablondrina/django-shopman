"""ChannelAdmin — Canal de venda com configuração integrada."""

from __future__ import annotations

import json
import logging

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from unfold.admin import ModelAdmin
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
        widget=_aspect_widget(4),
        required=False,
        help_text=f"Como o pedido é aceito. JSON: mode (immediate/auto_confirm/auto_cancel/manual), timeout_minutes. {_INHERIT}",
    )
    payment = forms.CharField(
        widget=_aspect_widget(5),
        required=False,
        help_text=f"Como e quando o cliente paga. JSON: method, timing, timeout_minutes. {_INHERIT}",
    )
    fulfillment = forms.CharField(
        widget=_aspect_widget(3),
        required=False,
        help_text=f"Quando preparar/despachar. JSON: timing, auto_sync. {_INHERIT}",
    )
    stock = forms.CharField(
        widget=_aspect_widget(4),
        required=False,
        help_text=f"Reserva de estoque. JSON: hold_ttl_minutes, safety_margin, check_on_commit, allowed_positions. {_INHERIT}",
    )
    notifications = forms.CharField(
        widget=_aspect_widget(3),
        required=False,
        help_text=f"Por onde avisamos o cliente. JSON: backend, fallback_chain, routing. {_INHERIT}",
    )
    pricing = forms.CharField(
        widget=_aspect_widget(2),
        required=False,
        help_text=f'Origem do preço. JSON: policy ("internal" = backend, "external" = marketplace). {_INHERIT}',
    )
    editing = forms.CharField(
        widget=_aspect_widget(2),
        required=False,
        help_text=f'Itens podem ser editados? JSON: policy ("open" ou "locked"). {_INHERIT}',
    )
    rules = forms.CharField(
        widget=_aspect_widget(4),
        required=False,
        help_text=f"Quais validators/modifiers ativar. JSON: validators, modifiers, checks. {_INHERIT}",
    )

    # ── Superfície: capacidade + fonte de conteúdo (primitivo SUPERFÍCIE) ──
    capability = forms.ChoiceField(
        choices=[
            ("transactional", "Transacional (aceita pedido)"),
            ("display", "Display (só exibe — menuboard)"),
            ("feed", "Feed (anúncio — Google/Meta)"),
        ],
        required=False,
        initial="transactional",
        help_text="O que esta superfície faz com o catálogo.",
    )
    content_collection = forms.ChoiceField(
        required=False,
        help_text=(
            "Coleção-fonte: o que aparece nesta superfície. Vazio = usa os ListingItems "
            "explícitos deste canal. Menuboard e Feed exigem uma coleção."
        ),
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
        # Dropdown de coleções (mais amigável que digitar o ref). Populado no init
        # p/ evitar acesso ao DB em tempo de import.
        self.fields["content_collection"].choices = self._collection_choices()
        if self.instance and self.instance.pk:
            data = self.instance.config or {}
            for aspect in self._ASPECTS:
                value = data.get(aspect, {})
                self.fields[aspect].initial = json.dumps(value, indent=2, ensure_ascii=False) if value else ""
            self.fields["capability"].initial = data.get("capability", "transactional")
            content = data.get("content", {}) or {}
            self.fields["content_collection"].initial = content.get("collection") or ""

    @staticmethod
    def _collection_choices():
        choices = [("", "— sem coleção (ListingItems explícitos) —")]
        try:
            from shopman.offerman.models import Collection

            choices += [
                (c.ref, f"{c.name} ({c.ref})")
                for c in Collection.objects.filter(is_active=True).order_by("sort_order", "name")
            ]
        except Exception:
            logger.debug("channel_form.collection_choices_failed", exc_info=True)
        return choices

    def _surface_config(self, source: dict) -> dict:
        """Monta os aspectos de superfície. ``source`` é inferido: coleção → collection."""
        capability = source.get("capability") or "transactional"
        coll = (source.get("content_collection") or "").strip()
        content = {"source": "collection", "collection": coll} if coll else {"source": "listing"}
        return {"capability": capability, "content": content}

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
        config.update(self._surface_config(cleaned))
        # Menuboard (display) e Feed (feed) precisam de uma coleção-fonte.
        if cleaned.get("capability") in ("display", "feed") and not (cleaned.get("content_collection") or "").strip():
            self.add_error("content_collection", "Menuboard/Feed exige uma coleção-fonte.")
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
        config.update(self._surface_config(self.cleaned_data))
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
    list_display = ("ref", "name", "capability_badge", "is_active")
    list_filter = ("is_active",)
    search_fields = ("ref", "name")
    ordering = ("display_order", "ref")
    actions = ("inject_simulated_ifood_order",)

    @admin.display(description="Capacidade")
    def capability_badge(self, obj):
        cap = ChannelConfig.for_channel(obj).capability
        labels = {"transactional": "Transacional", "display": "📺 Display", "feed": "🛰 Feed"}
        return labels.get(cap, cap)

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
        ("Fulfillment", {"fields": ("fulfillment",), "classes": ("tab",)}),
        ("Estoque", {"fields": ("stock",), "classes": ("tab",)}),
        ("Notificações", {"fields": ("notifications",), "classes": ("tab",)}),
        ("Pricing", {"fields": ("pricing",), "classes": ("tab",)}),
        ("Editing", {"fields": ("editing",), "classes": ("tab",)}),
        ("Regras", {"fields": ("rules",), "classes": ("tab",)}),
        ("Superfície", {
            "fields": ("capability", "content_collection", "surface_links"),
            "classes": ("tab",),
            "description": (
                "Generaliza o canal para o primitivo Superfície. Escolha a capacidade e a "
                "coleção-fonte — Display vira um 📺 menuboard, Feed vira um 🛰 feed Google/Meta. "
                "Os links abaixo abrem/apontam a superfície pronta."
            ),
        }),
        ("Config resolvida", {"fields": ("resolved_config_display",), "classes": ("tab",)}),
    )
    readonly_fields = ("resolved_config_display", "surface_links")

    @admin.display(description="Superfície pronta")
    def surface_links(self, obj):
        if not obj or not obj.pk:
            return "Salve o canal para ver os links."
        cap = ChannelConfig.for_channel(obj).capability
        if cap == "display":
            return format_html(
                'Menuboard: <a class="text-primary-600 underline" href="/menuboard/{}/" target="_blank">'
                '/menuboard/{}/</a>',
                obj.ref, obj.ref,
            )
        if cap == "feed":
            return format_html(
                'Feed Google: <a class="text-primary-600 underline" href="/feed/{}.xml" target="_blank">'
                '/feed/{}.xml</a><br>Feed Meta: <a class="text-primary-600 underline" '
                'href="/feed/{}.xml?platform=meta" target="_blank">/feed/{}.xml?platform=meta</a>',
                obj.ref, obj.ref, obj.ref, obj.ref,
            )
        return "Superfície transacional (sem link de display/feed)."

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
