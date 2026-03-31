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
      color: oklch(var(--primary) / 0.8);
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
    # Mix factors: positive = toward white (L→1, C→0), negative = toward black (L→0, C→0)
    if not is_dark:
        mix_factors = [
            0.0,    # 1: bg — exact input
            0.50,   # 2: surface/cards — 50% → white (meio termo)
            1.00,   # 3: input/fields — 100% → white (branco puro)
            0.05,   # 4: muted — 5% → white (barely visible, "transparent" feel)
            -0.10,  # 5: subtle → black
            -0.20,  # 6: border → black
            -0.30,  # 7: border-strong → black
            -0.42,  # 8: ring → black
            -0.55,  # 9: solid → black
            -0.65,  # 10: solid-hover → black
            -0.80,  # 11: muted text → black
            -0.93,  # 12: main text → black
        ]
    else:
        mix_factors = [
            0.0,    # 1: bg — exact input
            -0.50,  # 2: surface/cards — 50% → black (meio termo)
            -1.00,  # 3: input/fields — 100% → black (preto puro)
            -0.05,  # 4: muted — 5% → black (barely visible)
            0.10,   # 5: subtle → white
            0.20,   # 6: border → white
            0.30,   # 7: border-strong → white
            0.42,   # 8: ring → white
            0.55,   # 9: solid → white
            0.65,   # 10: solid-hover → white
            0.80,   # 11: muted text → white
            0.93,   # 12: main text → white
        ]

    WHITE_L = 0.985
    BLACK_L = 0.08

    scale = {}
    for i, factor in enumerate(mix_factors, 1):
        if factor == 0.0:
            # Exact input color
            scale[i] = oklch_to_raw(anchor_L, chroma, hue)
        elif factor > 0:
            # Mix toward white: L→1, C→0
            step_L = _mix(anchor_L, WHITE_L, factor)
            step_C = _mix(chroma, 0.0, factor)
            scale[i] = oklch_to_raw(max(0.0, min(1.0, step_L)), step_C, hue)
        else:
            # Mix toward black: L→0, C→0
            t = abs(factor)
            step_L = _mix(anchor_L, BLACK_L, t)
            step_C = _mix(chroma, 0.0, t)
            scale[i] = oklch_to_raw(max(0.0, min(1.0, step_L)), step_C, hue)
    return scale


# ── Token Generation ─────────────────────────────────────────────────

