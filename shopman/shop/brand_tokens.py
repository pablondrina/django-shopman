"""
Paleta da marca do storefront (Nelson Boulangerie), exposta ao CSS como **canais RGB sRGB**.

Identidade: **navbar burgundy, corpo creme, detalhes/destaques em dourado/latão, rodapé
verde-musgo** — boulangerie francesa clássica. Os valores são strings `'R G B'` (0–255).

Uso no CSS: `rgb(var(--primary))` e no Tailwind `rgb(var(--primary) / <alpha-value>)`;
na superfície Nuxt a camada de marca emite `rgb(R G B)` nas variáveis reais do tema.

NOTA (dívida de governança): a paleta vive aqui como código porque o deployment é o
Nelson singleton. O destino é movê-la para dado (seed/Shop) consumido por um builder
genérico — ver docs/plans/THEMING-PLAN.md.
"""

from __future__ import annotations

# ── Paleta nomeada NB (referência) → papéis semânticos shadcn/UI-Thing ──
# NB Faubourg (creme) · NB Wood (marrom) · NB Burgundy · NB Brass/Mustard (dourado) ·
# NB Kraft (greige) · NB Moss (verde). Hexes derivados do brand sheet.

_BRAND_LIGHT: dict[str, str] = {
    "background": "245 233 194",          # NB Light Yellow — corpo (comparação; Faubourg era 244 235 215)
    "foreground": "59 42 30",             # NB Wood escurecido — texto marrom
    "card": "252 247 238",                # creme quase-branco
    "card_foreground": "59 42 30",
    "popover": "252 247 238",
    "popover_foreground": "59 42 30",
    "primary": "124 58 64",               # NB Burgundy — CTA/forte
    "primary_foreground": "247 239 224",  # creme sobre burgundy
    "secondary": "233 220 196",           # NB Kraft claro
    "secondary_foreground": "59 42 30",
    "muted": "237 227 208",
    "muted_foreground": "110 90 72",      # marrom médio (texto secundário)
    "accent": "239 226 201",              # creme/dourado pálido — hover sutil (NÃO o dourado vivo)
    "accent_foreground": "59 42 30",
    "destructive": "180 35 24",
    "destructive_foreground": "255 255 255",
    "success": "94 123 59",               # NB Moss — verde
    "success_foreground": "255 255 255",
    "warning": "200 150 47",              # NB Mustard — dourado
    "warning_foreground": "59 42 30",
    "info": "63 110 140",
    "info_foreground": "255 255 255",
    "border": "220 205 180",              # NB Kraft
    "input": "220 205 180",
    "ring": "200 150 47",                 # NB Brass/Mustard — destaque dourado (foco)
    # Superfícies de identidade (navbar/rodapé/barras/CTAs) — tratamento de marca revesível
    "header": "124 58 64",                # navbar burgundy (NB Burgundy)
    "header_foreground": "247 239 224",   # conteúdo creme sobre a navbar
    "footer": "70 81 47",                 # NB Dark Moss — rodapé
    "footer_foreground": "247 239 224",
    "ink": "83 29 34",                    # NB Dark Burgundy — barras escuras (status)
    "ink_foreground": "247 239 224",
    "bottomnav": "244 235 215",           # NB Faubourg — bottom bar (leve contraste com o fundo)
    "cta": "139 107 46",                  # NB Brass — destaques/CTAs (escuro p/ texto claro)
    "cta_foreground": "250 246 237",      # creme quase-branco sobre o Brass
}

_BRAND_LIGHT_ALIASES: dict[str, str] = {
    "surface": "252 247 238",
    "surface_hover": "237 227 208",
    "foreground_muted": "110 90 72",
    "border_strong": "200 177 137",
    "primary_hover": "106 49 55",
    "secondary_hover": "224 208 180",
    "accent_hover": "230 214 184",
    "error": "180 35 24",
    "error_foreground": "255 255 255",
}

_BRAND_DARK: dict[str, str] = {
    "background": "34 22 16",             # marrom-burgundy quase-preto
    "foreground": "240 230 210",          # creme
    "card": "43 29 22",
    "card_foreground": "240 230 210",
    "popover": "43 29 22",
    "popover_foreground": "240 230 210",
    "primary": "154 79 86",               # burgundy levantado p/ o escuro
    "primary_foreground": "247 239 224",
    "secondary": "58 42 32",
    "secondary_foreground": "240 230 210",
    "muted": "51 36 26",
    "muted_foreground": "194 174 150",
    "accent": "58 42 32",
    "accent_foreground": "240 230 210",
    "destructive": "224 106 94",
    "destructive_foreground": "43 29 22",
    "success": "127 160 85",
    "success_foreground": "34 22 16",
    "warning": "216 174 74",
    "warning_foreground": "34 22 16",
    "info": "111 160 192",
    "info_foreground": "34 22 16",
    "border": "70 53 40",
    "input": "70 53 40",
    "ring": "212 165 63",                 # dourado mais claro p/ o escuro
    "header": "124 58 64",                # navbar burgundy também no escuro (a marca é a marca)
    "header_foreground": "247 239 224",
    "footer": "54 63 36",                 # Dark Moss mais escuro p/ o escuro
    "footer_foreground": "240 230 210",
    "ink": "83 29 34",                    # Dark Burgundy (barras escuras, nos dois modos)
    "ink_foreground": "247 239 224",
    "bottomnav": "43 29 22",              # superfície escura p/ a bottom bar no escuro
    "cta": "150 116 52",                  # NB Brass (um tom acima p/ o escuro)
    "cta_foreground": "250 246 237",
}

_BRAND_DARK_ALIASES: dict[str, str] = {
    "surface": "43 29 22",
    "surface_hover": "58 42 32",
    "foreground_muted": "194 174 150",
    "border_strong": "90 70 50",
    "primary_hover": "168 90 97",
    "secondary_hover": "70 53 40",
    "accent_hover": "70 53 40",
    "error": "224 106 94",
    "error_foreground": "43 29 22",
}


def _rgb_channels_to_hex(channels: str) -> str:
    """'R G B' (0–255) → '#rrggbb'."""
    parts = channels.split()
    if len(parts) != 3:
        return "#808080"
    r, g, b = (max(0, min(255, int(p))) for p in parts)
    return f"#{r:02x}{g:02x}{b:02x}"


def build_storefront_design_tokens(
    *,
    heading_font: str = "Instrument Sans",
    body_font: str = "Instrument Sans",
    color_mode: str = "light",
) -> dict:
    """
    Dict para `storefront.design_tokens`: cada cor semântica é string **'R G B'** (canais sRGB).

    Light + mapa `dark` espelham os mesmos nomes de token, para Nuxt e Django se vestirem
    de UMA config. `theme_hex` (navbar/PWA) = primary burgundy; `background_hex` = creme.
    """
    light = {**_BRAND_LIGHT, **_BRAND_LIGHT_ALIASES}
    dark = {**_BRAND_DARK, **_BRAND_DARK_ALIASES}

    return {
        **light,
        "dark": dark,
        "color_mode": color_mode,
        "heading_font": heading_font,
        "body_font": body_font,
        "background_hex": _rgb_channels_to_hex(_BRAND_LIGHT["background"]),
        "theme_hex": _rgb_channels_to_hex(_BRAND_LIGHT["primary"]),
    }
