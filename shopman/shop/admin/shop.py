"""Shop admin — singleton with branding, colors, typography."""

from __future__ import annotations

import json
from datetime import time

from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin
from unfold.widgets import UnfoldAdminColorInputWidget, UnfoldAdminSelectWidget, UnfoldAdminTimeWidget

from shopman.shop.admin.widgets import FontPreviewWidget
from shopman.shop.colors import oklch_to_hex
from shopman.shop.models import NotificationTemplate, Shop


OPENING_HOUR_DAYS = (
    ("monday", "Segunda"),
    ("tuesday", "Terça"),
    ("wednesday", "Quarta"),
    ("thursday", "Quinta"),
    ("friday", "Sexta"),
    ("saturday", "Sábado"),
    ("sunday", "Domingo"),
)

OPENING_STATUS_CHOICES = (
    ("open", "Aberto"),
    ("closed", "Fechado"),
)


def _opening_field(day: str, suffix: str) -> str:
    return f"opening_hours_{day}_{suffix}"


def _format_admin_time(value) -> str:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    raw = str(value or "").strip()
    if not raw:
        return ""
    return raw[:5]


class ShopForm(forms.ModelForm):
    opening_hours_monday_status = forms.ChoiceField(
        label="Segunda",
        choices=OPENING_STATUS_CHOICES,
        widget=UnfoldAdminSelectWidget,
    )
    opening_hours_monday_open = forms.TimeField(
        label="Abre",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_monday_close = forms.TimeField(
        label="Fecha",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_tuesday_status = forms.ChoiceField(
        label="Terça",
        choices=OPENING_STATUS_CHOICES,
        widget=UnfoldAdminSelectWidget,
    )
    opening_hours_tuesday_open = forms.TimeField(
        label="Abre",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_tuesday_close = forms.TimeField(
        label="Fecha",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_wednesday_status = forms.ChoiceField(
        label="Quarta",
        choices=OPENING_STATUS_CHOICES,
        widget=UnfoldAdminSelectWidget,
    )
    opening_hours_wednesday_open = forms.TimeField(
        label="Abre",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_wednesday_close = forms.TimeField(
        label="Fecha",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_thursday_status = forms.ChoiceField(
        label="Quinta",
        choices=OPENING_STATUS_CHOICES,
        widget=UnfoldAdminSelectWidget,
    )
    opening_hours_thursday_open = forms.TimeField(
        label="Abre",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_thursday_close = forms.TimeField(
        label="Fecha",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_friday_status = forms.ChoiceField(
        label="Sexta",
        choices=OPENING_STATUS_CHOICES,
        widget=UnfoldAdminSelectWidget,
    )
    opening_hours_friday_open = forms.TimeField(
        label="Abre",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_friday_close = forms.TimeField(
        label="Fecha",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_saturday_status = forms.ChoiceField(
        label="Sábado",
        choices=OPENING_STATUS_CHOICES,
        widget=UnfoldAdminSelectWidget,
    )
    opening_hours_saturday_open = forms.TimeField(
        label="Abre",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_saturday_close = forms.TimeField(
        label="Fecha",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_sunday_status = forms.ChoiceField(
        label="Domingo",
        choices=OPENING_STATUS_CHOICES,
        widget=UnfoldAdminSelectWidget,
    )
    opening_hours_sunday_open = forms.TimeField(
        label="Abre",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_sunday_close = forms.TimeField(
        label="Fecha",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )

    class Meta:
        model = Shop
        fields = "__all__"
        widgets = {
            "primary_color": UnfoldAdminColorInputWidget,
            "secondary_color": UnfoldAdminColorInputWidget,
            "accent_color": UnfoldAdminColorInputWidget,
            "neutral_color": UnfoldAdminColorInputWidget,
            "neutral_dark_color": UnfoldAdminColorInputWidget,
            "heading_font": FontPreviewWidget(sample_text="Aa Bb Cc \u2014 O sabor que encanta"),
            "body_font": FontPreviewWidget(sample_text="O p\u00e3o fresco de cada dia, feito com amor e tradi\u00e7\u00e3o."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("opening_hours", None)

        opening_hours = getattr(self.instance, "opening_hours", None) or {}
        if not isinstance(opening_hours, dict):
            opening_hours = {}

        for day, _label in OPENING_HOUR_DAYS:
            entry = opening_hours.get(day) if isinstance(opening_hours.get(day), dict) else {}
            opens_at = _format_admin_time(entry.get("open"))
            closes_at = _format_admin_time(entry.get("close"))
            self.fields[_opening_field(day, "status")].initial = "open" if opens_at and closes_at else "closed"
            self.fields[_opening_field(day, "open")].initial = opens_at
            self.fields[_opening_field(day, "close")].initial = closes_at

    def clean(self):
        cleaned_data = super().clean()
        for day, label in OPENING_HOUR_DAYS:
            status = cleaned_data.get(_opening_field(day, "status"))
            opens_at = cleaned_data.get(_opening_field(day, "open"))
            closes_at = cleaned_data.get(_opening_field(day, "close"))
            if status != "open":
                continue
            if not opens_at or not closes_at:
                raise forms.ValidationError(f"Informe abertura e fechamento para {label}, ou marque como fechado.")
            if opens_at >= closes_at:
                raise forms.ValidationError(f"Em {label}, o horário de abertura precisa ser anterior ao fechamento.")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.opening_hours = {
            day: {
                "open": _format_admin_time(self.cleaned_data.get(_opening_field(day, "open"))),
                "close": _format_admin_time(self.cleaned_data.get(_opening_field(day, "close"))),
            }
            for day, _label in OPENING_HOUR_DAYS
            if self.cleaned_data.get(_opening_field(day, "status")) == "open"
        }
        if commit:
            instance.save()
            self.save_m2m()
        return instance


def _oklch_raw_to_hex(raw: str) -> str:
    """Convert OKLCH raw string '0.550 0.150 85.0' to hex color."""
    parts = raw.split()
    if len(parts) == 3:
        return oklch_to_hex(float(parts[0]), float(parts[1]), float(parts[2]))
    return "#888888"


def _token_value_to_hex(val: str) -> str:
    """design_tokens: 'R G B' (0–255) ou legado OKLCH tripla → hex."""
    parts = val.split()
    if len(parts) == 3:
        try:
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
            if 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255:
                return f"#{r:02x}{g:02x}{b:02x}"
        except ValueError:
            pass
        if "." in parts[0]:
            return _oklch_raw_to_hex(val)
    return "#888888"


@admin.register(Shop)
class ShopAdmin(ModelAdmin):
    form = ShopForm
    readonly_fields = ("color_preview", "storefront_preview")

    fieldsets = (
        ("Identidade", {
            "fields": ("name", "legal_name", "document"),
        }),
        ("Endereço", {
            "fields": (
                "formatted_address", "route", "street_number", "complement",
                "neighborhood", "city", "state_code", "postal_code",
                "country", "country_code", "latitude", "longitude", "place_id",
            ),
            "description": "Endereço no padrão Google Places. Preencha 'endereço completo' OU os campos individuais.",
        }),
        ("Contato", {
            "fields": ("phone", "email", "default_ddd"),
        }),
        ("Operação", {
            "fields": (
                "currency",
                "timezone",
                ("opening_hours_monday_status", "opening_hours_monday_open", "opening_hours_monday_close"),
                ("opening_hours_tuesday_status", "opening_hours_tuesday_open", "opening_hours_tuesday_close"),
                ("opening_hours_wednesday_status", "opening_hours_wednesday_open", "opening_hours_wednesday_close"),
                ("opening_hours_thursday_status", "opening_hours_thursday_open", "opening_hours_thursday_close"),
                ("opening_hours_friday_status", "opening_hours_friday_open", "opening_hours_friday_close"),
                ("opening_hours_saturday_status", "opening_hours_saturday_open", "opening_hours_saturday_close"),
                ("opening_hours_sunday_status", "opening_hours_sunday_open", "opening_hours_sunday_close"),
            ),
            "description": "Horários gravados em Shop.opening_hours, editados aqui como campos por dia.",
        }),
        ("Branding", {
            "fields": ("brand_name", "short_name", "tagline", "description", "logo"),
        }),
        ("Conteúdo padrão do PDP", {
            "fields": ("conservation_tips_default", "food_safety_notice"),
            "description": (
                "Texto exibido na seção de conservação do PDP quando o produto "
                "não tiver dica específica. O aviso de produção compartilhada "
                "aparece na seção de ingredientes."
            ),
        }),
        ("Paleta de Cores", {
            "fields": (
                "primary_color", "secondary_color", "accent_color",
                "neutral_color", "neutral_dark_color", "color_mode",
                "color_preview",
            ),
            "description": (
                "Seletor de cor (Unfold) para primária, secundária, destaque e neutros. "
                "Cores derivadas automaticamente da primária se deixadas em branco. "
                "Neutra claro: fundo no modo claro; neutra escuro: fundo no modo escuro. "
                "Use 'Automático' para seguir o tema do sistema. "
                "Abaixo, preview da paleta gerada (claro + escuro)."
            ),
        }),
        ("Tipografia & Forma", {
            "fields": ("heading_font", "body_font", "border_radius"),
            "description": (
                "Fontes com preview ao vivo (Google Fonts). Raio dos cantos aplica-se a cards e botões."
            ),
        }),
        ("Preview do storefront (WP-S4)", {
            "fields": ("storefront_preview",),
            "description": (
                "Página inicial em iframe (mesma origem). Salve o formulário e clique em "
                "<strong>Atualizar preview</strong> para ver cores e tipografia sem sair do admin."
            ),
        }),
        ("Redes Sociais", {
            "fields": ("social_links",),
            "description": "Cole as URLs completas das redes sociais. Ícones são detectados automaticamente.",
        }),
        ("Defaults de Negócio", {
            "fields": ("defaults",),
            "classes": ("collapse",),
        }),
        ("Integrações", {
            "fields": ("integrations",),
            "classes": ("collapse",),
            "description": (
                "Seleção de adapters Admin-configurável. Sobreescreve settings.py. "
                "Exemplo: {\"payment\": {\"pix\": \"shopman.shop.adapters.payment_efi\"}}."
            ),
        }),
    )

    @admin.display(description="Preview da paleta (Oxbow → RGB)")
    def color_preview(self, obj):
        """Swatches dos tokens (canais RGB no storefront)."""
        if not obj or not obj.pk:
            return "Salve a loja para ver a paleta."

        tokens = obj.design_tokens
        dark = tokens.get("dark", {})

        # Token groups to preview
        groups = [
            ("Primária", [
                ("primary", "Primary"),
                ("primary_hover", "Hover"),
                ("secondary", "Secondary"),
                ("accent", "Accent"),
            ]),
            ("Superfícies", [
                ("background", "Background"),
                ("surface", "Surface"),
                ("muted", "Muted"),
                ("border", "Border"),
            ]),
            ("Texto", [
                ("foreground", "Foreground"),
                ("foreground_muted", "Muted"),
            ]),
            ("Status", [
                ("success", "Success"),
                ("warning", "Warning"),
                ("error", "Error"),
                ("info", "Info"),
            ]),
        ]

        html_parts = ['<div style="display:flex;flex-direction:column;gap:12px;margin-top:4px">']

        for group_label, items in groups:
            html_parts.append(
                f'<div><strong style="font-size:11px;text-transform:uppercase;'
                f'letter-spacing:0.05em;color:#6b7280">{group_label}</strong>'
                f'<div style="display:flex;gap:6px;margin-top:4px">'
            )
            for token_key, label in items:
                raw = tokens.get(token_key, "128 128 128")
                hex_color = _token_value_to_hex(raw)
                dark_raw = dark.get(token_key, raw)
                dark_hex = _token_value_to_hex(dark_raw)

                html_parts.append(
                    f'<div style="text-align:center">'
                    f'<div style="display:flex;border-radius:6px;overflow:hidden;border:1px solid #e5e7eb">'
                    f'<div style="width:36px;height:36px;background:{hex_color}" title="Light: {hex_color}"></div>'
                    f'<div style="width:36px;height:36px;background:{dark_hex}" title="Dark: {dark_hex}"></div>'
                    f'</div>'
                    f'<div style="font-size:10px;color:#9ca3af;margin-top:2px">{label}</div>'
                    f'</div>'
                )
            html_parts.append('</div></div>')

        html_parts.append('</div>')
        return mark_safe("".join(html_parts))

    @admin.display(description="Preview ao vivo (iframe)")
    def storefront_preview(self, obj):
        """Iframe da home — requer X-Frame-Options: SAMEORIGIN na HomeView."""
        if not obj or not obj.pk:
            return format_html(
                '<p class="help">Salve a loja para carregar o preview do storefront.</p>'
            )

        from django.urls import reverse

        try:
            url = reverse("storefront:home")
        except Exception:
            url = "/"

        url_json = mark_safe(json.dumps(url))
        return format_html(
            '<div class="storefront-admin-preview" style="max-width:100%">'
            '<p style="margin:0 0 8px;font-size:12px;color:#6b7280">'
            "A home pública permite iframe apenas neste site (SAMEORIGIN)."
            "</p>"
            '<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap">'
            '<button type="button" class="button" id="storefront-preview-refresh">'
            "Atualizar preview"
            "</button>"
            "</div>"
            '<iframe id="storefront-preview-iframe" src="{}" title="Storefront" '
            'style="width:100%;min-height:min(70vh,640px);border:1px solid #e5e7eb;'
            'border-radius:8px;background:#fff"></iframe>'
            "<script>"
            "(function(){{"
            'var f=document.getElementById("storefront-preview-iframe");'
            'var b=document.getElementById("storefront-preview-refresh");'
            "var u={};"
            "if(b&&f){{b.addEventListener('click',function(){{"
            'var sep=u.indexOf("?")>=0?"&":"?";'
            'f.src=u+sep+"__pv="+Date.now();'
            "}});}}"
            "}})();"
            "</script>"
            "</div>",
            url,
            url_json,
        )

    def has_add_permission(self, request):
        return not Shop.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = Shop.objects.first()
        if obj:
            return self.changeform_view(request, str(obj.pk), extra_context=extra_context)
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(ModelAdmin):
    list_display = ("event", "subject", "is_active")
    list_filter = ("is_active",)
    search_fields = ("event", "subject", "body")
    list_editable = ("is_active",)
    fields = ("event", "subject", "body", "is_active")
    readonly_fields = ("event",)
