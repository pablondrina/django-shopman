"""Admin for CustomerInsight."""

from django.contrib import admin

from shopman.guestman.contrib.insights.models import CustomerInsight


@admin.register(CustomerInsight)
class CustomerInsightAdmin(admin.ModelAdmin):
    list_display = [
        "customer",
        "total_orders",
        "formatted_total_spent",
        "rfm_segment",
        "churn_risk_display",
        "calculated_at",
    ]
    list_filter = ["rfm_segment"]
    search_fields = ["customer__ref", "customer__first_name"]
    readonly_fields = [
        "customer",
        "total_orders",
        "total_spent_q",
        "average_ticket_q",
        "first_order_at",
        "last_order_at",
        "days_since_last_order",
        "average_days_between_orders",
        "preferred_weekday",
        "preferred_hour",
        "favorite_products",
        "preferred_channel",
        "channels_used",
        "rfm_recency",
        "rfm_frequency",
        "rfm_monetary",
        "rfm_segment",
        "churn_risk",
        "predicted_ltv_q",
        "calculated_at",
        "calculation_version",
    ]

    def formatted_total_spent(self, obj):
        return f"R$ {obj.total_spent:,.2f}"

    formatted_total_spent.short_description = "Total Spent"

    def churn_risk_display(self, obj):
        if obj.churn_risk is None:
            return "N/A"
        if obj.churn_risk > 0.7:
            return f"🔴 {obj.churn_risk:.0%}"
        if obj.churn_risk > 0.4:
            return f"🟡 {obj.churn_risk:.0%}"
        return f"🟢 {obj.churn_risk:.0%}"

    churn_risk_display.short_description = "Churn Risk"
