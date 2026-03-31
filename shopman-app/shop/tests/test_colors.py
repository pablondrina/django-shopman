"""
Tests for the OKLCH color system (shop/colors.py).

Covers: hex↔OKLCH roundtrip, CSS formatting, scale generation,
auto-derivation, token generation, gamut clamping, and edge cases.
"""

from __future__ import annotations

import unittest

from shop.colors import (
    DARK_STEPS,
    LIGHT_STEPS,
    STATUS_HUES,
    generate_design_tokens,
    generate_scale,
    hex_to_oklch,
    oklch_to_css,
    oklch_to_hex,
    oklch_to_raw,
)


class TestHexToOklch(unittest.TestCase):
    """hex_to_oklch conversion."""

    def test_black(self):
        L, C, H = hex_to_oklch("#000000")
        self.assertAlmostEqual(L, 0.0, places=2)
        self.assertAlmostEqual(C, 0.0, places=2)

    def test_white(self):
        L, C, H = hex_to_oklch("#ffffff")
        self.assertAlmostEqual(L, 1.0, places=2)
        self.assertAlmostEqual(C, 0.0, places=2)

    def test_pure_red_has_high_chroma(self):
        L, C, H = hex_to_oklch("#ff0000")
        self.assertGreater(C, 0.2)
        self.assertGreater(L, 0.4)

    def test_shorthand_hex(self):
        """#RGB expands to #RRGGBB."""
        L1, C1, H1 = hex_to_oklch("#fff")
        L2, C2, H2 = hex_to_oklch("#ffffff")
        self.assertAlmostEqual(L1, L2, places=5)


class TestOklchToHex(unittest.TestCase):
    """oklch_to_hex conversion with gamut clamping."""

    def test_black_roundtrip(self):
        self.assertEqual(oklch_to_hex(0.0, 0.0, 0.0), "#000000")

    def test_white_roundtrip(self):
        self.assertEqual(oklch_to_hex(1.0, 0.0, 0.0), "#ffffff")

    def test_gamut_clamping(self):
        """Extreme chroma should be clamped to valid sRGB."""
        result = oklch_to_hex(0.5, 0.5, 150.0)
        self.assertTrue(result.startswith("#"))
        self.assertEqual(len(result), 7)


class TestRoundtrip(unittest.TestCase):
    """hex → OKLCH → hex roundtrip accuracy."""

    def test_brand_gold(self):
        """Nelson Boulangerie primary: #9E833E."""
        original = "#9e833e"
        L, C, H = hex_to_oklch(original)
        recovered = oklch_to_hex(L, C, H)
        # Allow ±1 per channel due to float precision
        for i in range(1, 7, 2):
            orig_val = int(original[i : i + 2], 16)
            rec_val = int(recovered[i : i + 2], 16)
            self.assertAlmostEqual(orig_val, rec_val, delta=1)

    def test_various_colors(self):
        """Roundtrip for a range of common colors."""
        colors = ["#c5a55a", "#2563eb", "#dc2626", "#16a34a", "#7c3aed"]
        for hex_color in colors:
            L, C, H = hex_to_oklch(hex_color)
            recovered = oklch_to_hex(L, C, H)
            for i in range(1, 7, 2):
                orig_val = int(hex_color[i : i + 2], 16)
                rec_val = int(recovered[i : i + 2], 16)
                self.assertAlmostEqual(orig_val, rec_val, delta=2, msg=f"{hex_color} channel {i}")


class TestCssFormatting(unittest.TestCase):
    """oklch_to_css and oklch_to_raw formatting."""

    def test_css_format(self):
        result = oklch_to_css(0.55, 0.15, 85.0)
        self.assertEqual(result, "oklch(0.550 0.150 85.0)")

    def test_raw_format(self):
        result = oklch_to_raw(0.55, 0.15, 85.0)
        self.assertEqual(result, "0.550 0.150 85.0")


