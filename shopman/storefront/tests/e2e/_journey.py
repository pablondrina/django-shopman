"""Journey helpers for the persona E2E suite.

Every helper drives the same surface the Nuxt storefront consumes: JSON over
``/api/v1/...`` via a ``django.test.Client``. Seeding builds a real catalog
(Shop + Channel + Product + Listing + stock), so availability, holds and pricing
behave exactly as they do in production.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

from django.test import Client
from django.utils import timezone

WEB_CHANNEL = "web"
DEFAULT_PHONE = "+5543999990001"
POSITION_REF = "loja"

# Mirrors the seed's ``web`` ("Loja online") channel config so journeys exercise
# the real remote lifecycle: optimistic auto-confirm, pix/card paid after the
# store confirms (post_commit), D-1 stock hidden, 30-min holds.
WEB_CHANNEL_CONFIG = {
    "confirmation": {"mode": "auto_confirm", "timeout_minutes": 5, "stale_new_alert_minutes": 10},
    "payment": {"method": ["pix", "card"], "timing": "post_commit", "timeout_minutes": 10},
    "stock": {"excluded_positions": ["ontem"], "hold_ttl_minutes": 30},
}


# ── seeding ──────────────────────────────────────────────────────────────────


def seed_shop(**overrides):
    """Create the singleton Shop with sensible storefront defaults."""
    from shopman.shop.models import Shop

    fields = {
        "name": "Padaria Demo",
        "brand_name": "Padaria Demo",
        "short_name": "Demo",
        "phone": "554333231997",
    }
    fields.update(overrides)
    return Shop.objects.create(**fields)


def seed_channel(ref: str = WEB_CHANNEL, name: str = "Loja Online", config: dict | None = None):
    """Create a Channel with an explicit ``config`` dict (verbatim)."""
    from shopman.shop.models import Channel

    return Channel.objects.create(ref=ref, name=name, config=config or {})


def seed_web_channel():
    """Create the storefront ``web`` channel with the production remote config."""
    return seed_channel(WEB_CHANNEL, "Loja online", config=dict(WEB_CHANNEL_CONFIG))


def seed_listing(ref: str = WEB_CHANNEL, name: str = "Web"):
    from shopman.offerman.models import Listing

    return Listing.objects.get_or_create(
        ref=ref, defaults={"name": name, "is_active": True, "priority": 10}
    )[0]


def seed_collection(ref: str = "paes", name: str = "Pães", sort_order: int = 1):
    from shopman.offerman.models import Collection

    return Collection.objects.get_or_create(
        ref=ref, defaults={"name": name, "is_active": True, "sort_order": sort_order}
    )[0]


def seed_product(
    sku: str,
    name: str,
    price_q: int,
    *,
    listing=None,
    collection=None,
    stock_qty: Decimal | int | None = None,
    plan_qty: Decimal | int | None = None,
    plan_date: date | None = None,
    shelf_life_days: int | None = None,
    sort_order: int = 1,
    **product_kwargs,
):
    """Create a sellable, published product wired into a listing/collection.

    ``stock_qty`` receives ready stock now; ``plan_qty`` plans a future batch
    (for preorder journeys). ``shelf_life_days`` marks the product perishable
    when set (``None`` = non-perishable / shelf-stable).
    """
    from shopman.offerman.models import CollectionItem, ListingItem, Product

    listing = listing or seed_listing()
    product = Product.objects.create(
        sku=sku,
        name=name,
        base_price_q=price_q,
        is_published=True,
        is_sellable=True,
        shelf_life_days=shelf_life_days,
        **product_kwargs,
    )
    ListingItem.objects.create(
        listing=listing,
        product=product,
        price_q=price_q,
        is_published=True,
        is_sellable=True,
    )
    if collection is not None:
        CollectionItem.objects.create(collection=collection, product=product, sort_order=sort_order)
    if stock_qty is not None:
        seed_stock(sku, stock_qty)
    if plan_qty is not None:
        plan_stock(product, plan_qty, plan_date or timezone.localdate())
    return product


def _position(ref: str = POSITION_REF):
    from shopman.stockman.models import Position, PositionKind

    return Position.objects.get_or_create(
        ref=ref,
        defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )[0]


def seed_stock(sku: str, qty: Decimal | int, *, position_ref: str = POSITION_REF, target_date: date | None = None):
    """Receive ready-to-sell stock for a SKU at the saleable position."""
    from shopman.stockman import stock

    stock.receive(
        quantity=Decimal(str(qty)),
        sku=sku,
        position=_position(position_ref),
        target_date=target_date or timezone.localdate(),
        reason="e2e persona seed",
    )


def plan_stock(product, qty: Decimal | int, target_date: date, *, position_ref: str = POSITION_REF):
    """Plan a future production batch (planned Quant) for preorder availability."""
    from shopman.stockman.services.planning import StockPlanning

    StockPlanning.plan(
        Decimal(str(qty)),
        product,
        target_date,
        position=_position(position_ref),
        reason="e2e persona planned batch",
    )


# ── customers & auth ─────────────────────────────────────────────────────────


def make_customer(
    *,
    ref: str | None = None,
    first_name: str = "Ana",
    last_name: str = "Silva",
    phone: str = DEFAULT_PHONE,
    email: str = "ana@example.com",
    group=None,
):
    from shopman.guestman.models import Customer

    fields = {
        "ref": ref or Customer.generate_ref(),
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "email": email,
    }
    if group is not None:
        fields["group"] = group
    return Customer.objects.create(**fields)


def authenticate(client: Client, customer) -> None:
    """Bind ``customer`` to the client session (Pattern A: user bridge).

    After this, requests via ``client`` have ``request.customer`` populated and
    ``get_authenticated_customer`` returns the ``Customer`` — no OTP/HTTP needed.
    """
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=customer.email or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")


def otp_login(client: Client, phone: str = DEFAULT_PHONE) -> dict:
    """Drive the real OTP login HTTP surface (request-code → verify-code).

    Seeds a ``VerificationCode`` directly (bypassing SMS/WhatsApp send + the
    per-IP throttle) and posts the raw code, exactly as the store's login page
    would after the customer types it.
    """
    from shopman.doorman.models import VerificationCode
    from shopman.doorman.models.verification_code import generate_raw_code

    raw_code, digest = generate_raw_code()
    VerificationCode.objects.create(
        target_value=phone,
        purpose=VerificationCode.Purpose.LOGIN,
        code_hash=digest,
    )
    resp = client.post(
        "/api/v1/auth/verify-code/",
        data=json.dumps({"phone": phone, "code": raw_code}),
        content_type="application/json",
    )
    return {"status": resp.status_code, "body": resp.json() if resp.content else {}}


# ── cart / checkout / payment / tracking ─────────────────────────────────────


def get_json(client: Client, url: str):
    resp = client.get(url)
    return resp.status_code, (resp.json() if resp.content else None)


def set_cart_qty(client: Client, sku: str, qty: int):
    """PUT an absolute cart quantity for a SKU. Returns (status, body)."""
    resp = client.put(
        f"/api/v1/cart/skus/{sku}/",
        data=json.dumps({"qty": qty}),
        content_type="application/json",
    )
    return resp.status_code, (resp.json() if resp.content else None)


def apply_coupon(client: Client, code: str):
    resp = client.post(
        "/api/v1/cart/coupon/",
        data=json.dumps({"code": code}),
        content_type="application/json",
    )
    return resp.status_code, (resp.json() if resp.content else None)


def last_pickup_slot() -> str:
    """The latest configured pickup slot — always selectable for *today*
    regardless of wall-clock, so today-pickup checkouts are not time-flaky."""
    from shopman.storefront.services.pickup_slots import get_slots

    return get_slots()[-1]["ref"]


def first_pickup_slot() -> str:
    from shopman.storefront.services.pickup_slots import get_slots

    return get_slots()[0]["ref"]


def checkout(client: Client, *, name="Ana Silva", phone=DEFAULT_PHONE, **overrides):
    """POST /api/v1/checkout/. Returns (status, body).

    Defaults to a today pickup paid in cash; override any serializer field
    (``fulfillment_type``, ``payment_method``, ``delivery_date``,
    ``delivery_time_slot``, ``delivery_address``, ``use_loyalty``, …).
    """
    payload = {
        "name": name,
        "phone": phone,
        "fulfillment_type": "pickup",
        "payment_method": "cash",
    }
    payload.update(overrides)
    if payload.get("fulfillment_type") == "pickup" and "delivery_time_slot" not in payload:
        payload["delivery_time_slot"] = last_pickup_slot()
        payload.setdefault("delivery_date", timezone.localdate().isoformat())
    resp = client.post(
        "/api/v1/checkout/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    return resp.status_code, (resp.json() if resp.content else None)


def checkout_committed(client: Client, capture_ctx, **kwargs):
    """Checkout with the on-commit lifecycle dispatch actually executed.

    Django test transactions do not run ``transaction.on_commit`` callbacks, so
    the commit-phase pipeline (loyalty redeem, notifications, …) never fires.
    Wrapping the POST in ``django_capture_on_commit_callbacks(execute=True)``
    runs them, mirroring production."""
    with capture_ctx(execute=True):
        return checkout(client, **kwargs)


def mock_confirm_payment(client: Client, ref: str):
    """POST the DEBUG-only mock payment confirmation (settles a pix/card intent)."""
    resp = client.post(f"/api/v1/payment/{ref}/mock-confirm/")
    return resp.status_code, (resp.json() if resp.content else None)


def get_payment(client: Client, ref: str):
    return get_json(client, f"/api/v1/payment/{ref}/")


def get_tracking(client: Client, ref: str):
    return get_json(client, f"/api/v1/tracking/{ref}/")


def checkout_draft(client: Client, *, fulfillment_type="delivery", structured: dict | None = None):
    """PATCH the delivery draft to re-price the cart (delivery fee/zone preview)."""
    body = {"fulfillment_type": fulfillment_type}
    if structured is not None:
        body["delivery_address_structured"] = structured
    resp = client.patch(
        "/api/v1/checkout/draft/",
        data=json.dumps(body),
        content_type="application/json",
    )
    return resp.status_code, (resp.json() if resp.content else None)


def toggle_loyalty(client: Client, enabled: bool):
    resp = client.patch(
        "/api/v1/checkout/loyalty/",
        data=json.dumps({"enabled": enabled}),
        content_type="application/json",
    )
    return resp.status_code, (resp.json() if resp.content else None)


def reorder(client: Client, ref: str, *, mode: str | None = None):
    body = {}
    if mode is not None:
        body["mode"] = mode
    resp = client.post(
        f"/api/v1/orders/{ref}/reorder/",
        data=json.dumps(body),
        content_type="application/json",
    )
    return resp.status_code, (resp.json() if resp.content else None)


def tomorrow_iso() -> str:
    return (timezone.localdate() + timedelta(days=1)).isoformat()


def days_ahead_iso(n: int) -> str:
    return (timezone.localdate() + timedelta(days=n)).isoformat()


# ── promotions / coupons / loyalty / favorites / addresses / reorder ─────────


def seed_promotion(
    *,
    name: str = "Promoção",
    kind: str = "percent",
    value: int = 20,
    skus: list[str] | None = None,
    collections: list[str] | None = None,
    customer_segments: list[str] | None = None,
    min_order_q: int = 0,
    fulfillment_types: list[str] | None = None,
):
    """Create a Promotion. With no Coupon attached it applies automatically."""
    from shopman.storefront.models import Promotion

    now = timezone.now()
    return Promotion.objects.create(
        name=name,
        type=Promotion.PERCENT if kind == "percent" else Promotion.FIXED,
        value=value,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        skus=skus or [],
        collections=collections or [],
        customer_segments=customer_segments or [],
        min_order_q=min_order_q,
        fulfillment_types=fulfillment_types or [],
    )


def seed_coupon(code: str, *, max_uses: int = 0, **promotion_kwargs):
    """Create a Promotion + Coupon. ``code`` is stored/looked-up uppercase."""
    from shopman.storefront.models import Coupon

    promo = seed_promotion(**promotion_kwargs)
    coupon = Coupon.objects.create(code=code.upper(), promotion=promo, max_uses=max_uses)
    return coupon


def give_loyalty(customer, points_balance: int):
    """Grant a redeemable loyalty balance (points map 1:1 to centavos)."""
    from shopman.guestman.contrib.loyalty.models import LoyaltyAccount

    return LoyaltyAccount.objects.create(customer=customer, points_balance=points_balance)


def seed_address(customer, *, is_default: bool = True, **overrides):
    from shopman.guestman.models import CustomerAddress

    fields = {
        "customer": customer,
        "label": "home",
        "formatted_address": "Rua das Flores, 123, Centro, Londrina - PR, 86020-000",
        "route": "Rua das Flores",
        "street_number": "123",
        "neighborhood": "Centro",
        "city": "Londrina",
        "state_code": "PR",
        "postal_code": "86020-000",
        "latitude": -23.31,
        "longitude": -51.16,
        "place_id": "test-place-id",
        "is_default": is_default,
    }
    fields.update(overrides)
    return CustomerAddress.objects.create(**fields)


def add_favorite(customer, sku: str):
    from shopman.storefront.models import CustomerFavorite

    return CustomerFavorite.objects.create(customer_ref=customer.ref, sku=sku)


def seed_past_order(customer, *, ref: str, items: list[dict], channel_ref: str = WEB_CHANNEL):
    """Seed a COMPLETED order owned by ``customer`` (for reorder journeys)."""
    from decimal import Decimal as _D

    from shopman.orderman.models import Order, OrderItem

    total_q = sum(int(i.get("line_total_q") or i["unit_price_q"] * i.get("qty", 1)) for i in items)
    order = Order.objects.create(
        ref=ref,
        channel_ref=channel_ref,
        session_key=f"sk-{ref.lower()}",
        status=Order.Status.COMPLETED,
        snapshot={"items": items, "pricing": {"total_q": total_q}},
        data={"customer_ref": customer.ref},
        total_q=total_q,
    )
    for idx, item in enumerate(items, start=1):
        qty = _D(str(item.get("qty", 1)))
        unit_price_q = int(item["unit_price_q"])
        OrderItem.objects.create(
            order=order,
            line_id=item.get("line_id") or f"L{idx}",
            sku=item["sku"],
            name=item.get("name", item["sku"]),
            qty=qty,
            unit_price_q=unit_price_q,
            line_total_q=int(item.get("line_total_q") or unit_price_q * int(qty)),
            meta=item.get("meta", {}),
        )
    return order


# ── bundles ──────────────────────────────────────────────────────────────────


def seed_bundle(sku, name, price_q, components, *, listing=None, collection=None, **product_kwargs):
    """Create a bundle Product (Product + ProductComponent rows) on the listing.

    ``components`` is a list of ``(component_product, qty)`` tuples; component
    products must already exist. The bundle itself is what gets listed/sold.
    """
    from decimal import Decimal as _D

    from shopman.offerman.models import ProductComponent

    combo = seed_product(
        sku, name, price_q, listing=listing, collection=collection, **product_kwargs
    )
    for component, qty in components:
        ProductComponent.objects.create(parent=combo, component=component, qty=_D(str(qty)))
    return combo


# ── delivery ─────────────────────────────────────────────────────────────────


def seed_delivery_zone(shop, *, match_value="860", fee_q=600, zone_type="cep_prefix", mode="override", name="Zona"):
    from shopman.storefront.models import DeliveryZone

    return DeliveryZone.objects.create(
        shop=shop,
        name=name,
        zone_type=zone_type,
        match_value=match_value,
        mode=mode,
        fee_q=fee_q,
    )


# ── order lifecycle (operator side, for full payment journeys) ───────────────


def confirm_order(order, callbacks_ctx, *, actor="test:operator"):
    """Optimistic confirmation: transition NEW → CONFIRMED, firing on-commit
    callbacks (the on_confirmed pipeline, e.g. pix.generate). ``callbacks_ctx``
    is the ``django_capture_on_commit_callbacks`` fixture."""
    from shopman.orderman.models import Order

    with callbacks_ctx(execute=True):
        order.transition_status(Order.Status.CONFIRMED, actor=actor)
    order.refresh_from_db()
    return order


def process_directives(limit: int = 100):
    """Drain due (queued) directives synchronously — the maintenance worker's job."""
    from django.core.management import call_command

    call_command("process_directives", limit=limit)
