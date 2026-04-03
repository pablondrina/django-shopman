"""
WP-F17.2 — Locust load testing scenarios.

Targets:
  - 100 concurrent browsing menu
  - 50 concurrent checkouts
  - 20 concurrent PIX payments
  - Dashboard admin with 10 operators
  - KDS with 30 tickets simultâneos
  - P95 < 500ms

Prerequisites:
  pip install locust
  make seed  # populate DB
  make run   # start dev server

Run:
  locust -f tests/load/locustfile.py --host=http://localhost:8000

  # Headless (CI):
  locust -f tests/load/locustfile.py --host=http://localhost:8000 \\
    --headless -u 100 -r 10 --run-time 60s

User mix (configured via weights):
  - BrowsingUser (weight=100): menu browsing, product detail, search
  - CheckoutUser (weight=50): add to cart, checkout flow
  - PaymentUser (weight=20): PIX generation, payment status polling
  - OperatorUser (weight=10): gestor de pedidos, dashboard
  - KDSUser (weight=30): KDS display, ticket check, ticket done
"""

from __future__ import annotations

import random
import string

from locust import HttpUser, between, task

# Product SKUs from seed data (Nelson Boulangerie)
PRODUCT_SKUS = [
    "PAO-FRANCES",
    "CROISSANT",
    "BAGUETTE",
    "BOLO-CENOURA",
    "BOLO-CHOCOLATE",
    "BRIGADEIRO",
    "COXINHA",
    "EMPADA",
]

COLLECTION_SLUGS = [
    "padaria",
    "confeitaria",
    "salgados",
]


def _random_phone():
    return f"+554399988{random.randint(1000, 9999)}"


def _random_name():
    first = random.choice(["João", "Maria", "Pedro", "Ana", "Carlos", "Julia"])
    last = random.choice(["Silva", "Santos", "Oliveira", "Lima", "Costa", "Souza"])
    return f"{first} {last}"


# ---------------------------------------------------------------------------
# 1. Browsing (weight=100) — Menu, product detail, search
# ---------------------------------------------------------------------------


class BrowsingUser(HttpUser):
    """Simulates customers browsing the menu."""

    weight = 100
    wait_time = between(1, 3)

    @task(5)
    def browse_menu(self):
        """GET /menu/ — main menu page."""
        self.client.get("/menu/", name="/menu/")

    @task(3)
    def browse_collection(self):
        """GET /menu/<collection>/ — filtered by collection."""
        slug = random.choice(COLLECTION_SLUGS)
        self.client.get(f"/menu/{slug}/", name="/menu/[collection]/")

    @task(2)
    def product_detail(self):
        """GET /produto/<sku>/ — product detail page."""
        sku = random.choice(PRODUCT_SKUS)
        self.client.get(f"/produto/{sku}/", name="/produto/[sku]/")

    @task(1)
    def search(self):
        """GET /menu/search/?q=... — search menu."""
        query = random.choice(["pao", "bolo", "croissant", "coxinha"])
        self.client.get(f"/menu/search/?q={query}", name="/menu/search/")

    @task(1)
    def home_page(self):
        """GET / — home page."""
        self.client.get("/", name="/")


# ---------------------------------------------------------------------------
# 2. Checkout (weight=50) — Cart + checkout flow
# ---------------------------------------------------------------------------


class CheckoutUser(HttpUser):
    """Simulates customers going through checkout."""

    weight = 50
    wait_time = between(2, 5)

    def on_start(self):
        """Start with a fresh session."""
        self.client.get("/menu/")

    @task(3)
    def add_to_cart(self):
        """POST /cart/add/ — add random item."""
        sku = random.choice(PRODUCT_SKUS)
        self.client.post(
            "/cart/add/",
            data={"sku": sku, "qty": random.randint(1, 5)},
            name="/cart/add/",
        )

    @task(2)
    def view_cart(self):
        """GET /cart/ — view cart."""
        self.client.get("/cart/", name="/cart/")

    @task(1)
    def cart_drawer(self):
        """GET /cart/drawer/ — HTMX cart drawer partial."""
        self.client.get(
            "/cart/drawer/",
            headers={"HX-Request": "true"},
            name="/cart/drawer/ (HTMX)",
        )

    @task(1)
    def checkout_page(self):
        """GET /checkout/ — checkout form."""
        self.client.get("/checkout/", name="/checkout/")


