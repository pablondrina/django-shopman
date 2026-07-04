"""
Playwright E2E for the storefront — post-headless topology.

The headless cutover retired the Django customer pages: the **Nuxt store** now
serves every customer surface, and **Django** serves only the API + the operator/
admin pages. These flows are rewritten accordingly:

  · Customer flows (menu → PDP → cart → checkout, tracking, payment) run against
    the Nuxt store (``store_base_url``), with UI-Thing/Nuxt selectors — not the
    dead HTMX pages.
  · Operator flows (order console, KDS) stay on Django (``operator_base_url``).
  · POS migrated to its OWN Nuxt app (surfaces/pos-nuxt, knob
    ``SHOPMAN_POS_BASE_URL``) and is NOT wired into this gate — its check is
    skipped with an explicit note, mirroring how the Omotenashi browser-QA gate
    skips POS until the fase-C PDV review.

Prerequisites (handled by scripts/run_storefront_e2e.sh):
  pip install pytest-playwright && playwright install chromium
  Two servers up: Nuxt store (:3100, BFF → Django) + Django (:8001), seeded.

Run via the orchestration script (boots both servers + seed):
  bash scripts/run_storefront_e2e.sh

Or against already-running servers:
  pytest shopman/shop/tests/e2e/test_storefront_e2e.py \
      --store-base-url=http://127.0.0.1:3100 \
      --operator-base-url=http://127.0.0.1:8001

These tests require RUNNING servers. They are NOT collected by `make test`
(the e2e directory is excluded from the default pytest path).
"""

from __future__ import annotations

import re

import pytest

# Skip the whole module if Playwright is not installed.
pw = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

# Browser E2E: deselected from the default suite (addopts `-m 'not browser'`),
# re-selected by scripts/run_storefront_e2e.sh with `-m browser` once both the
# Nuxt store and the Django API are up.
pytestmark = pytest.mark.browser

ADD_TO_CART = re.compile(r"Adicionar", re.IGNORECASE)


def _seeded_sku(page, store_base_url) -> str | None:
    """First product SKU off the live menu, from a /product/<sku> card link."""
    page.goto(f"{store_base_url}/menu", wait_until="networkidle")
    href = page.locator("a[href*='/product/']").first.get_attribute("href")
    if not href:
        return None
    match = re.search(r"/product/([^/?#]+)", href)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Customer store (Nuxt) — happy paths
# ---------------------------------------------------------------------------


class TestCustomerStore:
    """Core customer journey against the Nuxt store."""

    def test_01_menu_lists_products_with_pdp_links(self, page, store_base_url):
        """Menu renders product cards that link to the PDP — no dead end."""
        page.goto(f"{store_base_url}/menu", wait_until="networkidle")
        assert page.title(), "Menu should have a title"
        product_links = page.locator("a[href*='/product/']")
        expect(product_links.first).to_be_visible()
        assert product_links.count() > 0, "Seeded menu should list products"

    def test_02_pdp_loads_with_price_and_add_button(self, page, store_base_url):
        """Navigate menu → PDP; the PDP shows price + an Adicionar action."""
        sku = _seeded_sku(page, store_base_url)
        assert sku, "Seeded menu should expose at least one product SKU"
        page.goto(f"{store_base_url}/product/{sku}", wait_until="networkidle")
        assert f"/product/{sku}" in page.url
        # Price is rendered as R$ … and an add-to-cart control is offered.
        expect(page.get_by_text(re.compile(r"R\$")).first).to_be_visible()
        expect(page.get_by_role("button", name=ADD_TO_CART).first).to_be_visible()

    def test_03_add_to_cart_then_cart_shows_item(self, page, store_base_url):
        """Add from the PDP, then the cart leaves the empty state."""
        sku = _seeded_sku(page, store_base_url)
        assert sku, "Seeded menu should expose at least one product SKU"
        page.goto(f"{store_base_url}/product/{sku}", wait_until="networkidle")
        page.get_by_role("button", name=ADD_TO_CART).first.click()
        # Optimistic cart state settles, then the cart page reflects the item.
        page.wait_for_timeout(600)
        page.goto(f"{store_base_url}/cart", wait_until="networkidle")
        expect(page.get_by_text("Sacola vazia")).to_have_count(0)

    def test_04_checkout_surfaces_auth_gate(self, page, store_base_url):
        """Anonymous checkout surfaces the login guardrail (expected, not a bug).

        Checkout gates on authentication: the store either redirects to /login or
        shows the "entrar por telefone" prompt. Either is the intended guardrail.
        """
        page.goto(f"{store_base_url}/checkout", wait_until="networkidle")
        gated = "/login" in page.url or page.get_by_text(
            re.compile(r"entrar", re.IGNORECASE)
        ).first.is_visible()
        assert gated, "Checkout should gate anonymous visitors on login"


