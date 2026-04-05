"""
OKLCH Color System for the Shopman storefront.

Generates 12-step perceptually uniform color scales from seed colors,
with automatic dark mode inversion. Inspired by Radix Colors (semantic steps),
shadcn/ui (token pairs), and Material Design 3 (seed-to-palette).

Color space: OKLCH (Lightness, Chroma, Hue)
- Perceptually uniform: equal numeric differences = equal perceived differences
- Browser-native: supported in CSS via oklch() function
- Predictable ramps: varying L produces clean light-to-dark scales

Conversion path: sRGB hex → linear sRGB → OKLab → OKLCH (and reverse).
Math from Björn Ottosson's paper: https://bottosson.github.io/posts/oklab/
"""

from __future__ import annotations

import math

# ── sRGB ↔ Linear sRGB ──────────────────────────────────────────────

def _srgb_to_linear(c: float) -> float:
    """sRGB component (0-1) to linear sRGB."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    """Linear sRGB to sRGB component (0-1)."""
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


# ── Linear sRGB ↔ OKLab ─────────────────────────────────────────────

def _linear_srgb_to_oklab(r: float, g: float, b: float) -> tuple[float, float, float]:
    """Linear sRGB to OKLab via LMS intermediate."""
    l_ = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m_ = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s_ = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    l_c = math.copysign(abs(l_) ** (1 / 3), l_)
    m_c = math.copysign(abs(m_) ** (1 / 3), m_)
    s_c = math.copysign(abs(s_) ** (1 / 3), s_)

    L = 0.2104542553 * l_c + 0.7936177850 * m_c - 0.0040720468 * s_c
    a = 1.9779984951 * l_c - 2.4285922050 * m_c + 0.4505937099 * s_c
    b_val = 0.0259040371 * l_c + 0.7827717662 * m_c - 0.8086757660 * s_c
    return L, a, b_val


def _oklab_to_linear_srgb(L: float, a: float, b: float) -> tuple[float, float, float]:
    """OKLab to linear sRGB via LMS intermediate."""
    l_c = L + 0.3963377774 * a + 0.2158037573 * b
    m_c = L - 0.1055613458 * a - 0.0638541728 * b
    s_c = L - 0.0894841775 * a - 1.2914855480 * b

    l_ = l_c ** 3
    m_ = m_c ** 3
    s_ = s_c ** 3

    r = +4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    b_val = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_
    return r, g, b_val


# ── OKLab ↔ OKLCH ───────────────────────────────────────────────────

def _oklab_to_oklch(L: float, a: float, b: float) -> tuple[float, float, float]:
    """OKLab to OKLCH (polar form)."""
    C = math.sqrt(a * a + b * b)
    H = math.degrees(math.atan2(b, a)) % 360
    return L, C, H


def _oklch_to_oklab(L: float, C: float, H: float) -> tuple[float, float, float]:
    """OKLCH to OKLab (rectangular form)."""
    h_rad = math.radians(H)
    a = C * math.cos(h_rad)
    b = C * math.sin(h_rad)
    return L, a, b


# ── Public API: hex ↔ OKLCH ──────────────────────────────────────────

def hex_to_oklch(hex_color: str) -> tuple[float, float, float]:
    """Convert hex color (#RRGGBB) to OKLCH (L, C, H)."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    r_srgb = int(h[0:2], 16) / 255
    g_srgb = int(h[2:4], 16) / 255
    b_srgb = int(h[4:6], 16) / 255

    r_lin = _srgb_to_linear(r_srgb)
    g_lin = _srgb_to_linear(g_srgb)
    b_lin = _srgb_to_linear(b_srgb)

    L, a, b = _linear_srgb_to_oklab(r_lin, g_lin, b_lin)
    return _oklab_to_oklch(L, a, b)


def oklch_to_hex(L: float, C: float, H: float) -> str:
    """Convert OKLCH to hex (#rrggbb), with gamut clamping."""
    L_ok, a, b = _oklch_to_oklab(L, C, H)
    r, g, b_val = _oklab_to_linear_srgb(L_ok, a, b)

    # Gamut clamping: reduce chroma until in sRGB [0, 1]
    attempts = 0
    c = C
    while (r < -0.001 or r > 1.001 or g < -0.001 or g > 1.001 or b_val < -0.001 or b_val > 1.001) and attempts < 20:
        c *= 0.95
        L_ok, a, b = _oklch_to_oklab(L, c, H)
        r, g, b_val = _oklab_to_linear_srgb(L_ok, a, b)
        attempts += 1

    r = max(0.0, min(1.0, r))
    g = max(0.0, min(1.0, g))
    b_val = max(0.0, min(1.0, b_val))

    r_int = round(_linear_to_srgb(r) * 255)
    g_int = round(_linear_to_srgb(g) * 255)
    b_int = round(_linear_to_srgb(b_val) * 255)
    return f"#{r_int:02x}{g_int:02x}{b_int:02x}"


def oklch_to_css(L: float, C: float, H: float) -> str:
    """Format OKLCH as CSS function: oklch(0.550 0.150 85.0)."""
    return f"oklch({L:.3f} {C:.3f} {H:.1f})"


def oklch_to_raw(L: float, C: float, H: float) -> str:
    """Format OKLCH as raw values for CSS variable (no oklch() wrapper).

    Used with Tailwind's <alpha-value> pattern:
      --primary: 0.550 0.150 85.0;
      color: rgb(var(--primary) / 0.8);
    """
    return f"{L:.3f} {C:.3f} {H:.1f}"


# ── Scale Generation ─────────────────────────────────────────────────

# 12-step lightness values (Radix-inspired semantic mapping):
# Steps 1-2:  Backgrounds (page, subtle)
# Steps 3-5:  Interactive states (normal, hover, active)
# Steps 6-8:  Borders (subtle, normal, strong/focus)
# Steps 9-10: Solid backgrounds (brand color, hover)
# Steps 11-12: Text (muted, high-contrast)
LIGHT_STEPS = [0.985, 0.965, 0.935, 0.905, 0.870, 0.825, 0.760, 0.680, 0.550, 0.490, 0.390, 0.250]
DARK_STEPS = [0.110, 0.140, 0.170, 0.200, 0.240, 0.290, 0.350, 0.420, 0.550, 0.610, 0.720, 0.930]

# Status color hues (fixed, not admin-configurable)
STATUS_HUES = {
    "success": 145.0,
    "warning": 75.0,
    "error": 25.0,
    "info": 250.0,
}
STATUS_CHROMA = 0.15


def generate_scale(hue: float, chroma: float, is_dark: bool = False) -> dict[int, str]:
    """
    Generate a 12-step OKLCH color scale (for primary/secondary/accent/status).

    Returns dict mapping step number (1-12) to raw OKLCH values (L C H).
    Chroma is tapered at lightness extremes to stay within sRGB gamut.
    """
    steps = DARK_STEPS if is_dark else LIGHT_STEPS
    scale = {}
    for i, l_val in enumerate(steps, 1):
        taper = max(0.15, min(1.0, 2.5 * min(l_val, 1.0 - l_val)))
        step_chroma = chroma * taper
        scale[i] = oklch_to_raw(l_val, step_chroma, hue)
    return scale


def _mix(a: float, b: float, t: float) -> float:
    """Linear interpolation: a→b by factor t (0=a, 1=b)."""
    return a + (b - a) * t


def generate_neutral_scale(
    anchor_L: float, chroma: float, hue: float, is_dark: bool = False,
) -> dict[int, str]:
    """
    Generate a 12-step neutral scale anchored at the input color's lightness.

    Mixing model: like paint. Mixing with white → L↑ C↓. With black → L↓ C↓.

    Semantic mapping:
      1: page background (EXACT admin-chosen color)
      2: surface — cards, modals (25% → white/black)
      3: surface-hover — inputs, fields (50% → white/black)
      4: muted — barely different from bg, "transparent" feel (5% → white/black)
      5-6: borders (10-20% → black/white)
      7-8: border-strong, focus ring (30-42% → black/white)
      9-10: solid (55-65% → black/white)
      11: muted text (80% → black/white)
      12: main text (93% → black/white)
    """
    # Target L values calibrated to match Oxbow UI's neutral scale.
    # When anchor is white (L≈1.0), produces: bg=1.0, surface=1.0, muted=0.97,
    # border=0.92, ring=0.71, muted-fg=0.56, fg=0.145.
    if not is_dark:
        target_L = [
            1.000,  # 1: bg
            1.000,  # 2: surface/cards
            0.922,  # 3: input/fields
            0.970,  # 4: muted
            0.940,  # 5: subtle border
            0.922,  # 6: border
            0.850,  # 7: border-strong
            0.708,  # 8: ring / focus
            0.450,  # 9: solid
            0.380,  # 10: solid-hover
            0.556,  # 11: muted text
            0.145,  # 12: main text
        ]
    else:
        target_L = [
            0.130,  # 1: bg
            0.160,  # 2: surface/cards
            0.200,  # 3: input/fields
            0.180,  # 4: muted
            0.220,  # 5: subtle border
            0.260,  # 6: border
            0.320,  # 7: border-strong
            0.420,  # 8: ring / focus
            0.650,  # 9: solid
            0.720,  # 10: solid-hover
            0.556,  # 11: muted text
            0.930,  # 12: main text
        ]

    scale = {}
    for i, step_L in enumerate(target_L, 1):
        if chroma < 0.01:
            # Achromatic input (white, black, gray) → pure gray scale, zero chroma
            step_C = 0.0
        else:
            # Chroma tapers toward extremes (near white/black = low chroma)
            dist_from_mid = abs(step_L - 0.5) * 2  # 0 at L=0.5, 1 at L=0/1
            step_C = chroma * max(0.05, 1.0 - dist_from_mid * 0.9)
        scale[i] = oklch_to_raw(max(0.0, min(1.0, step_L)), step_C, hue)
    return scale


# ── Token Generation ─────────────────────────────────────────────────


def generate_design_tokens(
    primary_hex: str = "",
    secondary_hex: str = "",
    accent_hex: str = "",
    neutral_hex: str = "",
    neutral_dark_hex: str = "",
    color_mode: str = "light",
) -> dict:
    """Tokens do storefront: **Oxbow UI** (`oxbow_tokens.build_storefront_design_tokens`).

    Os argumentos de cor são ignorados; mantidos só por compatibilidade de assinatura.
    Use `Shop.design_tokens` ou `build_storefront_design_tokens` com fontes.
    """
    from shopman.oxbow_tokens import build_storefront_design_tokens

    return build_storefront_design_tokens(color_mode=color_mode)
