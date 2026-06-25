"""
Locust load testing — post-headless topology.

After the headless cutover the customer load is on the **Django API**
(``/api/v1/*``): the Nuxt store's BFF is a thin proxy, so stressing the backend
means hitting the API directly. The customer classes below target the real API
contracts (confirmed in ``shopman/storefront/api/urls.py``); the operator classes
stay on the live Django operator pages.

Targets:
  - Browsing (weight=100): home/menu/PDP/search/availability projections
  - Checkout (weight=50): cart mutation + cart/checkout projections + draft
  - Payment (weight=20): PIX status polling + order tracking
  - Operator (weight=10): order console + dashboard (Django, live)
  - KDS (weight=30): KDS picker + station runtime (Django, live)
  - P95 < 500ms

Prerequisites:
  pip install locust
  Django API up (seeded). Customer host = the Django API origin.

Run (headless, CI-style):
  locust -f shopman/shop/tests/load/locustfile.py \\
    --host=http://127.0.0.1:8001 --headless -u 100 -r 10 --run-time 60s

  # or via the Makefile:
  make load-test HOST=http://127.0.0.1:8001 USERS=100 RATE=10 TIME=60s

The customer host and the operator host are the SAME Django origin post-headless
(the store's HTML host is the Nuxt app, which is not what we load here).

IMPORTANT — run the Django target with the anonymous API throttle DISABLED:

  SHOPMAN_API_ANON_THROTTLE_RATE= python manage.py runserver 127.0.0.1:8001

Locust drives all traffic from one IP; the per-IP ``anon`` throttle (120/min)
would otherwise trip instantly and you'd be measuring the throttle, not the
backend. The env knob keeps the production guardrail intact while letting the
synthetic load reach the app.
"""

from __future__ import annotations

import random
import re

from locust import HttpUser, between, task

_CSRF_INPUT = re.compile(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"')


def _admin_login(client):
    """Authenticate against the Django admin, honoring CSRF.

    The admin login form is CSRF-protected: fetch it, lift the
    ``csrfmiddlewaretoken`` (the ``csrftoken`` cookie rides along on the locust
    session), then POST with the token + Referer.
    """
    form = client.get("/admin/login/", name="/admin/login/")
    match = _CSRF_INPUT.search(form.text)
    token = match.group(1) if match else ""
    client.post(
        "/admin/login/",
        data={
            "username": "admin",
            "password": "admin",
            "csrfmiddlewaretoken": token,
            "next": "/admin/",
        },
        headers={"Referer": client.base_url + "/admin/login/"},
        name="/admin/login/ (POST)",
    )

# Static fallbacks — the customer classes refresh these from the live menu on
# start, so they self-correct against whatever the seed produced.
FALLBACK_SKUS = [
    "PAO-FRANCES",
    "CROISSANT",
    "BAGUETE",
    "BOLO-CENOURA",
]

SEARCH_TERMS = ["pao", "bolo", "croissant", "pastel", "cafe"]


def _extract_skus(payload) -> list[str]:
    """Walk an API projection JSON and collect every product ``sku`` string."""
    found: list[str] = []

    def visit(node):
        if isinstance(node, dict):
            sku = node.get("sku")
            if isinstance(sku, str) and sku:
                found.append(sku)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload)
    # Preserve order, de-duplicate.
    return list(dict.fromkeys(found))


class _CatalogAwareUser(HttpUser):
    """Base user that learns real product SKUs from the live menu projection."""

    abstract = True

    def on_start(self):
        self.skus = list(FALLBACK_SKUS)
        try:
            response = self.client.get("/api/v1/storefront/menu/", name="/api/v1/storefront/menu/")
            if response.ok:
                skus = _extract_skus(response.json())
                if skus:
                    self.skus = skus
        except Exception:
            # Keep the fallbacks; the run still exercises the endpoints.
            pass

    def a_sku(self) -> str:
        return random.choice(self.skus)


# ---------------------------------------------------------------------------
# 1. Browsing (weight=100) — catalog projections + search
# ---------------------------------------------------------------------------


class BrowsingUser(_CatalogAwareUser):
    """Customers browsing the catalog through the API."""

    weight = 100
    wait_time = between(1, 3)

    @task(2)
    def home(self):
        self.client.get("/api/v1/storefront/home/", name="/api/v1/storefront/home/")

    @task(5)
    def menu(self):
        self.client.get("/api/v1/storefront/menu/", name="/api/v1/storefront/menu/")

    @task(3)
    def product_detail(self):
        sku = self.a_sku()
        self.client.get(
            f"/api/v1/storefront/products/{sku}/",
            name="/api/v1/storefront/products/[sku]/",
        )

    @task(2)
    def search(self):
        term = random.choice(SEARCH_TERMS)
        self.client.get(
            f"/api/v1/catalog/products/?search={term}",
            name="/api/v1/catalog/products/?search=",
        )

    @task(1)
    def availability(self):
        sku = self.a_sku()
        self.client.get(
            f"/api/v1/availability/{sku}/",
            name="/api/v1/availability/[sku]/",
        )


