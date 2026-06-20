"""Unfold read-only display helpers for the Shopman suite."""

import json

from django.utils.html import format_html, format_html_join


def unfold_kv_list(data, *, empty="—"):
    """Render a dict as a read-only Unfold definition list (label → value).

    For parsed, human-readable views of JSONField/metadata in admins — instead of
    raw JSON. Nested dict/list values are pretty-printed as compact JSON. Returns
    ``empty`` when there is nothing to show.
    """
    if not data or not isinstance(data, dict):
        return empty

    def _fmt(value):
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    rows = format_html_join(
        "",
        '<div class="flex gap-3 py-1 border-b border-base-100 dark:border-base-800">'
        '<dt class="font-medium text-base-500 dark:text-base-400 w-48 shrink-0">{}</dt>'
        '<dd class="text-sm break-words">{}</dd></div>',
        ((key, _fmt(value)) for key, value in data.items()),
    )
    return format_html('<dl class="flex flex-col">{}</dl>', rows)
