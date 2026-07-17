"""
Offerman Admin with Unfold theme.
"""
from __future__ import annotations

import json
from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from import_export.admin import ExportMixin, ImportExportModelAdmin
from shopman.offerman.contrib.admin_unfold.nutrition_form import (
    MACRONUTRIENTS,
    MICRONUTRIENTS,
    REMOTE_PURCHASE_FORM_FIELDS,
    SERVING_FIELDS,
    ProductAdminForm,
)
from shopman.offerman.models import (
    Collection,
    CollectionItem,
    Listing,
    ListingItem,
    Product,
    ProductComponent,
)
from shopman.utils.admin.mixins import AutofillInlineMixin
from shopman.utils.contrib.admin_unfold.badges import unfold_badge
from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin, BaseTabularInline
from shopman.utils.monetary import format_money
from unfold.contrib.filters.admin.numeric_filters import RangeNumericFilter
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from unfold.decorators import display
from unfold.forms import ActionForm
from unfold.widgets import (
    UnfoldAdminSelectWidget,
    UnfoldAdminTextareaWidget,
    UnfoldAdminTextInputWidget,
)

# Unregister basic admins
for model in [Collection, Listing, Product]:
    try:
        admin.site.unregister(model)
    except admin.sites.NotRegistered:
        pass


# =============================================================================
# COLLECTION ADMIN
# =============================================================================


class CollectionItemInline(BaseTabularInline):
    model = CollectionItem
    extra = 1
    autocomplete_fields = ["product"]
    fields = ["product", "is_primary", "sort_order"]

    ordering_field = "sort_order"
    hide_ordering_field = True


_RULE_HELP = (
    "Coleção automática por regra. Vazio = coleção manual (usa os itens abaixo). "
    'JSON: {"match": "all"|"any", "conditions": [{"field", "op", "value"}]}. '
    "Campos: keyword, sku, name, unit, base_price_q, is_published, is_sellable, collection. "
    "Operadores: eq, ne, lt, lte, gt, gte, in, contains."
)


