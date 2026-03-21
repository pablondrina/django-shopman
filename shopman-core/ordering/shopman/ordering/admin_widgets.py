from __future__ import annotations

from django.forms import TextInput
from django.utils.html import escape
from django.utils.safestring import mark_safe


class DatalistTextInput(TextInput):
    """
    TextInput com <datalist> para sugestões (autocomplete) sem restringir valores.

    Útil para campos livres que ainda assim têm "valores comuns" (ex.: handle_type, topic, currency).
    """

    def __init__(self, suggestions: list[str], *args, **kwargs):
        self.suggestions = [s for s in suggestions if s]
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs or {}
        list_id = attrs.get("list") or f"datalist__{name}"
        attrs["list"] = list_id

        input_html = super().render(name, value, attrs, renderer)
        options_html = "".join(f"<option value=\"{escape(s)}\"></option>" for s in self.suggestions)
        datalist_html = f"<datalist id=\"{escape(list_id)}\">{options_html}</datalist>"
        return mark_safe(input_html + datalist_html)
