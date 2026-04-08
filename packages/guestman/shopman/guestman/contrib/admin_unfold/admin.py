"""
Customers Admin with Unfold theme.

This module provides Unfold-styled admin classes for Customers models.
To use, add 'shopman.guestman.contrib.admin_unfold' to INSTALLED_APPS after 'customers'.

The admins will automatically unregister the basic admins and register
the Unfold versions.
"""
from __future__ import annotations

import csv

from django.contrib import admin, messages
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.contrib.filters.admin.dropdown_filters import ChoicesDropdownFilter
from unfold.decorators import display

from shopman.utils.contrib.admin_unfold.badges import unfold_badge
from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin, BaseTabularInline
from shopman.guestman.models import (
    Customer,
    CustomerGroup,
    CustomerAddress,
)


# Unregister basic admins
for model in [Customer, CustomerGroup, CustomerAddress]:
    try:
        admin.site.unregister(model)
    except admin.sites.NotRegistered:
        pass


# =============================================================================
# CUSTOM FILTERS
# =============================================================================


class RFMSegmentFilter(admin.SimpleListFilter):
    """Filter customers by RFM segment (via CustomerInsight)."""
    title = _("Segmento RFM")
    parameter_name = "rfm_segment"

    RFM_CHOICES = [
        ("champion", _("Champion")),
        ("loyal_customer", _("Loyal Customer")),
        ("recent_customer", _("Recent Customer")),
        ("at_risk", _("At Risk")),
        ("lost", _("Lost")),
        ("regular", _("Regular")),
    ]

    def lookups(self, request, model_admin):
        return self.RFM_CHOICES

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        try:
            from shopman.guestman.contrib.insights.models import CustomerInsight
            customer_ids = CustomerInsight.objects.filter(
                rfm_segment=value
            ).values_list("customer_id", flat=True)
            return queryset.filter(pk__in=customer_ids)
        except ImportError:
            return queryset


# =============================================================================
# CUSTOMER GROUP ADMIN
# =============================================================================


@admin.register(CustomerGroup)
class CustomerGroupAdmin(BaseModelAdmin):
    list_display = [
        "ref",
        "name",
        "listing_ref",
        "priority",
        "is_default_badge",
        "customer_count",
    ]
    list_filter = ["is_default"]
    search_fields = ["ref", "name"]
    ordering = ["-priority", "name"]

    @display(description="Default", boolean=True)
    def is_default_badge(self, obj):
        return obj.is_default

    @display(description="Customers")
    def customer_count(self, obj):
        return obj.customers.count()


# =============================================================================
# CUSTOMER ADMIN
# =============================================================================


class CustomerAddressInline(BaseTabularInline):
    model = CustomerAddress
    extra = 0
    fields = ["label", "formatted_address", "is_default", "is_verified"]
    readonly_fields = ["is_verified"]


