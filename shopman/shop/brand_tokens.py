"""
Paleta da marca do storefront (Nelson Boulangerie), exposta ao CSS como **canais RGB sRGB**.

Identidade: **navbar burgundy, corpo creme, detalhes/destaques em dourado/latão, rodapé
verde-musgo** — boulangerie francesa clássica. Os valores são strings `'R G B'` (0–255).

## Arquitetura (escala de matizes)
A fonte da verdade são **escalas nomeadas por matiz** (Burgundy, Brass, Moss, Faubourg),
cada uma com ramp completo (50=mais claro → 950=mais escuro). Os **papéis** semânticos
(`primary`, `background`, `border`, …) mapeiam degraus dessas escalas — então retunar um matiz é
mexer na escala, não caçar hex espalhado. Sistema de cor decidido em
[[project_color_system_plan]] (Modelo A: **burgundy = ação**, ouro = acento/superfície/estado).

- **Ação** = Burgundy (`primary`, `header`, `ink`).
- **Acento/superfície/estado** = Brass (barras douradas, fios, pílula selecionada, foco=Brass-700).
- **Neutros do corpo** = Faubourg (com leve sopro róseo) + Brass claro (canvas 200) + creme/branco.
- **Status** (success/warning/error/info) = eixo PRÓPRIO, distinto da marca (não reusa Moss/Brass).

Dark mode é um esquema derivado à mão (fundo marrom-burgundy quase-preto), não um degrau das
escalas claras — por isso fica num dict próprio.

Uso no CSS: `rgb(var(--primary))`; na superfície Nuxt a marca emite `rgb(R G B)` nas variáveis reais.

NOTA (dívida de governança): a paleta vive aqui como código porque o deployment é o Nelson
singleton. O destino é movê-la para dado (seed/Shop) consumido por um builder genérico.
"""

from __future__ import annotations

# ── Escalas de matiz NB (light) — fonte da verdade. Ramps completos 50 (claro) → 950 (escuro). ──
# Cada matiz tem 11 degraus. Âncoras de papel comentadas ao lado.
_BURGUNDY = {
    "50": "247 236 237", "100": "233 212 214", "200": "219 180 184", "300": "185 123 130",
    "400": "157 88 96", "500": "124 58 64",   # 500 = primary / header (ação)
    "600": "106 49 55",   # 600 = primary-hover
    "700": "94 39 45", "800": "83 29 34",     # 800 = ink (barras escuras)
    "900": "58 20 24", "950": "40 12 15",
}
# BRASS = dourado UNIFICADO (antigo Yellow + Brass fundidos num só ramp). Claros = canvas/creme,
# escuros = latão/bronze. 200 = canvas · 500 = dourado vivo (fios/qty) · 700 = cta · 950 = texto.
_BRASS = {
    "50": "253 250 240", "100": "251 244 220", "200": "245 233 194",  # 200 = background (canvas)
    "300": "236 214 143", "400": "217 184 90",
    "500": "200 150 47",   # 500 = dourado vivo (fio/latão/pílula qty)
    "600": "168 134 47",
    "700": "139 107 46",   # 700 = cta (acento/superfície/estado)
    "800": "107 80 25",    # 800 = ring (foco)
    "900": "76 56 31", "950": "59 42 30",  # 950 = foreground (texto bronze)
}
_MOSS = {
    "50": "241 244 234", "100": "223 230 206", "200": "196 210 166", "300": "138 154 107",
    "400": "116 136 79", "500": "94 123 59", "600": "78 100 49",
    "700": "66 82 42",    # 700 = help (CTA ajuda/WhatsApp)
    "800": "56 69 34", "900": "48 57 30",  # 900 = footer (rodapé)
    "950": "30 36 19",
}
# Faubourg = bege com leve sopro róseo (R puxa, B sobe p/ tirar o amarelo). Neutros do corpo.
_FAUBOURG = {
    "50": "254 251 248", "100": "252 246 241", "200": "245 231 221", "300": "238 223 212",
    "400": "232 216 203", "500": "222 201 187",  # 500 = border / input
    "600": "169 141 119", "700": "110 90 72",     # 700 = muted-foreground
    "800": "82 66 51", "900": "54 43 33", "950": "36 28 21",
}
# Yellow foi FUNDIDO em Brass — alias mantido só para compatibilidade de import antigo.
_YELLOW = _BRASS
_CREAM = "247 239 224"   # creme de leitura sobre superfícies escuras de marca
_WHITE = "255 255 255"

# Eixo de STATUS — distinto da marca, mas na mesma linha terrosa (saturação/valor moderados).
# success = verde-folha (≠ Moss oliva) · warning = âmbar queimado (≠ Brass mostarda) ·
# error = vermelho-tijolo (≠ Burgundy vinho) · info = azul-poeira (único tom frio).
_STATUS = {"success": "62 125 68", "warning": "194 112 28", "error": "180 51 37", "info": "63 110 140"}

