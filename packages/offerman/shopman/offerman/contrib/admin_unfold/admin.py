"""
Offering Admin with Unfold theme.
"""
from __future__ import annotations

from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from import_export.admin import ExportMixin, ImportExportModelAdmin
from unfold.contrib.filters.admin.numeric_filters import RangeNumericFilter
from unfold.contrib.filters.admin.dropdown_filters import RelatedDropdownFilter, ChoicesDropdownFilter
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from unfold.decorators import display

from shopman.utils.admin.mixins import AutofillInlineMixin
from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin, BaseTabularInline
from shopman.utils.contrib.admin_unfold.badges import unfold_badge
from shopman.offerman.models import (
    Collection,
    CollectionItem,
    Listing,
    ListingItem,
    Product,
    ProductComponent,
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


@admin.register(Collection)
class CollectionAdmin(BaseModelAdmin):
    list_display = [
        "slug",
        "name",
        "parent",
        "is_active_badge",
        "valid_from",
        "valid_until",
        "products_count",
    ]
    list_filter = ["is_active", "parent"]
    search_fields = ["slug", "name"]
    ordering = ["sort_order", "name"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CollectionItemInline]

    fieldsets = [
        (None, {"fields": ("slug", "name", "description")}),
        ("Hierarchy", {"fields": ("parent",)}),
        ("Validity", {"fields": ("valid_from", "valid_until")}),
        ("Settings", {"fields": ("sort_order", "is_active")}),
    ]

    @display(description="Active", boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active

    @display(description="Products")
    def products_count(self, obj):
        return obj.items.count()


# =============================================================================
# LISTING ADMIN
# =============================================================================


class ListingItemInline(AutofillInlineMixin, BaseTabularInline):
    model = ListingItem
    extra = 1
    autocomplete_fields = ["product"]
    autofill_fields = {"product": {"price_q": "base_price_q"}}
    fields = ["product", "price_q", "min_qty", "is_published", "is_available"]


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
        ("Validity", {"fields": ("valid_from", "valid_until")}),
        ("Settings", {"fields": ("priority", "is_active")}),
    ]

    def save_formset(self, request, form, formset, change):
        """Default price_q to product.base_price_q when left blank."""
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, ListingItem) and instance.product_id:
                if not instance.price_q:
                    instance.price_q = instance.product.base_price_q
            instance.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()

    @display(description="Active", boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active

    @display(description="Items")
    def items_count(self, obj):
        return obj.items.count()


# =============================================================================
# PRODUCT ADMIN (with Import/Export, advanced filters, bulk actions)
# =============================================================================


class ProductComponentInline(BaseTabularInline):
    model = ProductComponent
    fk_name = "parent"
    extra = 1
    autocomplete_fields = ["component"]


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
    fields = ["listing", "price_q", "is_published", "is_available", "min_qty"]
    readonly_fields = ["listing"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class _ProductImportExportBase(ImportExportModelAdmin, BaseModelAdmin):
    """Combined base for Product admin with Unfold styling + import/export."""
    import_form_class = ImportForm
    export_form_class = ExportForm


@admin.register(Product)
class ProductAdmin(_ProductImportExportBase):
    from shopman.offerman.contrib.admin_unfold.resources import ProductResource

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
        "is_available",
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
            "Price & Cost",
            {"fields": ("base_price_q", "margin_percent")},
        ),
        (
            "Publication & Availability",
            {
                "fields": ("is_published", "is_available"),
                "description": "is_published controls catalog publication, is_available controls purchase availability.",
            },
        ),
        (
            "Configuration",
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
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("metadata", "uuid", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    ]

    @display(description="")
    def image_thumbnail(self, obj):
        if obj.image_url:
            return format_html(
                '<img src="{}" alt="{}" style="width:40px;height:40px;object-fit:cover;border-radius:6px;">',
                obj.image_url, obj.name,
            )
        return ""

    @display(description="Price")
    def formatted_price(self, obj):
        return f"R$ {obj.base_price_q / 100:.2f}"

    @display(description="Status")
    def visibility_status(self, obj):
        """Display visibility status with colored badges."""
        badges = []

        if not obj.is_published:
            badges.append(unfold_badge("Unpublished", "yellow"))
        if not obj.is_available:
            badges.append(unfold_badge("Unavailable", "red"))

        if not badges:
            return unfold_badge("Active", "green")

        return format_html(" ".join(str(b) for b in badges))

    @display(description="Bundle", boolean=True)
    def is_bundle_display(self, obj):
        return obj.is_bundle

    @display(description=_("Custo"))
    def cost_display(self, obj):
        cost_q = obj.reference_cost_q
        if cost_q is None:
            return "-"
        return f"R$ {cost_q / 100:.2f}"

    @display(description=_("Margem"))
    def margin_display(self, obj):
        margin = obj.margin_percent
        if margin is None:
            return "-"
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
        """Display available stock from Stocking (if available)."""
        try:
            from shopman.stockman.models import Quant
            from django.db.models import Sum
            total = (
                Quant.objects
                .filter(sku=obj.sku, position__is_saleable=True)
                .aggregate(total=Sum("_quantity"))["total"]
            )
            if total is None:
                return "-"
            from shopman.utils.formatting import format_quantity
            return format_quantity(total)
        except ImportError:
            return "-"

    actions = [
        "unpublish_products",
        "publish_products",
        "pause_products",
        "resume_products",
        "update_price_percent",
        "add_to_collection",
    ]

    @admin.action(description=_("Unpublish selected products"))
    def unpublish_products(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"{updated} product(s) unpublished.")

    @admin.action(description=_("Publish selected products"))
    def publish_products(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f"{updated} product(s) published.")

    @admin.action(description=_("Pause selected products (unavailable)"))
    def pause_products(self, request, queryset):
        updated = queryset.update(is_available=False)
        self.message_user(request, f"{updated} product(s) paused.")

    @admin.action(description=_("Resume selected products (available)"))
    def resume_products(self, request, queryset):
        updated = queryset.update(is_available=True)
        self.message_user(request, f"{updated} product(s) resumed.")

    @admin.action(description=_("Atualizar preço +X%%"))
    def update_price_percent(self, request, queryset):
        percent_str = request.POST.get("price_percent", "").strip()
        if not percent_str:
            messages.warning(
                request,
                _("Informe o percentual no campo 'price_percent'. Ex: 10 para +10%, -5 para -5%."),
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

    @admin.action(description=_("Adicionar à collection"))
    def add_to_collection(self, request, queryset):
        collection_id = request.POST.get("collection_id", "").strip()
        if not collection_id:
            collections = Collection.objects.filter(is_active=True).order_by("name")
            options = ", ".join(f"{c.pk}={c.name}" for c in collections[:20])
            messages.warning(
                request,
                _("Informe 'collection_id' no POST. Collections ativas: %(opts)s") % {"opts": options},
            )
            return

        try:
            collection = Collection.objects.get(pk=collection_id)
        except Collection.DoesNotExist:
            messages.error(request, _("Collection não encontrada: %(id)s") % {"id": collection_id})
            return

        created = 0
        skipped = 0
        max_sort = CollectionItem.objects.filter(collection=collection).count()
        for product in queryset:
            _, was_created = CollectionItem.objects.get_or_create(
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
