"""Automated Omotenashi invariant tests (WP-GAP-03 Fase 2 — sub-item 2.3).

Three automated tests mapped to Omotenashi principles:

- Invisível: storefront templates contain no forbidden DOM-scripting patterns.
- Ma: interactive-element density in key templates is below a conservative threshold.
- Antecipação: GET /checkout/ with a known customer pre-fills phone and name.

Calor and Retorno are too subjective for automated assertion — they stay in the PR checklist.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

STOREFRONT_TEMPLATES = Path(__file__).parents[1] / "templates" / "storefront"

# ── Invisível ──────────────────────────────────────────────────────────


class TestInvisivel:
    """Templates must not contain native inline event handlers."""

    FORBIDDEN = [
        r"onclick\s*=",
        r"onchange\s*=",
        r"onsubmit\s*=",
    ]

    def _html_files(self) -> list[Path]:
        return sorted(STOREFRONT_TEMPLATES.rglob("*.html"))

    def test_no_forbidden_patterns_in_storefront_templates(self):
        """Zero native inline event handlers in storefront templates."""
        violations: list[str] = []
        patterns = [re.compile(p) for p in self.FORBIDDEN]
        for path in self._html_files():
            text = path.read_text(encoding="utf-8")
            for pattern in patterns:
                for match in pattern.finditer(text):
                    lineno = text[: match.start()].count("\n") + 1
                    violations.append(f"{path.relative_to(STOREFRONT_TEMPLATES.parent.parent.parent)}:{lineno} → {match.group()!r}")
        assert not violations, (
            "Forbidden DOM patterns found in storefront templates.\n"
            "Replace native inline handlers with Alpine.js (@click, x-show, x-data) or HTMX attributes.\n\n"
            + "\n".join(violations)
        )

    def test_storefront_templates_directory_exists(self):
        assert STOREFRONT_TEMPLATES.exists()


# ── Ma ────────────────────────────────────────────────────────────────


class TestMa:
    """Interactive element density in key templates must be below a conservative threshold.

    Ma (間) is negative space. A page crowded with interactive elements violates the
    principle of considered emptiness.

    Threshold: < 10 interactive elements (button/a/input/select/textarea) per 1 KB of
    template source. This is deliberately conservative — a typical well-structured page
    is well below 5/KB.
    """

    INTERACTIVE = re.compile(r"<(button|input|select|textarea)\b|<a\s", re.IGNORECASE)

    KEY_TEMPLATES = [
        "home.html",
        "menu.html",
        "cart.html",
        "checkout.html",
        "order_tracking.html",
    ]

    MAX_INTERACTIVE_PER_KB = 10

    def test_interactive_density_in_key_templates(self):
        violations: list[str] = []
        for name in self.KEY_TEMPLATES:
            path = STOREFRONT_TEMPLATES / name
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            size_kb = max(len(text) / 1024, 0.1)
            count = len(self.INTERACTIVE.findall(text))
            density = count / size_kb
            if density > self.MAX_INTERACTIVE_PER_KB:
                violations.append(
                    f"{name}: {count} interactive elements in {size_kb:.1f} KB "
                    f"= {density:.1f}/KB (max {self.MAX_INTERACTIVE_PER_KB})"
                )
        assert not violations, (
            "Interactive element density too high — simplify the template or raise the threshold with justification.\n\n"
            + "\n".join(violations)
        )


# ── Antecipação ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAnticipacao:
    """GET /checkout/ with a known customer pre-fills phone and name in the form."""

    @pytest.fixture(autouse=True)
    def setup(self, db):
        from shopman.shop.models import Channel, Shop

        Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})
        Channel.objects.get_or_create(ref="web", defaults={"name": "Web", "is_active": True})

    def _add_to_cart(self, client):
        from shopman.offerman.models import Product

        product, _ = Product.objects.get_or_create(
            sku="ANTICIPACAO-SKU",
            defaults={
                "name": "Test Product",
                "base_price_q": 1000,
                "is_published": True,
                "is_sellable": True,
            },
        )
        with patch(
            "shopman.shop.services.availability.reserve",
            return_value={
                "ok": True,
                "hold_id": "fake-hold",
                "available_qty": 999,
                "is_paused": False,
                "error_code": None,
                "substitutes": [],
            },
        ):
            client.post("/cart/add/", {"sku": product.sku, "qty": "1"})

    def _login(self, client, customer):
        from shopman.doorman.protocols.customer import AuthCustomerInfo
        from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

        info = AuthCustomerInfo(
            uuid=customer.uuid,
            name=customer.first_name,
            phone=customer.phone,
            email=None,
            is_active=True,
        )
        user, _ = get_or_create_user_for_customer(info)
        client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")

    def test_checkout_prefills_phone_and_name_for_known_customer(self, client):
        """Known customer's phone and name appear pre-filled in GET /checkout/."""
        from shopman.guestman.models import Customer

        customer = Customer.objects.create(
            first_name="Ana",
            last_name="Souza",
            phone="5543999880022",
        )
        self._login(client, customer)
        self._add_to_cart(client)

        resp = client.get("/checkout/")

        assert resp.status_code == 200
        # Phone and name must be visible in the response (pre-filled in the form)
        content = resp.content.decode()
        assert "5543999880022" in content or "43999880022" in content, (
            "Customer phone not found in checkout response — Omotenashi Antecipação violated."
        )
        assert "Ana" in content, (
            "Customer name not found in checkout response — Omotenashi Antecipação violated."
        )
