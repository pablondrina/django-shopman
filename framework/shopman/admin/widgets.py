"""Custom admin widgets for the Shopman admin."""

from __future__ import annotations

from django import forms
from django.utils.safestring import mark_safe


class FontPreviewWidget(forms.Select):
    """Select widget with live Google Fonts preview.

    Renders a <select> followed by a preview <div> that loads
    the selected Google Font and displays sample text.
    """

    def __init__(self, *args, sample_text: str = "", **kwargs):
        self.sample_text = sample_text or "Aa Bb Cc \u2014 O sabor que encanta"
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        select_html = super().render(name, value, attrs, renderer)
        widget_id = attrs.get("id", name) if attrs else name
        preview_id = f"{widget_id}_preview"
        link_id = f"{widget_id}_font_link"

        current_font = value or ""
        font_url = ""
        if current_font:
            encoded = current_font.replace(" ", "+")
            font_url = f"https://fonts.googleapis.com/css2?family={encoded}:wght@400;600;700&display=swap"

        preview_html = f"""
        <link id="{link_id}" rel="stylesheet" href="{font_url}">
        <div id="{preview_id}"
             style="margin-top:8px;padding:12px 16px;border:1px solid #e5e7eb;border-radius:8px;
                    font-family:'{current_font}',sans-serif;font-size:1.25rem;line-height:1.4;
                    color:#1f2937;background:#fafafa;transition:font-family 0.3s ease">
            {self.sample_text}
        </div>
        <script>
        (function() {{
            var sel = document.getElementById("{widget_id}");
            var preview = document.getElementById("{preview_id}");
            var link = document.getElementById("{link_id}");
            if (!sel || !preview) return;
            sel.addEventListener("change", function() {{
                var font = sel.value;
                if (!font) return;
                var encoded = font.replace(/ /g, "+");
                link.href = "https://fonts.googleapis.com/css2?family=" + encoded + ":wght@400;600;700&display=swap";
                preview.style.fontFamily = "'" + font + "', sans-serif";
            }});
        }})();
        </script>
        """
        return mark_safe(select_html + preview_html)