# ---------------------------------------------------------------------------
# Customer store (Nuxt) — edge cases
# ---------------------------------------------------------------------------


class TestCustomerEdgeCases:
    """Resilience + order-scoped access on the Nuxt store."""

    def test_05_cart_empty_state(self, page, store_base_url):
        """A fresh visitor sees the empty-cart message, not a crash."""
        page.context.clear_cookies()
        page.goto(f"{store_base_url}/cart", wait_until="networkidle")
        expect(page.get_by_text("Sacola vazia")).to_be_visible()

    def test_06_unknown_order_tracking_is_graceful(self, page, store_base_url):
        """Tracking a non-existent/unauthorized order degrades gracefully.

        Without an order-access grant the store shows an access/not-found view
        with a path back (login), never a stack trace.
        """
        page.context.clear_cookies()
        page.goto(f"{store_base_url}/tracking/NONEXISTENT-001", wait_until="networkidle")
        body = page.locator("body")
        expect(body).to_be_visible()
        # Friendly recovery, not a server error dump.
        assert not re.search(r"Server Error|Traceback", body.inner_text())

    def test_07_tracking_ready_with_grant(
        self, page, store_base_url, grant_order_access, ready_order_ref
    ):
        """With a session grant, tracking renders the real READY order state."""
        grant_order_access(page.context, ready_order_ref)
        page.goto(f"{store_base_url}/tracking/{ready_order_ref}", wait_until="networkidle")
        body = page.locator("body").inner_text()
        # The granted page shows the order, not the access-error fallback.
        assert ready_order_ref in body or re.search(r"pronto|retir|entrega", body, re.IGNORECASE), (
            "Granted tracking page should render the order state"
        )

    def test_08_payment_pending_with_grant(
        self, page, store_base_url, grant_order_access, pix_pending_order_ref
    ):
        """With a session grant, the PIX payment page renders the real state."""
        grant_order_access(page.context, pix_pending_order_ref)
        page.goto(
            f"{store_base_url}/pedido/{pix_pending_order_ref}/pagamento",
            wait_until="networkidle",
        )
        body = page.locator("body").inner_text()
        assert re.search(r"PIX|pagamento|pagar|expir", body, re.IGNORECASE), (
            "Granted payment page should render the PIX payment state"
        )


# ---------------------------------------------------------------------------
# Operator (Django) — still alive post-headless
# ---------------------------------------------------------------------------


class TestOperator:
    """Operator surfaces remain Django-served and gated by auth."""

    def test_09_order_console_loads_for_operator(
        self, page, operator_base_url, operator_session
    ):
        """The Admin/Unfold order console renders for an authenticated operator."""
        operator_session(page.context)
        response = page.goto(f"{operator_base_url}/admin/operacao/pedidos/")
        assert response.status == 200
        expect(page.locator("body")).to_be_visible()
        assert "/login" not in page.url

    def test_10_kds_picker_loads_for_operator(
        self, page, operator_base_url, operator_session
    ):
        """The KDS station picker renders for an authenticated operator."""
        operator_session(page.context)
        response = page.goto(f"{operator_base_url}/operacao/kds/")
        assert response.status == 200
        expect(page.locator("body")).to_be_visible()

    @pytest.mark.parametrize("path", [
        "/admin/operacao/pedidos/",
        "/operacao/kds/",
    ])
    def test_11_operator_pages_require_auth(self, page, operator_base_url, path):
        """Operator pages redirect anonymous visitors to login."""
        page.context.clear_cookies()
        response = page.goto(f"{operator_base_url}{path}")
        assert response.status in (200, 302, 403)
        # Anonymous lands on (or is redirected to) the login flow.
        assert "/login" in page.url or response.status in (302, 403)

    @pytest.mark.skip(
        reason="POS migrou para seu próprio app Nuxt (surfaces/pos-nuxt, "
        "knob SHOPMAN_POS_BASE_URL) e não está cabeado neste gate — coberto na "
        "fase C (revisão do PDV), igual o gate Omotenashi pula o POS."
    )
    def test_12_pos_counter(self):
        """POS flow — deferred to fase C (PDV review)."""


# ---------------------------------------------------------------------------
# Navigation smoke
# ---------------------------------------------------------------------------


class TestNavigation:
    """Core pages return 200 and render."""

    @pytest.mark.parametrize("path", ["/", "/menu", "/cart", "/checkout", "/busca"])
    def test_store_pages_load(self, page, store_base_url, path):
        """Public store pages return 200/redirect and render."""
        response = page.goto(f"{store_base_url}{path}")
        assert response.status in (200, 302), f"{path} returned {response.status}"
        expect(page.locator("body")).to_be_visible()