@admin.register(Customer)
class CustomerAdmin(BaseModelAdmin):
    list_display = [
        "ref",
        "name",
        "customer_type_badge",
        "group",
        "phone",
        "orders_link",
        "rfm_segment_badge",
        "churn_risk_badge",
        "is_active_badge",
    ]
    list_filter = [
        "customer_type",
        ("group", ChoicesDropdownFilter),
        "is_active",
        RFMSegmentFilter,
    ]
    search_fields = ["ref", "first_name", "last_name", "document", "phone", "email"]
    readonly_fields = ["uuid", "created_at", "updated_at"]
    inlines = [CustomerAddressInline]

    fieldsets = [
        (
            "Identification",
            {
                "fields": [
                    "ref",
                    "uuid",
                    "first_name",
                    "last_name",
                    "customer_type",
                    "document",
                ]
            },
        ),
        ("Contact", {"fields": ["email", "phone"]}),
        ("Segmentation", {"fields": ["group", "notes"]}),
        (
            "System",
            {
                "fields": [
                    "is_active",
                    "metadata",
                    "created_at",
                    "updated_at",
                    "created_by",
                    "source_system",
                ],
                "classes": ["collapse"],
            },
        ),
    ]

    actions = ["export_selected_csv", "recalculate_insights"]

    @display(description="Type")
    def customer_type_badge(self, obj):
        colors = {
            "individual": "blue",
            "company": "green",
        }
        color = colors.get(obj.customer_type, "base")
        return unfold_badge(obj.get_customer_type_display(), color)

    @display(description="Active", boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active

    @display(description="Orders")
    def orders_link(self, obj):
        """Show order count with link to order list filtered by this customer."""
        try:
            from shopman.omniman.models import Order

            count = Order.objects.filter(
                handle_type="customer", handle_ref=obj.ref
            ).count()
            if count == 0:
                return "-"
            url = (
                reverse("admin:omniman_order_changelist")
                + f"?handle_type=customer&handle_ref={obj.ref}"
            )
            return format_html(
                '<a href="{}" class="text-primary-600 hover:text-primary-700">'
                "{} pedido{}</a>",
                url,
                count,
                "s" if count != 1 else "",
            )
        except ImportError:
            return "-"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        try:
            from shopman.guestman.contrib.insights.models import CustomerInsight
            from django.db.models import OuterRef, Subquery
            insight_qs = CustomerInsight.objects.filter(customer=OuterRef("pk"))
            qs = qs.annotate(
                _rfm_segment=Subquery(insight_qs.values("rfm_segment")[:1]),
                _churn_risk=Subquery(insight_qs.values("churn_risk")[:1]),
            )
        except ImportError:
            pass
        return qs

    @display(description=_("Segmento RFM"))
    def rfm_segment_badge(self, obj):
        """Display RFM segment badge from CustomerInsight."""
        segment = getattr(obj, "_rfm_segment", None)
        if not segment:
            return "-"
        segment_colors = {
            "champion": "green",
            "loyal_customer": "blue",
            "recent_customer": "blue",
            "at_risk": "yellow",
            "lost": "red",
            "regular": "base",
        }
        color = segment_colors.get(segment, "base")
        label = segment.replace("_", " ").title()
        return unfold_badge(label, color)

    @display(description=_("Churn"))
    def churn_risk_badge(self, obj):
        """Display churn risk badge from CustomerInsight."""
        churn_risk = getattr(obj, "_churn_risk", None)
        if churn_risk is None:
            return "-"
        risk = float(churn_risk)
        pct = f"{risk * 100:.0f}%"
        if risk >= 0.7:
            return unfold_badge(pct, "red")
        elif risk >= 0.4:
            return unfold_badge(pct, "yellow")
        else:
            return unfold_badge(pct, "green")

    @admin.action(description=_("Exportar selecionados (CSV)"))
    def export_selected_csv(self, request, queryset):
        """Export selected customers as CSV."""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename=guestman.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "ref", "first_name", "last_name", "customer_type",
            "email", "phone", "group", "is_active",
        ])
        for customer in queryset.select_related("group"):
            writer.writerow([
                customer.ref,
                customer.first_name,
                customer.last_name,
                customer.customer_type,
                customer.email or "",
                customer.phone or "",
                customer.group.ref if customer.group else "",
                customer.is_active,
            ])
        return response

    @admin.action(description=_("Recalcular insights"))
    def recalculate_insights(self, request, queryset):
        """Recalculate CustomerInsight for selected customers."""
        try:
            from shopman.guestman.contrib.insights.service import InsightService
        except ImportError:
            messages.error(request, _("guestman.contrib.insights não está instalado."))
            return

        recalculated = 0
        errors = 0
        for customer in queryset:
            try:
                InsightService.recalculate(customer.ref)
                recalculated += 1
            except Exception as exc:
                errors += 1

        if recalculated:
            messages.success(
                request,
                _("%(count)d insight(s) recalculado(s).") % {"count": recalculated},
            )
        if errors:
            messages.warning(
                request,
                _("%(count)d erro(s) ao recalcular.") % {"count": errors},
            )


# =============================================================================
# CUSTOMER ADDRESS ADMIN
# =============================================================================


@admin.register(CustomerAddress)
class CustomerAddressAdmin(BaseModelAdmin):
    list_display = [
        "customer",
        "label_badge",
        "formatted_address",
        "is_default_badge",
        "is_verified_badge",
    ]
    list_filter = ["label", "is_default", "is_verified"]
    search_fields = ["customer__ref", "customer__first_name", "formatted_address"]
    raw_id_fields = ["customer"]

    @display(description="Label")
    def label_badge(self, obj):
        colors = {
            "home": "green",
            "work": "blue",
            "other": "base",
        }
        color = colors.get(obj.label, "base")
        return unfold_badge(obj.get_label_display(), color)

    @display(description="Default", boolean=True)
    def is_default_badge(self, obj):
        return obj.is_default

    @display(description="Verified", boolean=True)
    def is_verified_badge(self, obj):
        return obj.is_verified
