"""
Unfold-themed admin for Buyman (item master de insumo + fornecedores + custo).

CRUD admins for Material, Supplier and SupplierMaterialCost. Registered when
'shopman.buyman.contrib.admin_unfold' is in INSTALLED_APPS. Buyman has no core
admin, so there is nothing to unregister.
"""

from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from shopman.buyman.models import Material, Supplier, SupplierMaterialCost
from shopman.utils.contrib.admin_unfold.badges import unfold_badge
from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin, BaseTabularInline
from shopman.utils.monetary import format_money
from unfold.decorators import display


class CostOnSupplierInline(BaseTabularInline):
    """Custos dos insumos fornecidos por este fornecedor."""

    model = SupplierMaterialCost
    extra = 0
    fields = ("material", "cost_q", "is_preferred")
    autocomplete_fields = ("material",)


class CostOnMaterialInline(BaseTabularInline):
    """Custos deste insumo por fornecedor."""

    model = SupplierMaterialCost
    extra = 0
    fields = ("supplier", "cost_q", "is_preferred")
    autocomplete_fields = ("supplier",)


@admin.register(Material)
class MaterialAdmin(BaseModelAdmin):
    list_display = ("sku", "name", "unit", "shelf_life_display", "is_active")
    list_filter = ("unit", "is_active")
    search_fields = ("sku", "name")
    ordering = ("sku",)
    inlines = (CostOnMaterialInline,)

    @display(description=_("Validade"))
    def shelf_life_display(self, obj: Material):
        if obj.shelf_life_days is None:
            return unfold_badge(_("Não perecível"), "blue")
        return unfold_badge(_("%(d)d dias") % {"d": obj.shelf_life_days}, "orange")


@admin.register(Supplier)
class SupplierAdmin(BaseModelAdmin):
    list_display = ("ref", "name", "document", "is_active")
    list_filter = ("is_active",)
    search_fields = ("ref", "name", "document")
    ordering = ("name",)
    inlines = (CostOnSupplierInline,)


@admin.register(SupplierMaterialCost)
class SupplierMaterialCostAdmin(BaseModelAdmin):
    list_display = ("material", "supplier", "cost_display", "preferred_display")
    list_filter = ("is_preferred",)
    search_fields = ("material__sku", "material__name", "supplier__ref", "supplier__name")
    autocomplete_fields = ("material", "supplier")
    ordering = ("material", "supplier")

    @display(description=_("Custo"))
    def cost_display(self, obj: SupplierMaterialCost):
        return format_money(obj.cost_q)

    @display(description=_("Preferencial"))
    def preferred_display(self, obj: SupplierMaterialCost):
        if obj.is_preferred:
            return unfold_badge(_("Canônico"), "green")
        return unfold_badge(_("Alternativo"), "base")