# ---------------------------------------------------------------------------
# 2. Checkout (weight=50) — cart mutation + cart/checkout projections
# ---------------------------------------------------------------------------


class CheckoutUser(_CatalogAwareUser):
    """Customers building a cart and reaching the checkout projection.

    The anonymous storefront session authorizes cart mutations without CSRF
    (DRF SessionAuthentication only enforces CSRF for authenticated users), so
    the absolute-quantity PUT is the canonical mutation here. No order is
    committed (checkout commit gates on auth), keeping the run idempotent.
    """

    weight = 50
    wait_time = between(2, 5)

    @task(3)
    def add_to_cart(self):
        sku = self.a_sku()
        # A 409 is the documented stock-conflict contract — a valid response when
        # concurrent carts deplete a SKU, not a backend failure.
        with self.client.put(
            f"/api/v1/cart/skus/{sku}/",
            json={"qty": 1},
            name="/api/v1/cart/skus/[sku]/ (PUT)",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 409):
                response.success()

    @task(2)
    def view_cart(self):
        self.client.get("/api/v1/storefront/cart/", name="/api/v1/storefront/cart/")

    @task(1)
    def checkout_projection(self):
        self.client.get("/api/v1/storefront/checkout/", name="/api/v1/storefront/checkout/")

    @task(1)
    def checkout_draft(self):
        """PATCH the fulfillment draft — read-preview that re-resolves the cart."""
        self.client.patch(
            "/api/v1/checkout/draft/",
            json={"fulfillment_type": "pickup"},
            name="/api/v1/checkout/draft/ (PATCH)",
        )


# ---------------------------------------------------------------------------
# 3. Payment (weight=20) — PIX status polling + tracking
# ---------------------------------------------------------------------------


class PaymentUser(HttpUser):
    """PIX status polling + order tracking — the read-heavy post-checkout phase."""

    weight = 20
    wait_time = between(3, 8)

    @task(3)
    def payment_status_poll(self):
        # Dummy ref — clients poll this endpoint while a PIX is pending; a 404 for
        # an unknown ref still measures the endpoint's latency under load.
        with self.client.get(
            "/api/v1/payment/LOAD-TEST-001/status/",
            name="/api/v1/payment/[ref]/status/",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 404):
                response.success()

    @task(1)
    def tracking(self):
        with self.client.get(
            "/api/v1/tracking/LOAD-TEST-001/",
            name="/api/v1/tracking/[ref]/",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 403, 404):
                response.success()


# ---------------------------------------------------------------------------
# 4. Operator — Django order console + dashboard (weight=10, live post-headless)
# ---------------------------------------------------------------------------


class OperatorUser(HttpUser):
    """Operators on the headless order API (Gestor de Pedidos app)."""

    weight = 10
    wait_time = between(2, 5)

    def on_start(self):
        _admin_login(self.client)

    @task(3)
    def order_queue(self):
        self.client.get("/api/v1/backstage/orders/", name="/api/v1/backstage/orders/")

    @task(2)
    def order_queue_poll(self):
        self.client.get("/api/v1/backstage/orders/", name="/api/v1/backstage/orders/ (poll)")

    @task(1)
    def admin_dashboard(self):
        self.client.get("/admin/", name="/admin/")


# ---------------------------------------------------------------------------
# 5. KDS — headless kitchen display API (weight=30, live post-headless)
# ---------------------------------------------------------------------------


class KDSUser(HttpUser):
    """KDS stations on the headless API (kds-uithing-nuxt app)."""

    weight = 30
    wait_time = between(1, 3)

    def on_start(self):
        _admin_login(self.client)

    @task(3)
    def kds_index(self):
        self.client.get("/api/v1/backstage/kds/", name="/api/v1/backstage/kds/")

    @task(5)
    def kds_board(self):
        ref = random.choice(["paes", "picking", "confeitaria"])
        with self.client.get(
            f"/api/v1/backstage/kds/{ref}/",
            name="/api/v1/backstage/kds/[ref]/",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 404):
                response.success()

    @task(2)
    def production_kds(self):
        # The production floor moved to the fournil. Nuxt app over the headless API.
        self.client.get(
            "/api/v1/backstage/production/kds/",
            name="/api/v1/backstage/production/kds/",
        )
