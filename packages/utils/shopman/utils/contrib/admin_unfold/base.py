"""
Base classes for Unfold admin.

Provides BaseModelAdmin, BaseTabularInline and BaseStackedInline with
sensible defaults for textarea fields.
"""

from django import forms
from django.contrib.admin.widgets import AdminTextareaWidget
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.widgets import UnfoldAdminTextareaWidget


class _TextareaCustomizationMixin:
    """Mixin to customize textarea fields in inlines (reduced height)."""

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)

        for field_name, field in formset.form.base_fields.items():
            widget = field.widget

            if isinstance(
                widget, (forms.Textarea, AdminTextareaWidget, UnfoldAdminTextareaWidget)
            ):
                if not hasattr(widget, "attrs"):
                    widget.attrs = {}

                if "rows" in widget.attrs:
                    try:
                        rows = int(widget.attrs["rows"])
                        widget.attrs["rows"] = max(1, rows // 2)
                    except (ValueError, TypeError):
                        widget.attrs["rows"] = 2
                elif isinstance(widget, forms.Textarea):
                    widget.attrs["rows"] = 2

        return formset


class BaseTabularInline(_TextareaCustomizationMixin, TabularInline):
    """TabularInline with reduced textarea height."""

    pass


class BaseStackedInline(_TextareaCustomizationMixin, StackedInline):
    """StackedInline with reduced textarea height."""

    pass


class BaseModelAdmin(ModelAdmin):
    """
    ModelAdmin with sensible defaults for textarea fields:
    - Reduced height (50%)
    - Max width of 42rem (aligned with other form fields)
    """

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        for field_name, field in form.base_fields.items():
            widget = field.widget

            if isinstance(
                widget, (forms.Textarea, AdminTextareaWidget, UnfoldAdminTextareaWidget)
            ):
                if not hasattr(widget, "attrs"):
                    widget.attrs = {}

                current_style = widget.attrs.get("style", "")

                style_parts = [
                    s
                    for s in current_style.split(";")
                    if "height" not in s.lower() and "max-height" not in s.lower()
                ]
                style_parts.append("height: 50%; max-height: 50%;")

                style_parts = [
                    s
                    for s in style_parts
                    if "width" not in s.lower() and "max-width" not in s.lower()
                ]
                style_parts.append("width: 100%; max-width: 42rem;")

                widget.attrs["style"] = "; ".join(
                    [s.strip() for s in style_parts if s.strip()]
                )

                if "rows" in widget.attrs:
                    try:
                        rows = int(widget.attrs["rows"])
                        widget.attrs["rows"] = max(1, rows // 2)
                    except (ValueError, TypeError):
                        widget.attrs["rows"] = 2
                elif isinstance(widget, forms.Textarea):
                    widget.attrs["rows"] = 2

        return form
