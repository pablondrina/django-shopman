"""Admin mixins for the Shopman suite."""

import json


class AutofillInlineMixin:
    """
    Mixin for TabularInline/StackedInline that auto-fills fields from
    autocomplete data.

    Usage::

        class OrderItemInline(AutofillInlineMixin, admin.TabularInline):
            model = OrderItem
            autocomplete_fields = ["product"]
            autofill_fields = {"product": {"unit_price_q": "base_price_q"}}

    When the user selects a product via autocomplete, the unit_price_q field
    is automatically filled with the product's base_price_q value from
    the Select2 cache. Target fields become optional (required=False).

    The mapping format is::

        autofill_fields = {
            "<source_field>": {
                "<target_field>": "<json_key>",
                ...
            }
        }

    Requires: the backend serialize_result must include the json_key
    in the autocomplete JSON response.
    """

    autofill_fields = {}

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)

        if not self.autofill_fields:
            return formset

        # Inject JS via form Media
        _autofill_js = "shopman_utils/js/autocomplete_autofill.js"
        base_form = formset.form
        if not hasattr(base_form, "Media"):
            base_form.Media = type("Media", (), {"js": [_autofill_js]})
        elif _autofill_js not in getattr(base_form.Media, "js", []):
            base_form.Media.js = list(getattr(base_form.Media, "js", [])) + [_autofill_js]

        # Configure widgets: data-autofill on source, required=False on targets
        for source_field, mapping in self.autofill_fields.items():
            if source_field in base_form.base_fields:
                widget = base_form.base_fields[source_field].widget
                inner = getattr(widget, "widget", widget)
                inner.attrs["data-autofill"] = json.dumps(mapping)

            for target_field in mapping:
                if target_field in base_form.base_fields:
                    base_form.base_fields[target_field].required = False

        return formset
