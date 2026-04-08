"""Timeline admin."""

from django.contrib import admin
from django.utils.html import format_html

from shopman.guestman.contrib.timeline.models import TimelineEvent


@admin.register(TimelineEvent)
class TimelineEventAdmin(admin.ModelAdmin):
    list_display = [
        "created_at",
        "event_type_badge",
        "customer_link",
        "title",
        "channel",
    ]
    list_filter = ["event_type", "channel"]
    search_fields = ["customer__ref", "customer__first_name", "title", "reference"]
    raw_id_fields = ["customer"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    def event_type_badge(self, obj):
        colors = {
            "order": "#28a745",
            "contact": "#007bff",
            "note": "#6c757d",
            "visit": "#17a2b8",
            "loyalty": "#ffc107",
            "system": "#6f42c1",
        }
        color = colors.get(obj.event_type, "#6c757d")
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; '
            'border-radius:3px; font-size:11px;">{}</span>',
            color,
            obj.get_event_type_display(),
        )

    event_type_badge.short_description = "Tipo"

    def customer_link(self, obj):
        from django.urls import reverse

        url = reverse("admin:guestman_customer_change", args=[obj.customer.pk])
        return format_html('<a href="{}">{}</a>', url, obj.customer.ref)

    customer_link.short_description = "Cliente"
