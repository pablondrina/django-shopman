"""Persona 3 — Nelson employee (staff discount at the counter).

BOUNDARY FINDING: the employee discount is a POS/counter concept and is NOT
reachable through the storefront. The discount modifier fires only when
``session.data["customer"]["group"] == "staff"``, and that key is written
exclusively by the POS attach-customer path (``shop/services/pos.py``). The
storefront hardcodes the ``web`` channel and writes only ``{name, phone}`` into
the session, so a staff member ordering on the public store is charged full price.

These tests pin that boundary from both sides:
  * through the storefront API a staff customer gets NO discount (correct — the
    public store must not leak staff pricing);
  * the discount mechanism itself works when driven the way the POS drives it
    (session data carrying ``customer.group == "staff"``).
"""

from __future__ import annotations

import pytest
from shopman.guestman.models import Customer, CustomerGroup
from shopman.orderman.models import Order, Session

from . import _journey as J

pytestmark = pytest.mark.django_db

SKU = "PAO-STAFF"


def _seed():
    J.seed_shop()
    J.seed_web_channel()
    collection = J.seed_collection()
    J.seed_product(SKU, "Pão", 1000, collection=collection, stock_qty=20)


def _staff_customer():
    group = CustomerGroup.objects.create(ref="staff", name="Funcionários")
    return Customer.objects.create(
        ref="CUST-STAFF-1", first_name="Carlos", last_name="Silva",
        phone=J.DEFAULT_PHONE, group=group,
    )


# ── the boundary, through the storefront ─────────────────────────────────────


def test_staff_customer_gets_no_discount_on_storefront(client):
    """A staff member ordering on the public store pays full price — the
    storefront never writes ``customer.group`` into the session."""
    _seed()
    staff = _staff_customer()
    J.authenticate(client, staff)

    J.set_cart_qty(client, SKU, 1)
    status, order_resp = J.checkout(client, name="Carlos Silva", payment_method="cash")
    assert status == 201, order_resp

    order = Order.objects.get(ref=order_resp["order_ref"])
    # Full price: R$10,00, no 20% employee discount.
    assert order.total_q == 1000
    # The order's customer sub-dict carries no group — the modifier could never fire.
    assert "group" not in (order.data.get("customer") or {})


# ── the mechanism, driven the way the POS drives it ──────────────────────────


def test_employee_discount_applies_when_session_carries_staff_group(client):
    """The modifier discounts every line when the session data marks the
    customer as staff — this is what the POS attach-customer path produces."""
    from shopman.shop.models import Channel
    from shopman.shop.modifiers import EmployeeDiscountModifier

    _seed()
    pdv = Channel.objects.create(ref="pdv", name="PDV", config={"payment": {"method": "cash"}})
    session = Session.objects.create(
        session_key="POS-STAFF-1",
        channel_ref="pdv",
        state="open",
        rev=1,
        items=[{"line_id": "L1", "sku": SKU, "qty": 1, "unit_price_q": 1000, "line_total_q": 1000}],
        data={"customer": {"name": "Carlos", "group": "staff"}},
        pricing={},
    )

    EmployeeDiscountModifier(discount_percent=20).apply(channel=pdv, session=session, ctx={})

    session.refresh_from_db()
    assert session.items[0]["unit_price_q"] == 800  # 20% off R$10,00
    assert session.pricing["employee_discount"]["total_discount_q"] == 200
    assert session.pricing["employee_discount"]["label"] == "Desconto funcionário"


def test_non_staff_group_gets_no_employee_discount(client):
    """A non-staff group leaves prices untouched."""
    from shopman.shop.models import Channel
    from shopman.shop.modifiers import EmployeeDiscountModifier

    _seed()
    pdv = Channel.objects.create(ref="pdv", name="PDV", config={"payment": {"method": "cash"}})
    session = Session.objects.create(
        session_key="POS-REG-1",
        channel_ref="pdv",
        state="open",
        rev=1,
        items=[{"line_id": "L1", "sku": SKU, "qty": 1, "unit_price_q": 1000, "line_total_q": 1000}],
        data={"customer": {"name": "Ana", "group": "regular"}},
        pricing={},
    )

    EmployeeDiscountModifier(discount_percent=20).apply(channel=pdv, session=session, ctx={})

    session.refresh_from_db()
    assert session.items[0]["unit_price_q"] == 1000  # untouched
    assert "employee_discount" not in (session.pricing or {})
