"""Custom admin widgets for the Shopman admin."""

from __future__ import annotations

import json

from django import forms
from django.utils.html import escape
from django.utils.safestring import mark_safe


class FontPreviewWidget(forms.Select):
    """Select widget with a live Google Fonts preview.

    Renders the Unfold select followed by a preview block whose font updates
    live as the operator changes the selection. The interactivity is Alpine
    (the project's DOM standard) — no hand-rolled ``<script>`` — and all static
    chrome uses Unfold utility classes. Only the irreducible dynamic bits (the
    Google Fonts stylesheet href and the preview ``font-family``) are Alpine
    bindings, since no design token can represent an arbitrary web font.
    """

    def __init__(self, *args, sample_text: str = "", **kwargs):
        self.sample_text = sample_text or "Aa Bb Cc — O sabor que encanta"
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = {**(attrs or {}), "x-on:change": "font = $event.target.value"}
        select_html = super().render(name, value, attrs, renderer)

        current_font = value or ""
        # JSON-encoded literal, then HTML-escaped for use inside the x-data attr.
        font_init = escape(json.dumps(current_font))
        sample = escape(self.sample_text)
        href_expr = escape(
            "font ? 'https://fonts.googleapis.com/css2?family=' "
            "+ font.replaceAll(' ', '+') + ':wght@400;600;700&display=swap' : ''"
        )
        style_expr = escape("font ? (\"font-family: '\" + font + \"', sans-serif\") : ''")

        preview_html = (
            f'<div x-data="{{ font: {font_init} }}" class="mt-2">'
            f'<link rel="stylesheet" x-bind:href="{href_expr}">'
            f'<div class="border border-base-200 dark:border-base-700 '
            f'bg-base-50 dark:bg-base-800 text-base-700 dark:text-base-300 '
            f'rounded-default p-4 text-lg" x-bind:style="{style_expr}">{sample}</div>'
            f"</div>"
        )
        return mark_safe(select_html + preview_html)
