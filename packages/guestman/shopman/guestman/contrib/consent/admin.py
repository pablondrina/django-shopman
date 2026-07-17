"""Consent admin."""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from shopman.guestman.contrib.consent.models import CommunicationConsent
from shopman.utils import unfold_badge
from unfold.admin import ModelAdmin
from unfold.decorators import display

_STATUS_COLORS = {"opted_in": "green", "opted_out": "red", "pending": "yellow"}


@admin.register(CommunicationConsent)
class CommunicationConsentAdmin(ModelAdmin):
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

    @display(description="situação")
    def status_badge(self, obj):
        return unfold_badge(obj.get_status_display(), _STATUS_COLORS.get(obj.status, "base"))

    @display(description="cliente")
    def customer_link(self, obj):
        url = reverse("admin:guestman_customer_change", args=[obj.customer.pk])
        return format_html('<a class="font-medium text-link" href="{}">{}</a>', url, obj.customer.ref)