_BRAND_LIGHT: dict[str, str] = {
    "background": _BRASS["200"],           # canvas creme (Brass-200 = antigo Yellow-300, 245 233 194)
    "foreground": _BRASS["950"],           # Brass-950 (bronze quase-marrom) — texto
    "card": _FAUBOURG["100"],              # creme quase-branco (sopro róseo)
    "card_foreground": _BRASS["950"],
    "popover": _FAUBOURG["100"],
    "popover_foreground": _BRASS["950"],
    "primary": _BURGUNDY["500"],           # AÇÃO — burgundy
    "primary_foreground": _CREAM,
    "secondary": _FAUBOURG["400"],
    "secondary_foreground": _BRASS["950"],
    "muted": _FAUBOURG["300"],
    "muted_foreground": _FAUBOURG["700"],  # marrom médio (texto secundário)
    "accent": "239 226 201",               # dourado pálido — hover sutil (preservado; era Brass-100 antigo)
    "accent_foreground": _BRASS["950"],
    "destructive": _STATUS["error"],
    "destructive_foreground": _WHITE,
    "success": _STATUS["success"],
    "success_foreground": _WHITE,
    "warning": _STATUS["warning"],
    "warning_foreground": _WHITE,
    "info": _STATUS["info"],
    "info_foreground": _WHITE,
    "border": _FAUBOURG["500"],            # Faubourg rosé
    "input": _FAUBOURG["500"],
    "ring": _BRASS["800"],                 # Deep Brass — foco (passa 3:1 no creme)
    # Superfícies de identidade (navbar/rodapé/barras) — tratamento de marca reversível.
    "header": _BURGUNDY["500"],            # navbar burgundy
    "header_foreground": _CREAM,
    "footer": _MOSS["900"],                # Deep Dark Moss — EXCLUSIVO do rodapé
    "footer_foreground": _WHITE,
    "help": _MOSS["700"],                  # Dark Moss — CTA de ajuda/WhatsApp
    "help_foreground": _WHITE,
    "ink": _BURGUNDY["800"],               # Dark Burgundy — barras escuras (status)
    "ink_foreground": _CREAM,
    "bottomnav": _FAUBOURG["200"],         # Faubourg rosé — bottom bar
    "cta": _BRASS["700"],                  # Brass — acento/superfície/estado (barras, fios, qty)
    "cta_foreground": _WHITE,
}

_BRAND_LIGHT_ALIASES: dict[str, str] = {
    "surface": _FAUBOURG["100"],
    "surface_hover": _FAUBOURG["300"],
    "foreground_muted": _FAUBOURG["700"],
    "border_strong": "200 178 160",
    "primary_hover": _BURGUNDY["600"],
    "secondary_hover": _FAUBOURG["500"],
    "accent_hover": "230 214 184",
    "error": _STATUS["error"],
    "error_foreground": _WHITE,
}

# Dark mode = esquema derivado à mão (fundo marrom-burgundy quase-preto). Status levantado p/
# contraste no escuro; marca (burgundy/brass/moss) mantida; neutros sem o rosé (concern do claro).
_BRAND_DARK: dict[str, str] = {
    "background": "34 22 16",             # marrom-burgundy quase-preto
    "foreground": "240 230 210",          # creme
    "card": "43 29 22",
    "card_foreground": "240 230 210",
    "popover": "43 29 22",
    "popover_foreground": "240 230 210",
    "primary": "154 79 86",               # burgundy levantado p/ o escuro
    "primary_foreground": _CREAM,
    "secondary": "58 42 32",
    "secondary_foreground": "240 230 210",
    "muted": "51 36 26",
    "muted_foreground": "194 174 150",
    "accent": "58 42 32",
    "accent_foreground": "240 230 210",
    "destructive": "224 106 94",
    "destructive_foreground": "43 29 22",
    "success": "126 178 110",             # verde-folha levantado
    "success_foreground": "34 22 16",
    "warning": "224 154 74",              # âmbar levantado
    "warning_foreground": "34 22 16",
    "info": "111 160 192",
    "info_foreground": "34 22 16",
    "border": "70 53 40",
    "input": "70 53 40",
    "ring": "212 165 63",                 # brass mais claro p/ o escuro (visível no fundo escuro)
    "header": "124 58 64",                # navbar burgundy também no escuro (a marca é a marca)
    "header_foreground": _CREAM,
    "footer": "38 45 24",                 # Deep Dark Moss (ainda mais escuro no dark) — só rodapé
    "footer_foreground": _WHITE,
    "help": "54 66 35",                   # Dark Moss — CTA de ajuda/WhatsApp
    "help_foreground": _WHITE,
    "ink": "83 29 34",                    # Dark Burgundy (barras escuras, nos dois modos)
    "ink_foreground": _CREAM,
    "bottomnav": "43 29 22",              # superfície escura p/ a bottom bar no escuro
    "cta": "150 116 52",                  # Brass (um tom acima p/ o escuro)
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