def generate_design_tokens(
    primary_hex: str,
    secondary_hex: str = "",
    accent_hex: str = "",
    neutral_hex: str = "",
    neutral_dark_hex: str = "",
    color_mode: str = "light",
) -> dict:
    """
    Generate complete design token dict from seed colors.

    Args:
        primary_hex: Main brand color (#RRGGBB). Required.
        secondary_hex: Supporting color. Empty = auto-derive (hue +120°).
        accent_hex: Highlight color. Empty = auto-derive (hue -60°).
        neutral_hex: Light mode background. Empty = warm gray from primary hue.
        neutral_dark_hex: Dark mode background. Empty = derived from neutral_hex.
        color_mode: "light", "dark", or "auto".

    Returns:
        Dict with all semantic tokens (OKLCH CSS strings),
        dark mode variants, and hex fallbacks.
    """
    # Parse primary seed
    p_l, p_c, p_h = hex_to_oklch(primary_hex or "#9E833E")

    # Parse or derive secondary
    if secondary_hex:
        s_l, s_c, s_h = hex_to_oklch(secondary_hex)
    else:
        s_l = p_l
        s_h = (p_h + 120) % 360
        s_c = p_c * 0.8

    # Parse or derive accent
    if accent_hex:
        a_l, a_c, a_h = hex_to_oklch(accent_hex)
    else:
        a_l = p_l
        a_h = (p_h - 60) % 360
        a_c = p_c

    # Parse or derive neutral
    if neutral_hex:
        n_l, n_c, n_h = hex_to_oklch(neutral_hex)
    else:
        n_l = 0.92  # default: light warm gray
        n_h = p_h
        n_c = 0.03

    # Generate scales for primary/secondary/accent (fixed L steps)
    primary_light = generate_scale(p_h, p_c, is_dark=False)
    secondary_light = generate_scale(s_h, s_c, is_dark=False)
    accent_light = generate_scale(a_h, a_c, is_dark=False)

    primary_dark = generate_scale(p_h, p_c, is_dark=True)
    secondary_dark = generate_scale(s_h, s_c, is_dark=True)
    accent_dark = generate_scale(a_h, a_c, is_dark=True)

    # Neutral light scale: exact input, surfaces → white
    neutral_light = generate_neutral_scale(n_l, n_c, n_h, is_dark=False)

    # Neutral dark scale: explicit dark tone or auto-derived
    if neutral_dark_hex:
        nd_l, nd_c, nd_h = hex_to_oklch(neutral_dark_hex)
    else:
        # Auto: medium-dark, same hue. Light ~0.90 → Dark ~0.28
        nd_l = 0.20 + (1.0 - n_l) * 0.8
        nd_c = n_c
        nd_h = n_h
    neutral_dark = generate_neutral_scale(nd_l, nd_c, nd_h, is_dark=True)

    # Status scales (fixed hues)
    status_light = {name: generate_scale(hue, STATUS_CHROMA, is_dark=False) for name, hue in STATUS_HUES.items()}
    status_dark = {name: generate_scale(hue, STATUS_CHROMA, is_dark=True) for name, hue in STATUS_HUES.items()}

    _WHITE = oklch_to_raw(1.0, 0.0, 0.0)
    _BLACK = oklch_to_raw(0.0, 0.0, 0.0)

    def _auto_foreground(L: float) -> str:
        """Pick white or black foreground based on lightness for best contrast."""
        return _BLACK if L > 0.6 else _WHITE

    def _exact_color_and_hover(L: float, C: float, H: float, is_dark: bool) -> tuple[str, str, str]:
        """Return (color, hover, foreground) using the EXACT input color.

        Hover shifts L toward the user: lighter in dark mode, darker in light mode.
        """
        color = oklch_to_raw(L, C, H)
        delta = 0.07
        hover_L = min(1.0, L + delta) if is_dark else max(0.0, L - delta)
        hover = oklch_to_raw(hover_L, C, H)
        foreground = _auto_foreground(L)
        return color, hover, foreground

    is_dark_mode = color_mode == "dark"

    # Exact tokens for primary, secondary, accent (the color admin picked)
    p_color, p_hover, p_fg = _exact_color_and_hover(p_l, p_c, p_h, is_dark_mode)
    s_color, s_hover, s_fg = _exact_color_and_hover(s_l, s_c, s_h, is_dark_mode)
    a_color, a_hover, a_fg = _exact_color_and_hover(a_l, a_c, a_h, is_dark_mode)

    def _map_tokens(pri, sec, acc, neu, stat):
        """Map scales to semantic tokens."""
        tokens = {
            # Surfaces
            "background": neu[1],
            "surface": neu[2],
            "surface_hover": neu[3],
            "input": neu[3],  # field/input bg — same step as surface-hover (lighter than card)
            "muted": neu[4],
            "border": neu[6],
            "border_strong": neu[7],
            "ring": pri[8],
            # Text
            "foreground": neu[12],
            "foreground_muted": neu[11],
            # Primary — exact input color
            "primary": p_color,
            "primary_hover": p_hover,
            "primary_foreground": p_fg,
            # Secondary — exact input color
            "secondary": s_color,
            "secondary_hover": s_hover,
            "secondary_foreground": s_fg,
            # Accent — exact input color
            "accent": a_color,
            "accent_hover": a_hover,
            "accent_foreground": a_fg,
        }
        # Status
        for name in STATUS_HUES:
            tokens[name] = stat[name][9]
            tokens[f"{name}_light"] = stat[name][3]
            tokens[f"{name}_foreground"] = stat[name][12]
        return tokens

    light_tokens = _map_tokens(primary_light, secondary_light, accent_light, neutral_light, status_light)
    dark_tokens = _map_tokens(primary_dark, secondary_dark, accent_dark, neutral_dark, status_dark)

    # Hex fallbacks (for PWA manifest, email, etc.)
    background_hex = oklch_to_hex(*LIGHT_STEPS[0:1], n_c, n_h) if True else "#F5F0EB"
    bg_l = LIGHT_STEPS[0]
    bg_c = n_c * min(1.0, 2.5 * min(bg_l, 1.0 - bg_l))

    result = dict(light_tokens)
    result["dark"] = dark_tokens
    result["background_hex"] = oklch_to_hex(bg_l, bg_c, n_h)
    result["theme_hex"] = primary_hex or "#9E833E"
    result["color_mode"] = color_mode
    return result