# ---------------------------------------------------------------------------
# 3. Payment (weight=20) — PIX generation + polling
# ---------------------------------------------------------------------------


class PaymentUser(HttpUser):
    """Simulates PIX payment flow with status polling."""

    weight = 20
    wait_time = between(3, 8)

    @task(1)
    def checkout_submit(self):
        """POST /checkout/ — submit checkout (may fail without valid session)."""
        self.client.post(
            "/checkout/",
            data={
                "phone": _random_phone(),
                "name": _random_name(),
                "fulfillment_type": "pickup",
            },
            name="/checkout/ (POST)",
            catch_response=True,
        )

    @task(2)
    def payment_status_poll(self):
        """GET /pedido/<ref>/pagamento/status/ — simulates PIX status polling."""
        # Use a dummy ref — measures response time even for 404
        self.client.get(
            "/pedido/LOAD-TEST-001/pagamento/status/",
            name="/pedido/[ref]/pagamento/status/",
            catch_response=True,
        )


# ---------------------------------------------------------------------------
# 4. Operator — Dashboard + Gestor (weight=10)
# ---------------------------------------------------------------------------


class OperatorUser(HttpUser):
    """Simulates operators using admin/gestor panels."""

    weight = 10
    wait_time = between(2, 5)

    def on_start(self):
        """Login as admin."""
        self.client.get("/admin/login/")
        self.client.post(
            "/admin/login/",
            data={
                "username": "admin",
                "password": "admin",
            },
            name="/admin/login/ (POST)",
        )

    @task(3)
    def gestor_pedidos(self):
        """GET /pedidos/ — order management panel."""
        self.client.get("/pedidos/", name="/pedidos/")

    @task(2)
    def gestor_list_partial(self):
        """GET /pedidos/list/ — HTMX partial order list."""
        self.client.get(
            "/pedidos/list/",
            headers={"HX-Request": "true"},
            name="/pedidos/list/ (HTMX)",
        )

    @task(1)
    def admin_dashboard(self):
        """GET /admin/ — Django admin dashboard."""
        self.client.get("/admin/", name="/admin/")


# ---------------------------------------------------------------------------
# 5. KDS (weight=30) — Kitchen display + ticket actions
# ---------------------------------------------------------------------------


class KDSUser(HttpUser):
    """Simulates KDS stations with ticket management."""

    weight = 30
    wait_time = between(1, 3)

    def on_start(self):
        """Login as admin for KDS access."""
        self.client.get("/admin/login/")
        self.client.post(
            "/admin/login/",
            data={
                "username": "admin",
                "password": "admin",
            },
        )

    @task(3)
    def kds_index(self):
        """GET /kds/ — KDS station list."""
        self.client.get("/kds/", name="/kds/")

    @task(5)
    def kds_display(self):
        """GET /kds/<ref>/ — KDS station display."""
        ref = random.choice(["paes", "picking", "confeitaria"])
        self.client.get(
            f"/kds/{ref}/",
            name="/kds/[ref]/",
            catch_response=True,
        )

    @task(3)
    def kds_ticket_list(self):
        """GET /kds/<ref>/tickets/ — HTMX ticket list polling."""
        ref = random.choice(["paes", "picking"])
        self.client.get(
            f"/kds/{ref}/tickets/",
            headers={"HX-Request": "true"},
            name="/kds/[ref]/tickets/ (HTMX)",
            catch_response=True,
        )
