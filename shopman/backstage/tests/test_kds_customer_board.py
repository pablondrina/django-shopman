from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.projections.kds import build_kds_customer_status
from shopman.shop.models import Shop


def _order(ref: str, status: str, *, fulfillment_type: str = "pickup") -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=status,
        total_q=1500,
        data={
            "fulfillment_type": fulfillment_type,
            "customer": {"name": "Ana Cliente", "phone": "43999990000"},
            "delivery_address": "Rua das Flores, 123",
        },
    )
    OrderItem.objects.create(
        order=order,
        line_id=f"{ref}-1",
        sku="SKU",
        name="Produto",
        qty=1,
        unit_price_q=1500,
        line_total_q=1500,
    )
    return order


@pytest.mark.django_db
def test_customer_board_projection_is_pickup_only_and_privacy_safe() -> None:
    _order("PICKUP-PREP", Order.Status.PREPARING)
    _order("PICKUP-READY", Order.Status.READY)
    _order("DELIVERY-READY", Order.Status.READY, fulfillment_type="delivery")

    board = build_kds_customer_status()

    assert [order.ref for order in board.preparing] == ["PICKUP-PREP"]
    assert [order.ref for order in board.ready] == ["PICKUP-READY"]
    assert all(not hasattr(order, "customer_name") for order in (*board.preparing, *board.ready))


@pytest.mark.django_db
def test_customer_board_routes_render_without_pii(client) -> None:
    Shop.objects.create(name="Test Shop", brand_name="Test")
    _order("PICKUP-READY", Order.Status.READY)

    response = client.get(reverse("backstage:kds_customer_board"))
    partial = client.get(reverse("backstage:kds_customer_board_orders"))

    assert response.status_code == 200
    assert partial.status_code == 200
    html = response.content.decode() + partial.content.decode()
    assert "PICKUP-READY" in html
    assert "Pronto para retirar" in html
    assert "Ana Cliente" not in html
    assert "43999990000" not in html
    assert "Rua das Flores" not in html
    assert "R$" not in html


def test_customer_board_listens_to_order_sse_with_polling_fallback() -> None:
    source = Path("shopman/backstage/templates/runtime/kds_customer/board.html").read_text()

    assert "hx-ext=\"sse\"" in source
    assert "kind='orders'" in source
    assert "sse:backstage-orders-update" in source
    assert "every 10s" in source
    assert 'aria-live="polite"' in source
