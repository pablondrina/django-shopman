from __future__ import annotations

from django.contrib import admin
from django.urls import path
from django.utils import timezone
from unfold.admin import ModelAdmin

from django import forms
from unfold.widgets import UnfoldAdminColorInputWidget

from .models import Coupon, DayClosing, KDSInstance, OperatorAlert, Promotion, Shop
from .widgets import FontPreviewWidget


class ShopForm(forms.ModelForm):
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


@admin.register(Shop)
class ShopAdmin(ModelAdmin):
    form = ShopForm

    def get_urls(self):
        from shop.views.closing import closing_view
        from shop.views.production import production_view, production_void_view

        urls = super().get_urls()
        custom = [
            path(
                "production/",
                self.admin_site.admin_view(
                    lambda request: production_view(request, self.admin_site)
                ),
                name="shop_production",
            ),
            path(
                "production/void/",
                self.admin_site.admin_view(
                    lambda request: production_void_view(request, self.admin_site)
                ),
                name="shop_production_void",
            ),
            path(
                "closing/",
                self.admin_site.admin_view(
                    lambda request: closing_view(request, self.admin_site)
                ),
                name="shop_closing",
            ),
        ]
        return custom + urls

    fieldsets = (
        ("Identidade", {
            "fields": ("name", "legal_name", "document"),
        }),
        ("Endereço", {
            "fields": ("formatted_address", "route", "street_number", "complement",
                       "neighborhood", "city", "state_code", "postal_code",
                       "country", "country_code", "latitude", "longitude", "place_id"),
            "description": "Endereço no padrão Google Places. Preencha 'endereço completo' OU os campos individuais.",
        }),
        ("Contato", {
            "fields": ("phone", "email", "default_ddd"),
        }),
        ("Operação", {
            "fields": ("currency", "timezone", "opening_hours"),
        }),
        ("Branding", {
            "fields": ("brand_name", "short_name", "tagline", "description", "logo"),
        }),
        ("Paleta de Cores", {
            "fields": ("primary_color", "secondary_color", "accent_color", "neutral_color", "neutral_dark_color", "color_mode"),
            "description": (
                "Cores derivadas automaticamente da primária se deixadas em branco. "
                "Neutra claro: fundo da página no modo claro (cards e campos clareiam para branco). "
                "Neutra escuro: fundo no modo escuro (cards e campos escurecem para preto). "
                "Use 'Automático' para respeitar preferência claro/escuro do sistema do usuário."
            ),
        }),
        ("Tipografia & Forma", {
            "fields": ("heading_font", "body_font", "border_radius"),
        }),
        ("Redes Sociais", {
            "fields": ("social_links",),
            "description": "Cole as URLs completas das redes sociais. Ícones são detectados automaticamente.",
        }),
        ("Defaults de Negócio", {
            "fields": ("defaults",),
            "classes": ("collapse",),
        }),
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


class CouponInline(admin.TabularInline):
    model = Coupon
    extra = 1
    fields = ("code", "max_uses", "uses_count", "is_active")
    readonly_fields = ("uses_count",)


# ── Promotion status filter ──────────────────────────────────────────


class PromotionStatusFilter(admin.SimpleListFilter):
    title = "situação"
    parameter_name = "situacao"

    def lookups(self, request, model_admin):
        return [
            ("ativa", "Ativa agora"),
            ("futura", "Futura"),
            ("expirada", "Expirada"),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == "ativa":
            return queryset.filter(is_active=True, valid_from__lte=now, valid_until__gte=now)
        if self.value() == "futura":
            return queryset.filter(is_active=True, valid_from__gt=now)
        if self.value() == "expirada":
            return queryset.filter(valid_until__lt=now)
        return queryset


@admin.register(Promotion)
class PromotionAdmin(ModelAdmin):
    list_display = (
        "name", "type", "value_display", "valid_from", "valid_until",
        "is_active", "status_display",
    )
    list_filter = (PromotionStatusFilter, "is_active", "type")
    search_fields = ("name",)
    inlines = [CouponInline]

    @admin.display(description="desconto", ordering="value")
    def value_display(self, obj):
        if obj.type == Promotion.PERCENT:
            return f"{obj.value}%"
        return f"R$ {obj.value / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @admin.display(description="situação", boolean=True)
    def status_display(self, obj):
        now = timezone.now()
        if not obj.is_active:
            return False
        return obj.valid_from <= now <= obj.valid_until


@admin.register(Coupon)
class CouponAdmin(ModelAdmin):
    list_display = (
        "code", "promotion", "usage_display", "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "promotion__name")
    readonly_fields = ("uses_count",)

    @admin.display(description="uso")
    def usage_display(self, obj):
        if obj.max_uses == 0:
            return f"{obj.uses_count} (ilimitado)"
        return f"{obj.uses_count}/{obj.max_uses}"


# ── DayClosing admin ──────────────────────────────────────────────────


@admin.register(DayClosing)
class DayClosingAdmin(ModelAdmin):
    list_display = ("date", "closed_by", "closed_at")
    list_filter = ("date",)
    readonly_fields = ("date", "closed_by", "closed_at", "notes", "data")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OperatorAlert)
class OperatorAlertAdmin(ModelAdmin):
    list_display = ("type", "severity", "short_message", "order_ref", "acknowledged", "created_at")
    list_filter = ("type", "severity", "acknowledged")
    search_fields = ("message", "order_ref")
    readonly_fields = ("type", "severity", "message", "order_ref", "created_at")
    list_per_page = 50
    ordering = ("-created_at",)
    actions = ["mark_acknowledged"]

    @admin.display(description="mensagem")
    def short_message(self, obj):
        return obj.message[:80] + "…" if len(obj.message) > 80 else obj.message

    @admin.action(description="Marcar como reconhecido")
    def mark_acknowledged(self, request, queryset):
        updated = queryset.filter(acknowledged=False).update(acknowledged=True)
        self.message_user(request, f"{updated} alerta(s) reconhecido(s).")


# ── Product admin: add allows_next_day_sale checkbox ──────────────────


def _extend_product_admin():
    """Add allows_next_day_sale checkbox to the offering ProductAdmin."""
    from shopman.offering.models import Product

    try:
        ProductAdminClass = type(admin.site._registry[Product])
    except KeyError:
        return

    # Add allows_next_day_sale as a boolean field rendered via custom form
    original_get_form = ProductAdminClass.get_form

    def get_form(self, request, obj=None, **kwargs):
        form = original_get_form(request, obj, **kwargs)

        class ExtendedForm(form):
            allows_next_day_sale = __import__("django.forms", fromlist=["BooleanField"]).BooleanField(
                label="Permite venda D-1",
                required=False,
                help_text="Produto pode ser vendido no dia seguinte com desconto D-1.",
            )

            def __init__(inner_self, *args, **inner_kwargs):
                super().__init__(*args, **inner_kwargs)
                if inner_self.instance and inner_self.instance.pk:
                    inner_self.fields["allows_next_day_sale"].initial = (
                        inner_self.instance.metadata.get("allows_next_day_sale", False)
                    )

        return ExtendedForm

    def save_model(self, request, obj, form, change):
        obj.metadata["allows_next_day_sale"] = form.cleaned_data.get("allows_next_day_sale", False)
        obj.save()

    ProductAdminClass.get_form = get_form
    ProductAdminClass.save_model = save_model

    # Add allows_next_day_sale to the Configuration fieldset
    fieldsets = list(ProductAdminClass.fieldsets or [])
    for i, (title, opts) in enumerate(fieldsets):
        if title == "Configuration":
            fields = list(opts["fields"])
            if "allows_next_day_sale" not in fields:
                fields.append("allows_next_day_sale")
                fieldsets[i] = (title, {**opts, "fields": tuple(fields)})
            break
    ProductAdminClass.fieldsets = fieldsets


_extend_product_admin()


# ── Order admin: add Fulfillment + Payment inlines ────────────────────


class FulfillmentOrderInline(admin.TabularInline):
    model = None  # set dynamically below
    extra = 0
    fields = ("status", "carrier", "tracking_code", "dispatched_at", "delivered_at")
    readonly_fields = ("status", "carrier", "tracking_code", "dispatched_at", "delivered_at")
    can_delete = False
    verbose_name = "fulfillment"
    verbose_name_plural = "fulfillments"

    def has_add_permission(self, request, obj=None):
        return False


def _payment_info(self, obj):
    """Show PaymentIntent info linked via order_ref."""
    from django.utils.html import format_html, format_html_join
    from shopman.payments.models import PaymentIntent

    intents = PaymentIntent.objects.filter(order_ref=obj.ref).order_by("-created_at")
    if not intents.exists():
        return "—"

    rows = format_html_join(
        "",
        '<tr><td style="padding:2px 8px">{}</td>'
        '<td style="padding:2px 8px">{}</td>'
        '<td style="padding:2px 8px">{}</td>'
        '<td style="padding:2px 8px">R$ {}</td></tr>',
        (
            (
                pi.ref,
                pi.get_method_display(),
                pi.get_status_display(),
                f"{pi.amount_q / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            )
            for pi in intents
        ),
    )
    return format_html(
        '<table style="border-collapse:collapse">'
        "<thead><tr>"
        '<th style="padding:2px 8px;text-align:left">Ref</th>'
        '<th style="padding:2px 8px;text-align:left">Método</th>'
        '<th style="padding:2px 8px;text-align:left">Status</th>'
        '<th style="padding:2px 8px;text-align:left">Valor</th>'
        "</tr></thead><tbody>{}</tbody></table>",
        rows,
    )


_payment_info.short_description = "Pagamentos"


def _extend_order_admin():
    """Add Fulfillment inline and payment info to OrderAdmin."""
    from shopman.ordering.models import Fulfillment, Order

    FulfillmentOrderInline.model = Fulfillment

    try:
        OrderAdminClass = type(admin.site._registry[Order])
    except KeyError:
        return

    # Add Fulfillment inline
    existing_inlines = list(OrderAdminClass.inlines or [])
    if FulfillmentOrderInline not in existing_inlines:
        existing_inlines.append(FulfillmentOrderInline)
        OrderAdminClass.inlines = existing_inlines

    # Add payment_info readonly field
    OrderAdminClass.payment_info = _payment_info
    existing_readonly = list(OrderAdminClass.readonly_fields or [])
    if "payment_info" not in existing_readonly:
        existing_readonly.append("payment_info")
        OrderAdminClass.readonly_fields = tuple(existing_readonly)

    # Add payment_info to fieldsets (append as new tab)
    existing_fieldsets = list(OrderAdminClass.fieldsets or [])
    payment_fieldset = ("Pagamentos", {"fields": ("payment_info",), "classes": ("tab",)})
    fieldset_names = [fs[0] for fs in existing_fieldsets]
    if "Pagamentos" not in fieldset_names:
        existing_fieldsets.append(payment_fieldset)
        OrderAdminClass.fieldsets = existing_fieldsets


_extend_order_admin()


# ── Batch admin: add supplier filter + expiry status ─────────────────


class SupplierFilter(admin.SimpleListFilter):
    title = "fornecedor"
    parameter_name = "supplier"

    def lookups(self, request, model_admin):
        from shopman.stocking.models import Batch

        suppliers = (
            Batch.objects.exclude(supplier="")
            .values_list("supplier", flat=True)
            .distinct()
            .order_by("supplier")
        )
        return [(s, s) for s in suppliers]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(supplier=self.value())
        return queryset


class ExpiryStatusFilter(admin.SimpleListFilter):
    title = "validade"
    parameter_name = "expiry_status"

    def lookups(self, request, model_admin):
        return [
            ("expired", "Expirado"),
            ("valid", "Válido"),
            ("no_expiry", "Sem validade"),
        ]

    def queryset(self, request, queryset):
        from datetime import date

        today = date.today()
        if self.value() == "expired":
            return queryset.filter(expiry_date__lt=today)
        if self.value() == "valid":
            return queryset.filter(expiry_date__gte=today)
        if self.value() == "no_expiry":
            return queryset.filter(expiry_date__isnull=True)
        return queryset


def _extend_batch_admin():
    """Add supplier and expiry status filters to BatchAdmin."""
    from shopman.stocking.models import Batch

    try:
        BatchAdminClass = type(admin.site._registry[Batch])
    except KeyError:
        return

    existing_filters = list(BatchAdminClass.list_filter or [])
    if SupplierFilter not in existing_filters:
        existing_filters.append(SupplierFilter)
    if ExpiryStatusFilter not in existing_filters:
        existing_filters.append(ExpiryStatusFilter)
    BatchAdminClass.list_filter = existing_filters


_extend_batch_admin()


# ── Quant admin: add batch link ──────────────────────────────────────


def _extend_quant_admin():
    """Add batch link to QuantAdmin for traceability."""
    from shopman.stocking.models import Quant

    try:
        QuantAdminClass = type(admin.site._registry[Quant])
    except KeyError:
        return

    def batch_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        from shopman.stocking.models import Batch

        if not obj.batch:
            return "—"
        batch = Batch.objects.filter(ref=obj.batch).first()
        if batch:
            url = reverse("admin:stocking_batch_change", args=[batch.pk])
            return format_html('<a href="{}">{}</a>', url, obj.batch)
        return obj.batch

    batch_link.short_description = "Lote"

    QuantAdminClass.batch_link = batch_link

    existing_display = list(QuantAdminClass.list_display or [])
    # Replace batch_display with batch_link if exists, otherwise append
    if "batch_display" in existing_display:
        idx = existing_display.index("batch_display")
        existing_display[idx] = "batch_link"
    elif "batch_link" not in existing_display:
        existing_display.append("batch_link")
    QuantAdminClass.list_display = existing_display


_extend_quant_admin()


# ── KDS Instance admin ──────────────────────────────────────────────


@admin.register(KDSInstance)
class KDSInstanceAdmin(ModelAdmin):
    list_display = ["name", "ref", "type", "target_time_minutes", "sound_enabled", "is_active"]
    list_filter = ["type", "is_active"]
    search_fields = ["name", "ref"]
    prepopulated_fields = {"ref": ("name",)}
    filter_horizontal = ["collections"]
    fieldsets = [
        (None, {"fields": ("name", "ref", "type")}),
        ("Coleções", {
            "fields": ("collections",),
            "description": "Categorias de produto que esta estação processa. Vazio = catch-all.",
        }),
        ("Configuração", {"fields": ("target_time_minutes", "sound_enabled", "is_active", "config")}),
    ]
