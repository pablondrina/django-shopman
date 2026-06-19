"""
Guestman Admin with Unfold theme.

This module provides Unfold-styled admin classes for Guestman models.
To use, add 'shopman.guestman.contrib.admin_unfold' to INSTALLED_APPS after 'customers'.

The admins will automatically unregister the basic admins and register
the Unfold versions.
"""
from __future__ import annotations

import csv

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from shopman.guestman.models import (
    ContactPoint,
    Customer,
    CustomerAddress,
    CustomerGroup,
    ExternalIdentity,
)
from shopman.utils.contrib.admin_unfold.badges import unfold_badge
from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin, BaseTabularInline
from unfold.contrib.filters.admin.dropdown_filters import ChoicesDropdownFilter
from unfold.decorators import display

# Unregister basic admins
for model in [Customer, CustomerGroup, CustomerAddress, ContactPoint, ExternalIdentity]:
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

    @display(description="Guestman")
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
            "business": "green",
        }
        color = colors.get(obj.customer_type, "base")
        return unfold_badge(obj.get_customer_type_display(), color)

    @display(description="Active", boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active

    @display(description="Orders")
    def orders_link(self, obj):
        """Show order count using Orderman's public customer-history contract."""
        try:
            from shopman.orderman.services import CustomerOrderHistoryService

            count = CustomerOrderHistoryService.get_customer_stats(obj.ref).total_orders
            if count == 0:
                return "-"
            return f"{count} pedido{'s' if count != 1 else ''}"
        except ImportError:
            return "-"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        try:
            from django.db.models import OuterRef, Subquery
            from shopman.guestman.contrib.insights.models import CustomerInsight
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
        response["Content-Disposition"] = 'attachment; filename="guestman.csv"'
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
            except Exception:
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


# =============================================================================
# CONTACT POINT ADMIN
# =============================================================================


@admin.register(ContactPoint)
class ContactPointAdmin(BaseModelAdmin):
    list_display = [
        "value_masked",
        "type",
        "customer_link",
        "is_primary",
        "is_verified_badge",
        "created_at",
    ]
    list_filter = ["type", "is_primary", "is_verified", "verification_method"]
    search_fields = ["value_normalized", "customer__ref", "customer__first_name"]
    raw_id_fields = ["customer"]
    readonly_fields = ["id", "verified_at", "created_at", "updated_at"]

    fieldsets = [
        (None, {"fields": ["id", "customer", "type", "value_normalized", "value_display"]}),
        ("Status", {"fields": ["is_primary", "is_verified"]}),
        (
            "Verification",
            {"fields": ["verification_method", "verified_at", "verification_ref"]},
        ),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    @display(description="Value")
    def value_masked(self, obj):
        return obj.value_masked

    @display(description="Customer")
    def customer_link(self, obj):
        from django.urls import reverse

        url = reverse("admin:guestman_customer_change", args=[obj.customer.pk])
        return format_html('<a href="{}">{}</a>', url, obj.customer.ref)

    @display(description="Verified", boolean=True)
    def is_verified_badge(self, obj):
        return obj.is_verified


# =============================================================================
# EXTERNAL IDENTITY ADMIN
# =============================================================================


@admin.register(ExternalIdentity)
class ExternalIdentityAdmin(BaseModelAdmin):
    list_display = [
        "provider",
        "provider_uid_short",
        "customer_link",
        "is_active",
        "created_at",
    ]
    list_filter = ["provider", "is_active"]
    search_fields = ["provider_uid", "customer__ref", "customer__first_name"]
    raw_id_fields = ["customer"]
    readonly_fields = ["id", "created_at", "updated_at"]

    fieldsets = [
        (None, {"fields": ["id", "customer", "provider", "provider_uid"]}),
        ("Status", {"fields": ["is_active"]}),
        ("Metadata", {"fields": ["provider_meta"], "classes": ["collapse"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    @display(description="Provider UID")
    def provider_uid_short(self, obj):
        if len(obj.provider_uid) > 20:
            return obj.provider_uid[:20] + "..."
        return obj.provider_uid

    @display(description="Customer")
    def customer_link(self, obj):
        from django.urls import reverse

        url = reverse("admin:guestman_customer_change", args=[obj.customer.pk])
        return format_html('<a href="{}">{}</a>', url, obj.customer.ref)


# =============================================================================
# LOYALTY ADMIN (optional contrib — only if guestman.contrib.loyalty installed)
# =============================================================================

try:
    from shopman.guestman.contrib.loyalty.models import (
        LoyaltyAccount,
        LoyaltyTransaction,
    )
except ImportError:
    LoyaltyAccount = None  # type: ignore[assignment,misc]
    LoyaltyTransaction = None  # type: ignore[assignment,misc]


if LoyaltyAccount is not None:
    for _model in (LoyaltyAccount, LoyaltyTransaction):
        try:
            admin.site.unregister(_model)
        except admin.sites.NotRegistered:
            pass

    _TIER_COLORS = {
        "bronze": "orange",
        "silver": "base",
        "gold": "yellow",
        "platinum": "blue",
    }

    class LoyaltyTransactionInline(BaseTabularInline):
        """Histórico imutável de pontos sob uma conta (somente leitura)."""

        model = LoyaltyTransaction
        extra = 0
        fields = ["transaction_type", "points", "balance_after", "description", "reference", "created_at"]
        readonly_fields = fields
        ordering = ["-created_at"]

        def has_add_permission(self, request, obj=None):
            return False

        def has_change_permission(self, request, obj=None):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

    @admin.register(LoyaltyAccount)
    class LoyaltyAccountAdmin(BaseModelAdmin):
        list_display = [
            "customer_link",
            "points_balance",
            "lifetime_points",
            "tier_badge",
            "stamps_progress",
            "is_active_badge",
            "enrolled_at",
        ]
        list_filter = ["tier", "is_active"]
        search_fields = ["customer__ref", "customer__first_name"]
        raw_id_fields = ["customer"]
        readonly_fields = ["enrolled_at", "updated_at"]
        inlines = [LoyaltyTransactionInline]

        @display(description=_("Cliente"))
        def customer_link(self, obj):
            from django.urls import reverse

            url = reverse("admin:guestman_customer_change", args=[obj.customer.pk])
            return format_html('<a href="{}">{}</a>', url, obj.customer.ref)

        @display(description=_("Nível"))
        def tier_badge(self, obj):
            color = _TIER_COLORS.get(obj.tier, "base")
            return unfold_badge(obj.get_tier_display(), color)

        @display(description=_("Carimbos"))
        def stamps_progress(self, obj):
            return f"{obj.stamps_current}/{obj.stamps_target} ({obj.stamps_progress_percent}%) — {obj.stamps_completed} completas"

        @display(description=_("Ativo"), boolean=True)
        def is_active_badge(self, obj):
            return obj.is_active

    @admin.register(LoyaltyTransaction)
    class LoyaltyTransactionAdmin(BaseModelAdmin):
        list_display = [
            "created_at",
            "customer_ref",
            "type_badge",
            "points_badge",
            "balance_after",
            "description",
        ]
        list_filter = ["transaction_type"]
        search_fields = ["account__customer__ref", "description", "reference"]
        readonly_fields = [
            "account",
            "transaction_type",
            "points",
            "balance_after",
            "description",
            "reference",
            "created_at",
            "created_by",
        ]
        date_hierarchy = "created_at"

        def has_add_permission(self, request):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

        @display(description=_("Cliente"))
        def customer_ref(self, obj):
            return obj.account.customer.ref

        @display(description=_("Tipo"))
        def type_badge(self, obj):
            return unfold_badge(obj.get_transaction_type_display(), "base")

        @display(description=_("Pontos"))
        def points_badge(self, obj):
            color = "green" if obj.points > 0 else "red"
            text = f"+{obj.points}" if obj.points > 0 else str(obj.points)
            return unfold_badge(text, color)
