"""
Paleta do storefront (base Oxbow UI), exposta ao CSS como **canais RGB sRGB**.

Motivação: evitar OKLCH em variáveis CSS — contraste e `color-mix` mais previsíveis,
Tailwind continua com `rgb(var(--token) / opacidade)`.

A conversão Oxbow original (OKLCH) → hex → RGB ocorre **uma vez** em build; o runtime
só vê números `R G B` (0–255) por token.
"""

from __future__ import annotations

from shopman.shop.colors import oklch_to_hex

# --- Fonte: triplas OKLCH do global.css Oxbow (só usadas na conversão inicial) ---

_OXBOW_LIGHT: dict[str, str] = {
    "background": "1 0 0",
    "foreground": "0.145 0 0",
    "card": "1 0 0",
    "card_foreground": "0.145 0 0",
    "popover": "1 0 0",
    "popover_foreground": "0.145 0 0",
    "primary": "0.205 0 0",
    "primary_foreground": "0.985 0 0",
    "secondary": "0.97 0 0",
    "secondary_foreground": "0.205 0 0",
    "muted": "0.97 0 0",
    "muted_foreground": "0.556 0 0",
    "accent": "0.659 0.23 35.2",
    "accent_foreground": "0.985 0 0",
    "destructive": "0.577 0.245 27.325",
    "destructive_foreground": "0.985 0 0",
    "success": "0.564 0.168 143.8",
    "success_foreground": "0.985 0 0",
    "warning": "0.681 0.15 59",
    "warning_foreground": "0.145 0 0",
    "info": "0.609 0.202 257.2",
    "info_foreground": "0.985 0 0",
    "border": "0.922 0 0",
    "input": "0.922 0 0",
    "ring": "0.708 0 0",
}

_OXBOW_LIGHT_ALIASES: dict[str, str] = {
    "surface": "1 0 0",
    "surface_hover": "0.97 0 0",
    "foreground_muted": "0.556 0 0",
    "border_strong": "0.85 0 0",
    "primary_hover": "0.175 0 0",
    "secondary_hover": "0.94 0 0",
    "accent_hover": "0.62 0.22 35.2",
    "error": "0.577 0.245 27.325",
    "error_foreground": "0.985 0 0",
}

_OXBOW_DARK: dict[str, str] = {
    "background": "0.145 0 0",
    "foreground": "0.985 0 0",
    "card": "0.145 0 0",
    "card_foreground": "0.985 0 0",
    "popover": "0.145 0 0",
    "popover_foreground": "0.985 0 0",
    "primary": "0.985 0 0",
    "primary_foreground": "0.205 0 0",
    "secondary": "0.269 0 0",
    "secondary_foreground": "0.985 0 0",
    "muted": "0.269 0 0",
    "muted_foreground": "0.708 0 0",
    "accent": "0.769 0.188 70.08",
    "accent_foreground": "0.145 0 0",
    "destructive": "0.396 0.141 25.723",
    "destructive_foreground": "0.985 0 0",
    "success": "0.634 0.188 142.8",
    "success_foreground": "0.985 0 0",
    "warning": "0.785 0.162 64.8",
    "warning_foreground": "0.145 0 0",
    "info": "0.701 0.156 247.3",
    "info_foreground": "0.145 0 0",
    "border": "0.269 0 0",
    "input": "0.269 0 0",
    "ring": "0.439 0 0",
}

_OXBOW_DARK_ALIASES: dict[str, str] = {
    "surface": "0.145 0 0",
    "surface_hover": "0.269 0 0",
    "foreground_muted": "0.708 0 0",
    "border_strong": "0.35 0 0",
    "primary_hover": "0.92 0 0",
    "secondary_hover": "0.32 0 0",
    "accent_hover": "0.72 0.185 70.08",
    "error": "0.396 0.141 25.723",
    "error_foreground": "0.985 0 0",
}


def _raw_oklch_to_hex(raw: str) -> str:
    parts = raw.split()
    return oklch_to_hex(float(parts[0]), float(parts[1]), float(parts[2]))


def _hex_to_rgb_channels(hex_color: str) -> str:
    """Retorna 'R G B' (0–255) para uso em `rgb(var(--x))` / Tailwind."""
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return "128 128 128"
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return f"{r} {g} {b}"


def _map_tokens_to_rgb_channels(raw_map: dict[str, str]) -> dict[str, str]:
    return {k: _hex_to_rgb_channels(_raw_oklch_to_hex(v)) for k, v in raw_map.items()}


def build_storefront_design_tokens(
    *,
    heading_font: str = "Inter",
    body_font: str = "Inter",
    color_mode: str = "light",
) -> dict:
    """
    Dict para `storefront.design_tokens`: cada cor semântica é string **'R G B'** (não OKLCH).

    Uso no CSS: `rgb(var(--primary))` e no Tailwind `rgb(var(--primary) / <alpha-value>)`.
    """
    light_raw = {**_OXBOW_LIGHT, **_OXBOW_LIGHT_ALIASES}
    dark_raw = {**_OXBOW_DARK, **_OXBOW_DARK_ALIASES}

    light = _map_tokens_to_rgb_channels(light_raw)
    dark = _map_tokens_to_rgb_channels(dark_raw)

    bg_hex = _raw_oklch_to_hex(light_raw["background"])
    primary_hex = _raw_oklch_to_hex(light_raw["primary"])

    result = {
        **light,
        "dark": dark,
        "color_mode": color_mode,
        "heading_font": heading_font,
        "body_font": body_font,
        "background_hex": bg_hex,
        "theme_hex": primary_hex,
    }
    return result
