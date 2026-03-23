from __future__ import annotations

from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse

from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin

from .models import StorefrontConfig


@admin.register(StorefrontConfig)
class StorefrontConfigAdmin(BaseModelAdmin):
    list_display = ["brand_name", "short_name", "theme_color", "default_city"]

    fieldsets = (
        ("Marca", {
            "fields": ("brand_name", "short_name", "tagline", "description"),
        }),
        ("Cores", {
            "fields": ("theme_color", "background_color"),
        }),
        ("Localização", {
            "fields": ("default_ddd", "default_city", "location", "whatsapp_number"),
        }),
    )

    def has_add_permission(self, request):
        # Singleton: only allow adding if no record exists
        return not StorefrontConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Singleton: redirect list view to edit the single record
        obj = StorefrontConfig.objects.first()
        if obj:
            return HttpResponseRedirect(
                reverse("admin:web_channel_storefrontconfig_change", args=[obj.pk])
            )
        return super().changelist_view(request, extra_context=extra_context)
