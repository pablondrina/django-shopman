"""Headless operator orders API contract (api/v1/backstage/orders/*).

Mirrors the Admin order console actions on the REST surface that the dedicated
Gestor de Pedidos (orders-uithing-nuxt) consumes. The gate is the existing
``shop.manage_orders`` permission (granted to the Caixa/Gerente groups), so a
non-superuser staff operator with that permission can drive the queue; staff
without it — and non-staff — are blocked.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.orderman.models import Directive, Order, OrderItem

from shopman.shop.models import Shop


def _manage_orders_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename="manage_orders",
    )


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def operator(db, shop):
    """Floor operator: staff + manage_orders, NOT superuser."""
    user = User.objects.create_user("orders-api", password="pw", is_staff=True)
    user.user_permissions.add(_manage_orders_perm())
    return user


@pytest.fixture
def plain_staff(db, shop):
    """Staff user WITHOUT manage_orders — must be blocked."""
    return User.objects.create_user("plain-staff", password="pw", is_staff=True)


def _order(ref: str, status: str = "confirmed", **data_extra) -> Order:
    data = {"customer": {"name": "Ana"}, "payment": {"method": "cash"}}
    data.update(data_extra)
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=status,
        total_q=1500,
        data=data,
    )
    OrderItem.objects.create(
        order=order, line_id="1", sku="SKU", name="Produto", qty=1, unit_price_q=1500, line_total_q=1500
    )
    return order


@pytest.fixture
def order(db):
    return _order("ORD-API-1")


# ── Permission gate (the WP-G1 fix: was dangling, superuser-only) ──────────


@pytest.mark.django_db
def test_queue_requires_manage_orders(client, operator, plain_staff, order):
    client.force_login(plain_staff)
    assert client.get(reverse("api-backstage-orders")).status_code == 403

    client.force_login(operator)
    response = client.get(reverse("api-backstage-orders"))
    assert response.status_code == 200
    assert "queue" in response.json()


@pytest.mark.django_db
def test_queue_blocks_non_staff(client, db, shop, order):
    customer = User.objects.create_user("customer", password="pw", is_staff=False)
    client.force_login(customer)
    assert client.get(reverse("api-backstage-orders")).status_code == 403


@pytest.mark.django_db
def test_all_action_endpoints_require_permission(client, plain_staff, order):
    client.force_login(plain_staff)
    ref = order.ref
    action_urls = [
        reverse("api-backstage-order-advance", args=[ref]),
        reverse("api-backstage-order-confirm", args=[ref]),
        reverse("api-backstage-order-reject", args=[ref]),
        reverse("api-backstage-order-cancel", args=[ref]),
        reverse("api-backstage-order-settle-delivery-cash", args=[ref]),
        reverse("api-backstage-order-requeue-fiscal", args=[ref]),
        reverse("api-backstage-order-notes", args=[ref]),
    ]
    for url in action_urls:
        assert client.post(url).status_code == 403, url


# ── Read surface ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_order_detail_returns_projection(client, operator, order):
    client.force_login(operator)
    response = client.get(reverse("api-backstage-order-detail", args=[order.ref]))
    assert response.status_code == 200
    payload = response.json()["order"]
    assert payload["ref"] == order.ref
    assert any(item["sku"] == "SKU" for item in payload["items"])


@pytest.mark.django_db
def test_order_detail_unknown_ref_is_404(client, operator):
    client.force_login(operator)
    assert client.get(reverse("api-backstage-order-detail", args=["NOPE"])).status_code == 404


# ── Write actions ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_advance_confirmed_order(client, operator, order):
    client.force_login(operator)
    response = client.post(reverse("api-backstage-order-advance", args=[order.ref]))
    assert response.status_code == 200
    assert response.json() == {"ok": True, "ref": order.ref}
    order.refresh_from_db()
    assert order.status == "preparing"


@pytest.mark.django_db
def test_reject_requires_reason(client, operator, order):
    client.force_login(operator)
    response = client.post(reverse("api-backstage-order-reject", args=[order.ref]))
    assert response.status_code == 400
    assert "detail" in response.json()


@pytest.mark.django_db
def test_save_notes_persists(client, operator, order):
    client.force_login(operator)
    response = client.post(reverse("api-backstage-order-notes", args=[order.ref]), {"notes": "Separar"})
    assert response.status_code == 200
    order.refresh_from_db()
    assert order.data["internal_notes"] == "Separar"


@pytest.mark.django_db
def test_requeue_fiscal_requeues_failed_directive(client, operator):
    order = _order("ORD-API-FISCAL", fiscal={"issue_document": True})
    directive = Directive.objects.create(
        topic="fiscal.emit_nfce",
        status="failed",
        payload={"order_ref": order.ref},
        last_error="Rejeição",
        error_code="terminal",
    )
    client.force_login(operator)
    response = client.post(reverse("api-backstage-order-requeue-fiscal", args=[order.ref]))
    assert response.status_code == 200
    directive.refresh_from_db()
    assert directive.status == "queued"
    assert directive.last_error == ""


@pytest.mark.django_db
def test_settle_delivery_cash_rejects_without_open_shift(client, operator):
    """Endpoint is wired and maps the service guard to a 400 (not a 500)."""
    order = _order(
        "ORD-API-COD",
        status="dispatched",
        fulfillment_type="delivery",
        payment={"method": "cash", "collection": "on_delivery"},
    )
    client.force_login(operator)
    response = client.post(
        reverse("api-backstage-order-settle-delivery-cash", args=[order.ref]),
        {"amount": "15,00"},
    )
    assert response.status_code == 400
    assert "detail" in response.json()
