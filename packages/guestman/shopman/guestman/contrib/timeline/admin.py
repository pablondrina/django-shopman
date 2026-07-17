"""Timeline admin."""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from shopman.guestman.contrib.timeline.models import TimelineEvent
from shopman.utils import unfold_badge
from unfold.admin import ModelAdmin
from unfold.decorators import display

_EVENT_COLORS = {
    "order": "green",
    "contact": "blue",
    "note": "base",
    "visit": "blue",
    "loyalty": "yellow",
    "system": "base",
}


@admin.register(TimelineEvent)
class TimelineEventAdmin(ModelAdmin):
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

    @display(description="tipo")
    def event_type_badge(self, obj):
        return unfold_badge(obj.get_event_type_display(), _EVENT_COLORS.get(obj.event_type, "base"))

    @display(description="cliente")
    def customer_link(self, obj):
        url = reverse("admin:guestman_customer_change", args=[obj.customer.pk])
        return format_html('<a class="font-medium text-link" href="{}">{}</a>', url, obj.customer.ref)
