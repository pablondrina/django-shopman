"""Consent admin."""

from django.contrib import admin
from django.utils.html import format_html
from shopman.guestman.contrib.consent.models import CommunicationConsent


@admin.register(CommunicationConsent)
class CommunicationConsentAdmin(admin.ModelAdmin):
    list_display = [
        "customer_link",
        "channel",
        "status_badge",
        "legal_basis",
        "source",
        "consented_at",
        "revoked_at",
    ]
    list_filter = ["channel", "status", "legal_basis"]
    search_fields = ["customer__ref", "customer__first_name"]
    raw_id_fields = ["customer"]
    readonly_fields = ["created_at", "updated_at"]

    def status_badge(self, obj):
        colors = {
            "opted_in": "#28a745",
            "opted_out": "#dc3545",
            "pending": "#ffc107",
        }
        color = colors.get(obj.status, "#6c757d")
        text_color = "#000" if obj.status == "pending" else "#fff"
        return format_html(
            '<span style="background:{}; color:{}; padding:2px 8px; '
            'border-radius:3px; font-size:11px;">{}</span>',
            color,
            text_color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"

    def customer_link(self, obj):
        from django.urls import reverse

        url = reverse("admin:guestman_customer_change", args=[obj.customer.pk])
        return format_html('<a href="{}">{}</a>', url, obj.customer.ref)

    customer_link.short_description = "Cliente"