class CollectionAdminForm(forms.ModelForm):
    """Form com editor JSON validado da regra (smart collection)."""

    rule = forms.CharField(
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 6}),
        required=False,
        help_text=_RULE_HELP,
    )

    class Meta:
        model = Collection
        fields = (
            "ref", "name", "description", "parent",
            "valid_from", "valid_until", "sort_order", "is_active", "rule",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.rule:
            self.fields["rule"].initial = json.dumps(self.instance.rule, indent=2, ensure_ascii=False)

    def clean_rule(self):
        raw = (self.cleaned_data.get("rule") or "").strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValidationError(f"JSON inválido: {e}") from e
        from shopman.offerman.smart_collection import validate_rule

        validate_rule(parsed)  # levanta ValidationError em regra malformada
        return parsed


@admin.register(Collection)
class CollectionAdmin(BaseModelAdmin):
    form = CollectionAdminForm
    # Ordem das coleções = lista arrastável (Unfold). O Unfold reatribui
    # sort_order pela posição (topo→base), por isso a lista ordena ascendente.
    ordering_field = "sort_order"
    hide_ordering_field = True
    list_display = [
        "ref",
        "name",
        "parent",
        "is_active_badge",
        "is_smart_badge",
        "valid_from",
        "valid_until",
        "products_count",
    ]
    list_filter = ["is_active", "parent"]
    search_fields = ["ref", "name"]
    ordering = ["sort_order", "name"]
    prepopulated_fields = {"ref": ("name",)}
    inlines = [CollectionItemInline]

    fieldsets = [
        (None, {"fields": ("ref", "name", "description")}),
        ("Hierarquia", {"fields": ("parent",)}),
        ("Validade", {"fields": ("valid_from", "valid_until")}),
        ("Configurações", {"fields": ("sort_order", "is_active")}),
        ("Regra (coleção automática)", {
            "fields": ("rule",),
            "classes": ("tab",),
            "description": (
                "Preencha para tornar a coleção automática por regra (membros computados dos "
                "atributos do produto). Vazia = coleção manual (itens explícitos)."
            ),
        }),
    ]

    @display(description="Ativo", boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active

    @display(description="Regra", boolean=True)
    def is_smart_badge(self, obj):
        return obj.is_smart

    @display(description="Produtos")
    def products_count(self, obj):
        # smart-aware: regra resolve a membership; manual conta os itens explícitos.
        return obj.product_queryset().count()


# =============================================================================
# LISTING ADMIN
# =============================================================================


class ListingItemInline(AutofillInlineMixin, BaseTabularInline):
    model = ListingItem
    extra = 1
    autocomplete_fields = ["product"]
    autofill_fields = {"product": {"price_q": "base_price_q"}}
    fields = ["product", "price_q", "min_qty", "is_published", "is_sellable"]


class _ListingExportBase(ExportMixin, BaseModelAdmin):
    """Combined base for Listing admin with Unfold styling + export."""
    export_form_class = ExportForm


@admin.register(Listing)
class ListingAdmin(_ListingExportBase):
    from shopman.offerman.contrib.admin_unfold.resources import ListingItemResource

    resource_classes = [ListingItemResource]

    list_display = [
        "ref",
        "name",
        "is_active_badge",
        "valid_from",
        "valid_until",
        "priority",
        "items_count",
    ]
    list_filter = ["is_active"]
    search_fields = ["ref", "name"]
    list_editable = ["priority"]
    ordering = ["-priority", "name"]
    inlines = [ListingItemInline]

    fieldsets = [
        (None, {"fields": ("ref", "name", "description")}),
        ("Validade", {"fields": ("valid_from", "valid_until")}),
        ("Configurações", {"fields": ("priority", "is_active")}),
    ]

    def save_formset(self, request, form, formset, change):
        """Default price_q to product.base_price_q when left blank."""
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, ListingItem) and instance.product_id:
                if instance.price_q is None:
                    instance.price_q = instance.product.base_price_q
            instance.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()

    def get_queryset(self, request):
        # Conta os itens num único JOIN em vez de uma query por linha (N+1).
        from django.db.models import Count

        return super().get_queryset(request).annotate(_items_count=Count("items"))

    @display(description="Ativo", boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active

    @display(description="Itens", ordering="_items_count")
    def items_count(self, obj):
        return getattr(obj, "_items_count", obj.items.count())


# =============================================================================
# PRODUCT ADMIN (with Import/Export, advanced filters, bulk actions)
# =============================================================================


class ProductComponentInline(BaseTabularInline):
    model = ProductComponent
    fk_name = "parent"
    extra = 1
    autocomplete_fields = ["component"]
    # Explícito: o componente e a quantidade no bundle ficam sempre visíveis.
    fields = ["component", "qty"]


class ProductCollectionItemInline(BaseTabularInline):
    """Inline to manage product's collection memberships."""
    model = CollectionItem
    extra = 1
    autocomplete_fields = ["collection"]
    fields = ["collection", "is_primary", "sort_order"]

    ordering_field = "sort_order"
    hide_ordering_field = True


class ProductListingItemInline(BaseTabularInline):
    """Inline to manage product's listing (per-channel pricing/visibility)."""
    model = ListingItem
    extra = 0
    fields = ["listing", "price_q", "is_published", "is_sellable", "min_qty"]
    readonly_fields = ["listing"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class _ProductImportExportBase(ImportExportModelAdmin, BaseModelAdmin):
    """Combined base for Product admin with Unfold styling + import/export."""
    import_form_class = ImportForm
    export_form_class = ExportForm


class ProductActionForm(ActionForm):
    """Campos reais na barra de ações (em vez de POST cru) para as ações que
    pedem um parâmetro: o percentual de reajuste e a coleção de destino."""

    price_percent = forms.CharField(
        required=False,
        label=_("Percentual"),
        help_text=_("Ex.: 10 para +10%, -5 para -5%."),
        widget=UnfoldAdminTextInputWidget,
    )
    collection_id = forms.ModelChoiceField(
        queryset=Collection.objects.filter(is_active=True).order_by("name"),
        required=False,
        label=_("Coleção"),
        widget=UnfoldAdminSelectWidget,
    )


@admin.register(Product)
class ProductAdmin(_ProductImportExportBase):
    from shopman.offerman.contrib.admin_unfold.resources import ProductResource

    form = ProductAdminForm
    resource_classes = [ProductResource]

    autocomplete_extra_fields = ["base_price_q"]
    list_display = [
        "image_thumbnail",
        "sku",
        "name",
        "formatted_price",
        "cost_display",
        "margin_display",
        "visibility_status",
        "is_bundle_display",
        "stock_available_display",
    ]
    list_filter = [
        "is_published",
        "is_sellable",
        "availability_policy",
        ("base_price_q", RangeNumericFilter),
    ]
    list_filter_submit = True
    search_fields = ["sku", "name", "keywords__name"]
    readonly_fields = ["uuid", "created_at", "updated_at", "is_bundle", "margin_percent", "is_perishable"]
    inlines = [ProductCollectionItemInline, ProductListingItemInline, ProductComponentInline]

    fieldsets = [
        (
            None,
            {"fields": ("sku", "name", "short_description", "long_description", "keywords")},
        ),
        (
            "Preço e custo",
            {"fields": ("base_price_q", "margin_percent"), "classes": ("tab",)},
        ),
        (
            "Publicação e venda",
            {
                "fields": ("is_published", "is_sellable"),
                "classes": ("tab",),
                "description": "“Publicado” controla a exposição no catálogo; “vendável” controla se o produto está comercialmente habilitado.",
            },
        ),
        (
            "Configuração",
            {
                "fields": (
                    "unit",
                    "unit_weight_g",
                    "availability_policy",
                    "shelf_life_days",
                    "storage_tip",
                    "is_perishable",
                    "production_cycle_hours",
                    "is_batch_produced",
                    "allows_next_day_sale",
                ),
                "classes": ("tab",),
            },
        ),
        (
            "Ingredientes",
            {
                "fields": ("ingredients_text",),
                "classes": ("tab",),
                "description": (
                    "Lista humana em pt-BR, ordem decrescente de peso "
                    "(ANVISA RDC 360/2003). Pode ser preenchido automaticamente "
                    "a partir da Recipe ativa."
                ),
            },
        ),
        (
            "Compra remota",
            {
                "fields": REMOTE_PURCHASE_FORM_FIELDS,
                "classes": ("tab",),
                "description": (
                    "Dados exibidos na PDP para reduzir dúvida na compra remota: "
                    "alérgenos, restrições, rendimento e medidas aproximadas."
                ),
            },
        ),
        (
            "Informações Nutricionais — Porção",
            {"fields": SERVING_FIELDS, "classes": ("tab",)},
        ),
        (
            "Informações Nutricionais — Macronutrientes",
            {"fields": MACRONUTRIENTS, "classes": ("tab",)},
        ),
        (
            "Informações Nutricionais — Micronutrientes",
            {"fields": MICRONUTRIENTS, "classes": ("tab",)},
        ),
        (
            "Metadados",
            {
                "fields": ("metadata", "nutrition_facts", "uuid", "created_at", "updated_at"),
                "classes": ("tab",),
            },
        ),
    ]

    @display(description="")
    def image_thumbnail(self, obj):
        if obj.image_url:
            return format_html(
                '<img src="{}" alt="{}" class="block h-10 object-cover rounded-default w-10">',
                obj.image_url, obj.name,
            )
        return ""

    @display(description="Preço")
    def formatted_price(self, obj):
        return f"R$ {format_money(obj.base_price_q)}"

    @display(description="Situação")
    def visibility_status(self, obj):
        """Display visibility status with colored badges."""
        badges = []

        if not obj.is_published:
            badges.append(unfold_badge("Não publicado", "yellow"))
        if not obj.is_sellable:
            badges.append(unfold_badge("Não vendável", "red"))

        if not badges:
            return unfold_badge("Ativo", "green")

        return format_html(" ".join(str(b) for b in badges))

    def get_queryset(self, request):
        from django.db.models import Exists, OuterRef
        from shopman.offerman.models import ProductComponent

        return super().get_queryset(request).annotate(
            has_components=Exists(ProductComponent.objects.filter(parent=OuterRef("pk"))),
        )

    @display(description="Combo", boolean=True)
    def is_bundle_display(self, obj):
        if hasattr(obj, "has_components"):
            return obj.has_components
        return obj.is_bundle

    @display(description=_("Custo"))
    def cost_display(self, obj):
        cost_q = obj.reference_cost_q
        if cost_q is None:
            return "—"
        return f"R$ {format_money(cost_q)}"

    @display(description=_("Margem"))
    def margin_display(self, obj):
        margin = obj.margin_percent
        if margin is None:
            return "—"
        from shopman.utils.contrib.admin_unfold.badges import unfold_badge as _badge
        pct = f"{margin:.1f}%"
        if margin >= 50:
            return _badge(pct, "green")
        elif margin >= 20:
            return _badge(pct, "blue")
        elif margin >= 0:
            return _badge(pct, "yellow")
        return _badge(pct, "red")

    @display(description=_("Estoque"))
    def stock_available_display(self, obj):
        """Display available stock from Stockman (if available)."""
        try:
            from django.db.models import Sum
            from shopman.stockman.models import Quant
            total = (
                Quant.objects
                .filter(sku=obj.sku, position__is_saleable=True)
                .aggregate(total=Sum("_quantity"))["total"]
            )
            if total is None:
                return "—"
            from shopman.utils.formatting import format_quantity
            return format_quantity(total)
        except ImportError:
            return "—"

    action_form = ProductActionForm
    actions = [
        "unpublish_products",
        "publish_products",
        "pause_products",
        "resume_products",
        "update_price_percent",
        "add_to_collection",
    ]

    def _bulk_set(self, request, queryset, field, value, label):
        """Itera com save() (não queryset.update()) para disparar product_updated →
        re-projeção para canais externos (iFood retrai o despublicado) + histórico.
        queryset.update() pulava o save() e nada disso acontecia."""
        count = 0
        for product in queryset:
            if getattr(product, field) != value:
                setattr(product, field, value)
                product.save()
                count += 1
        self.message_user(request, f"{count} produto(s) {label}.")

    @admin.action(description=_("Despublicar produtos selecionados"))
    def unpublish_products(self, request, queryset):
        self._bulk_set(request, queryset, "is_published", False, "despublicado(s)")

    @admin.action(description=_("Publicar produtos selecionados"))
    def publish_products(self, request, queryset):
        self._bulk_set(request, queryset, "is_published", True, "publicado(s)")

    @admin.action(description=_("Desabilitar venda dos selecionados"))
    def pause_products(self, request, queryset):
        self._bulk_set(request, queryset, "is_sellable", False, "com venda desabilitada")

    @admin.action(description=_("Habilitar venda dos selecionados"))
    def resume_products(self, request, queryset):
        self._bulk_set(request, queryset, "is_sellable", True, "com venda habilitada")

    @admin.action(description=_("Atualizar preço +X%%"))
    def update_price_percent(self, request, queryset):
        percent_str = request.POST.get("price_percent", "").strip()
        if not percent_str:
            messages.warning(
                request,
                _("Preencha o campo Percentual ao lado da ação. Ex.: 10 para +10%, -5 para -5%."),
            )
            return

        try:
            percent = Decimal(percent_str)
        except Exception:
            messages.error(request, _("Percentual inválido: %(val)s") % {"val": percent_str})
            return

        multiplier = 1 + (percent / 100)
        updated = 0
        for product in queryset:
            new_price = int(product.base_price_q * multiplier)
            if new_price < 0:
                new_price = 0
            product.base_price_q = new_price
            product.save(update_fields=["base_price_q"])
            updated += 1

        self.message_user(
            request,
            _("%(count)d produto(s) atualizado(s) com %(pct)s%%.") % {
                "count": updated,
                "pct": percent,
            },
        )

    @admin.action(description=_("Adicionar à coleção"))
    def add_to_collection(self, request, queryset):
        collection_id = request.POST.get("collection_id", "").strip()
        if not collection_id:
            messages.warning(
                request,
                _("Escolha a coleção de destino no campo Coleção ao lado da ação."),
            )
            return

        try:
            collection = Collection.objects.get(pk=collection_id)
        except Collection.DoesNotExist:
            messages.error(request, _("Coleção não encontrada: %(id)s") % {"id": collection_id})
            return

        created = 0
        skipped = 0
        max_sort = CollectionItem.objects.filter(collection=collection).count()
        for product in queryset:
            _collection_item, was_created = CollectionItem.objects.get_or_create(
                collection=collection,
                product=product,
                defaults={"sort_order": max_sort, "is_primary": False},
            )
            if was_created:
                created += 1
                max_sort += 1
            else:
                skipped += 1

        self.message_user(
            request,
            _("%(created)d adicionado(s) à '%(col)s', %(skipped)d já existiam.") % {
                "created": created,
                "col": collection.name,
                "skipped": skipped,
            },
        )
