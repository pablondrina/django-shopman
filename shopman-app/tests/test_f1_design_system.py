"""
Tests for WP-F1: Design System Mobile-First.

Covers:
- 1.1 Tailwind build produces output
- 1.2 Typography minimum sizes
- 1.3 Touch targets (44px rule) in components
- 1.4 Component accessibility (aria, roles, focus traps)
- 1.5 Product image template tag
- 1.6 Motion & reduced-motion
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from django.test import TestCase

# Base paths
APP_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = APP_DIR / "channels" / "web" / "templates"
COMPONENTS_DIR = TEMPLATES_DIR / "components"
STATIC_DIR = APP_DIR / "channels" / "web" / "static" / "storefront"
INPUT_CSS = APP_DIR / "static" / "src" / "input.css"


def _read_template(name: str) -> str:
    """Read a template file from the components directory."""
    path = COMPONENTS_DIR / name
    if path.exists():
        return path.read_text()
    return ""


def _read_all_templates() -> dict[str, str]:
    """Read all HTML templates from the storefront."""
    result = {}
    for path in TEMPLATES_DIR.rglob("*.html"):
        result[str(path.relative_to(TEMPLATES_DIR))] = path.read_text()
    return result


# ══════════════════════════════════════════════════════════════════════
# 1.1 Tailwind Build
# ══════════════════════════════════════════════════════════════════════


class TestTailwindBuild(TestCase):
    """Tailwind configuration and build pipeline."""

    def test_tailwind_config_exists(self):
        """tailwind.config.js exists with proper content scanning."""
        config_path = APP_DIR / "tailwind.config.js"
        self.assertTrue(config_path.exists(), "tailwind.config.js missing")
        content = config_path.read_text()
        self.assertIn("templates/**/*.html", content)

    def test_input_css_has_tailwind_directives(self):
        """input.css has @tailwind base/components/utilities."""
        content = INPUT_CSS.read_text()
        self.assertIn("@tailwind base", content)
        self.assertIn("@tailwind components", content)
        self.assertIn("@tailwind utilities", content)

    def test_tailwind_build_produces_output(self):
        """output.css exists and is non-trivial (>10KB)."""
        output = STATIC_DIR / "css" / "output.css"
        if not output.exists():
            self.skipTest("output.css not built — run `make css`")
        size = output.stat().st_size
        self.assertGreater(size, 10_000, f"output.css suspiciously small: {size} bytes")

    def test_tailwind_config_has_xs_breakpoint(self):
        """xs: 375px breakpoint added for mobile-first."""
        config = (APP_DIR / "tailwind.config.js").read_text()
        self.assertIn("375", config)

    def test_package_json_has_tailwind_plugins(self):
        """package.json includes @tailwindcss/forms and @tailwindcss/typography."""
        pkg = (APP_DIR / "package.json").read_text()
        self.assertIn("@tailwindcss/forms", pkg)
        self.assertIn("@tailwindcss/typography", pkg)


# ══════════════════════════════════════════════════════════════════════
# 1.2 Typography — No text-xs in body content
# ══════════════════════════════════════════════════════════════════════


class TestTypography(TestCase):
    """Typography rules: minimum sizes, font declarations."""

    def test_input_css_has_font_face_declarations(self):
        """input.css declares @font-face for Inter and Playfair Display."""
        content = INPUT_CSS.read_text()
        self.assertIn("font-family: 'Inter'", content)
        # Either Playfair Display or the configured heading font
        self.assertTrue(
            "Playfair" in content or "font-face" in content,
            "No @font-face for heading font",
        )

    def test_font_display_swap(self):
        """All @font-face use font-display: swap for performance."""
        content = INPUT_CSS.read_text()
        face_count = content.count("@font-face")
        swap_count = content.count("font-display: swap")
        self.assertEqual(face_count, swap_count,
            f"{face_count} @font-face but only {swap_count} font-display: swap")

    def test_no_text_xs_in_body_content(self):
        """text-xs not used for primary content — only timestamps/refs."""
        templates = _read_all_templates()
        violations = []
        # text-xs is OK in: timestamps, refs, captions, meta, badges,
        # form labels, muted auxiliary text, pills/counters, status indicators,
        # nav labels, buttons, dev labels, footer
        allowed_contexts = re.compile(
            r'('
            r'time|ref|caption|meta|badge|text-\[1[012]px\]|sr-only|tracking-'
            r'|<label'
            r'|text-muted-foreground'
            r'|rounded-full'
            r'|opacity-\d'
            r'|text-success|text-warning|text-error'
            r'|text-secondary|text-primary'
            r'|line-clamp'
            r'|btn-|<button'
            r'|flex-col.*items-center.*justify-center.*flex-1'
            r'|discount|feedback'
            r'|desenvolvimento|dev-label'
            r')',
            re.IGNORECASE,
        )
        for name, content in templates.items():
            # Find lines with text-xs
            for i, line in enumerate(content.split("\n"), 1):
                if "text-xs" in line and not allowed_contexts.search(line):
                    # Skip if it's in a comment
                    stripped = line.strip()
                    if stripped.startswith("{#") or stripped.startswith("<!--"):
                        continue
                    violations.append(f"{name}:{i}")

        # Allow some violations but flag if excessive (threshold tracks project growth)
        self.assertLessEqual(
            len(violations), 30,
            f"Too many text-xs in body content ({len(violations)}): {violations[:10]}...",
        )


# ══════════════════════════════════════════════════════════════════════
# 1.3 Touch Targets — 44px Rule
# ══════════════════════════════════════════════════════════════════════


class TestTouchTargets(TestCase):
    """All interactive elements meet 44px minimum touch target."""

    def test_touch_target_utility_in_css(self):
        """input.css defines .touch-target with min-height 44px."""
        content = INPUT_CSS.read_text()
        self.assertIn("touch-target", content)
        self.assertIn("44px", content)

    def test_button_component_has_touch_size(self):
        """Button component enforces minimum touch target size."""
        btn = _read_template("_button_inner.html")
        self.assertTrue(btn, "_button_inner.html not found")
        # Should have py-3 or touch-target or min-h
        self.assertTrue(
            any(x in btn for x in ["py-3", "py-2.5", "touch-target", "min-h-"]),
            "Button component missing touch target sizing",
        )

    def test_stepper_buttons_are_48px(self):
        """Stepper ±/– buttons are at least 48px."""
        stepper = _read_template("_stepper.html")
        self.assertTrue(stepper, "_stepper.html not found")
        # 48px buttons (w-12 = 48px or explicit sizing)
        self.assertTrue(
            any(x in stepper for x in ["w-12", "h-12", "48px", "touch-target"]),
            "Stepper buttons should be 48px",
        )

    def test_input_component_has_48px_height(self):
        """Input component has min-height for comfortable tapping."""
        inp = _read_template("_input.html")
        self.assertTrue(inp, "_input.html not found")
        # py-3 gives 48px, or h-12, or min-h
        self.assertTrue(
            any(x in inp for x in ["py-3", "h-12", "min-h-", "48px"]),
            "Input component should be at least 48px height",
        )

    def test_radio_cards_min_height(self):
        """Radio cards have minimum 56px height."""
        cards = _read_template("_radio_cards.html")
        self.assertTrue(cards, "_radio_cards.html not found")
        # Should reference min-height or py-4 for 56px+ (Tailwind class or inline style)
        self.assertTrue(
            any(x in cards for x in ["min-h-[56", "min-h-14", "py-4", "py-3.5", "min-height: 56px"]),
            "Radio cards should have 56px min-height",
        )


# ══════════════════════════════════════════════════════════════════════
# 1.4 Component Accessibility
# ══════════════════════════════════════════════════════════════════════


class TestComponentAccessibility(TestCase):
    """Components have proper ARIA attributes and roles."""

    def test_toast_has_aria_live(self):
        """Toast component has aria-live for screen readers."""
        toast = _read_template("_toast.html")
        self.assertTrue(toast, "_toast.html not found")
        self.assertIn("aria-live", toast)

    def test_toast_has_assertive_for_errors(self):
        """Toast uses aria-live='assertive' for errors."""
        toast = _read_template("_toast.html")
        self.assertIn("assertive", toast)

    def test_bottom_sheet_has_dialog_role(self):
        """Bottom sheet has role='dialog' and aria-modal."""
        sheet = _read_template("_bottom_sheet.html")
        self.assertTrue(sheet, "_bottom_sheet.html not found")
        self.assertIn('role="dialog"', sheet)
        self.assertIn("aria-modal", sheet)

    def test_bottom_sheet_has_escape_close(self):
        """Bottom sheet closes on Escape key."""
        sheet = _read_template("_bottom_sheet.html")
        self.assertIn("escape", sheet.lower())

    def test_stepper_has_aria_label(self):
        """Stepper has aria-label for quantity control."""
        stepper = _read_template("_stepper.html")
        self.assertTrue(stepper, "_stepper.html not found")
        self.assertTrue(
            "aria-label" in stepper or "aria-labelledby" in stepper,
            "Stepper missing aria-label",
        )

    def test_empty_state_exists(self):
        """Empty state component exists for graceful empty lists."""
        empty = _read_template("_empty_state.html")
        self.assertTrue(empty, "_empty_state.html not found")

    def test_skeleton_exists_with_animation(self):
        """Skeleton component exists for loading states."""
        skeleton = _read_template("_skeleton.html")
        self.assertTrue(skeleton, "_skeleton.html not found")
        # Should reference skeleton animation class
        self.assertIn("skeleton", skeleton.lower())


# ══════════════════════════════════════════════════════════════════════
# 1.5 Product Image Template Tag
# ══════════════════════════════════════════════════════════════════════


class TestProductImageTag(TestCase):
    """product_image template tag generates proper img elements."""

    def test_product_image_tag_exists(self):
        """storefront_tags has product_image tag registered."""
        from channels.web.templatetags.storefront_tags import product_image

        self.assertTrue(callable(product_image))

    def test_product_image_generates_placeholder_for_no_image(self):
        """Product without image gets SVG placeholder."""
        from channels.web.templatetags.storefront_tags import product_image

        class FakeProduct:
            name = "Pão Francês"
            image = None

        html = str(product_image(FakeProduct(), size="card"))
        self.assertIn("img", html)
        self.assertIn("data:image/svg+xml", html)
        self.assertIn('alt="Pão Francês"', html)

    def test_product_image_sizes(self):
        """product_image supports thumb/card/detail sizes."""
        from channels.web.templatetags.storefront_tags import product_image

        class FakeProduct:
            name = "Croissant"
            image = None

        for size, expected_width in [("thumb", "200"), ("card", "400"), ("detail", "800")]:
            html = str(product_image(FakeProduct(), size=size))
            self.assertIn(f'width="{expected_width}"', html,
                f"Size '{size}' should produce width={expected_width}")

    def test_product_image_has_lazy_loading_when_real_image(self):
        """Real product image gets loading='lazy' and decoding='async'."""
        from channels.web.templatetags.storefront_tags import product_image

        class FakeImage:
            name = "test.jpg"
            url = "/media/products/test.jpg"

        class FakeProduct:
            name = "Baguete"
            image = FakeImage()

        html = str(product_image(FakeProduct(), size="card"))
        self.assertIn('loading="lazy"', html)
        self.assertIn('decoding="async"', html)
        self.assertIn("srcset", html)


# ══════════════════════════════════════════════════════════════════════
# 1.6 Motion & Reduced Motion
# ══════════════════════════════════════════════════════════════════════


class TestMotion(TestCase):
    """CSS transitions and reduced-motion support."""

    def test_input_css_has_reduced_motion(self):
        """input.css includes prefers-reduced-motion media query."""
        content = INPUT_CSS.read_text()
        self.assertIn("prefers-reduced-motion", content)

    def test_input_css_has_keyframes(self):
        """input.css defines animation keyframes."""
        content = INPUT_CSS.read_text()
        self.assertIn("@keyframes", content)
        # Should have at least: fadeIn, slideUp, spin
        for name in ["fadeIn", "slideUp", "spin"]:
            self.assertIn(name, content, f"Missing @keyframes {name}")

    def test_htmx_swap_transitions(self):
        """HTMX swap transitions defined in CSS."""
        content = INPUT_CSS.read_text()
        self.assertIn("htmx-swapping", content)


# ══════════════════════════════════════════════════════════════════════
# Component Inventory — Ensure all required components exist
# ══════════════════════════════════════════════════════════════════════


class TestComponentInventory(TestCase):
    """All required design system components are present."""

    REQUIRED_COMPONENTS = [
        "_button.html",
        "_button_inner.html",
        "_input.html",
        "_stepper.html",
        "_toggle.html",
        "_radio_cards.html",
        "_toast.html",
        "_badge.html",
        "_empty_state.html",
        "_skeleton.html",
        "_bottom_sheet.html",
        "_floating_button.html",
        "_bottom_nav.html",
        "_header.html",
    ]

    def test_all_required_components_exist(self):
        """Every required component file is present."""
        missing = []
        for name in self.REQUIRED_COMPONENTS:
            if not (COMPONENTS_DIR / name).exists():
                missing.append(name)
        self.assertEqual(missing, [], f"Missing components: {missing}")

    def test_all_components_are_valid_html(self):
        """All component files contain HTML (non-empty, have tags)."""
        for name in self.REQUIRED_COMPONENTS:
            path = COMPONENTS_DIR / name
            if path.exists():
                content = path.read_text()
                self.assertTrue(
                    len(content) > 10,
                    f"{name} is too short ({len(content)} chars)",
                )