class TestGenerateScale(unittest.TestCase):
    """12-step scale generation."""

    def test_light_scale_has_12_steps(self):
        scale = generate_scale(85.0, 0.15, is_dark=False)
        self.assertEqual(len(scale), 12)
        self.assertIn(1, scale)
        self.assertIn(12, scale)

    def test_dark_scale_has_12_steps(self):
        scale = generate_scale(85.0, 0.15, is_dark=True)
        self.assertEqual(len(scale), 12)

    def test_step_format(self):
        """Each step should be a raw OKLCH string with 3 space-separated values."""
        scale = generate_scale(85.0, 0.15, is_dark=False)
        for step_num, value in scale.items():
            parts = value.split()
            self.assertEqual(len(parts), 3, f"Step {step_num}: expected 3 parts")

    def test_light_step9_matches_dark_step9(self):
        """Step 9 is the brand color — same L=0.550 in both modes."""
        light = generate_scale(85.0, 0.15, is_dark=False)
        dark = generate_scale(85.0, 0.15, is_dark=True)
        light_L = float(light[9].split()[0])
        dark_L = float(dark[9].split()[0])
        self.assertAlmostEqual(light_L, LIGHT_STEPS[8], places=3)
        self.assertAlmostEqual(dark_L, DARK_STEPS[8], places=3)
        self.assertAlmostEqual(light_L, dark_L, places=3)


class TestAutoDerivation(unittest.TestCase):
    """Auto-derivation of secondary, accent, neutral from primary."""

    def test_secondary_auto_derived(self):
        """Empty secondary → hue +120°."""
        tokens = generate_design_tokens("#9e833e", secondary_hex="")
        self.assertIn("secondary", tokens)
        # Secondary should differ from primary
        self.assertNotEqual(tokens["primary"], tokens["secondary"])

    def test_accent_auto_derived(self):
        """Empty accent → hue -60°."""
        tokens = generate_design_tokens("#9e833e", accent_hex="")
        self.assertIn("accent", tokens)
        self.assertNotEqual(tokens["primary"], tokens["accent"])

    def test_neutral_auto_derived(self):
        """Empty neutral → same hue, chroma ~0.03."""
        tokens = generate_design_tokens("#9e833e", neutral_hex="")
        # Neutral background should have very low chroma (near-gray)
        bg_parts = tokens["background"].split()
        chroma = float(bg_parts[1])
        self.assertLess(chroma, 0.05)

    def test_explicit_colors_override(self):
        """Explicit hex values should be used instead of auto-derivation."""
        tokens_auto = generate_design_tokens("#9e833e")
        tokens_explicit = generate_design_tokens("#9e833e", secondary_hex="#2563eb")
        self.assertNotEqual(tokens_auto["secondary"], tokens_explicit["secondary"])


class TestGenerateDesignTokens(unittest.TestCase):
    """Full token generation."""

    def test_light_tokens_present(self):
        tokens = generate_design_tokens("#9e833e")
        required = [
            "background", "surface", "foreground", "foreground_muted",
            "primary", "primary_hover", "primary_foreground",
            "secondary", "accent", "border", "ring",
        ]
        for key in required:
            self.assertIn(key, tokens, f"Missing token: {key}")

    def test_dark_tokens_present(self):
        tokens = generate_design_tokens("#9e833e")
        self.assertIn("dark", tokens)
        dark = tokens["dark"]
        self.assertIn("background", dark)
        self.assertIn("foreground", dark)
        self.assertIn("primary", dark)

    def test_status_colors_present(self):
        tokens = generate_design_tokens("#9e833e")
        for name in STATUS_HUES:
            self.assertIn(name, tokens, f"Missing status: {name}")
            self.assertIn(f"{name}_light", tokens)
            self.assertIn(f"{name}_foreground", tokens)

    def test_hex_fallbacks(self):
        tokens = generate_design_tokens("#9e833e")
        self.assertIn("background_hex", tokens)
        self.assertIn("theme_hex", tokens)
        self.assertTrue(tokens["background_hex"].startswith("#"))
        self.assertEqual(tokens["theme_hex"], "#9e833e")

    def test_color_mode_passed_through(self):
        for mode in ("light", "dark", "auto"):
            tokens = generate_design_tokens("#9e833e", color_mode=mode)
            self.assertEqual(tokens["color_mode"], mode)
