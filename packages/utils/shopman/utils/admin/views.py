"""
Enriched autocomplete view for Shopman suite.

Extends Django's AutocompleteJsonView to include extra fields declared
by ModelAdmin classes via ``autocomplete_extra_fields``.

This enables AutofillInlineMixin to read values from the Select2 cache
without monkey-patching the global AutocompleteJsonView.

Usage:
    # In any ModelAdmin:
    class ProductAdmin(admin.ModelAdmin):
        autocomplete_extra_fields = ["base_price_q"]

    # In the project's urls.py (before admin.site.urls):
    from shopman.utils.admin.views import EnrichedAutocompleteJsonView

    urlpatterns = [
        path("admin/autocomplete/", EnrichedAutocompleteJsonView.as_view(admin_site=admin.site)),
        path("admin/", admin.site.urls),
    ]
"""

from django.contrib.admin.views.autocomplete import AutocompleteJsonView


class EnrichedAutocompleteJsonView(AutocompleteJsonView):
    """
    AutocompleteJsonView that includes extra fields from the model instance
    in the JSON response, as declared by the source ModelAdmin.

    The source ModelAdmin can declare which extra fields to include::

        class ProductAdmin(admin.ModelAdmin):
            autocomplete_extra_fields = ["base_price_q"]

    When a Product is selected via autocomplete, the response will include
    ``{"id": "...", "text": "...", "base_price_q": 500}``.
    """

    def serialize_result(self, obj, to_field_name):
        result = super().serialize_result(obj, to_field_name)
        model_admin = self.admin_site._registry.get(type(obj))
        if model_admin is None and obj._meta.proxy:
            model_admin = self.admin_site._registry.get(obj._meta.concrete_model)
        if model_admin:
            for field in getattr(model_admin, "autocomplete_extra_fields", ()):
                if hasattr(obj, field):
                    result[field] = getattr(obj, field)
        return result
