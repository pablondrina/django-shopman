"""End-to-end guardrails for AVAILABILITY-PLAN WP-AV-14.

These tests intentionally use Django's Client and projection builders instead
of Playwright. The plan needs reliable coverage in the default framework gate;
browser screenshots remain a separate Omotenashi QA concern.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import Client, RequestFactory
from django.utils import timezone
from shopman.guestman.models import Customer
from shopman.offerman.models import AvailabilityPolicy, CollectionItem, ListingItem, Product
from shopman.orderman.models import Session
from shopman.stockman.models import Hold

from shopman.shop.projections.types import Availability
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.projections import build_cart, build_catalog

pytestmark = pytest.mark.django_db


DOORMAN_SETTINGS = {
    "CUSTOMER_RESOLVER_CLASS": "shopman.guestman.adapters.auth.CustomerResolver",
    "MESSAGE_SENDER_CLASS": "shopman.doorman.senders.LogSender",
    "DEVICE_TRUST_COOKIE_NAME": "doorman_dt",
    "LOGOUT_REDIRECT_URL": "/",
}

AUTH_BACKENDS = [
    "shopman.doorman.backends.PhoneOTPBackend",
    "django.contrib.auth.backends.ModelBackend",
]


@pytest.fixture(autouse=True)
def _reset_stockman_sku_validator():
    from shopman.stockman.adapters.sku_validation import reset_sku_validator

    reset_sku_validator()
    yield
    reset_sku_validator()


def _use_offerman_sku_validator(settings) -> None:
    from shopman.stockman.adapters.sku_validation import reset_sku_validator

    settings.STOCKMAN = {
        "SKU_VALIDATOR": "shopman.offerman.adapters.sku_validator.SkuValidator",
    }
    reset_sku_validator()


def _make_product(
    sku: str,
    name: str,
    *,
    price_q: int = 900,
    availability_policy: str = AvailabilityPolicy.PLANNED_OK,
) -> Product:
    return Product.objects.create(
        sku=sku,
        name=name,
        base_price_q=price_q,
        availability_policy=availability_policy,
        is_published=True,
        is_sellable=True,
    )


def _publish(listing, product: Product, *, price_q: int | None = None) -> None:
    ListingItem.objects.get_or_create(
        listing=listing,
        product=product,
        defaults={
            "price_q": price_q if price_q is not None else product.base_price_q,
            "is_published": True,
            "is_sellable": True,
        },
    )


def _categorize(collection, product: Product, *, sort_order: int = 1) -> None:
    CollectionItem.objects.get_or_create(
        collection=collection,
        product=product,
        defaults={"sort_order": sort_order},
    )


def _seed_stock(sku: str, qty: Decimal):
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={
            "name": "Loja Principal",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    return stock.receive(
        quantity=qty,
        sku=sku,
        position=position,
        target_date=None,
        reason="availability plan e2e seed",
    )


def _seed_tracked_sold_out(sku: str) -> None:
    """Create a real Stockman footprint with zero remaining stock."""
    from shopman.stockman import stock

    quant = _seed_stock(sku, Decimal("1"))
    stock.issue(
        quantity=Decimal("1"),
        quant=quant,
        reason="availability plan e2e sold out seed",
    )


def _request_with_session(client: Client, path: str = "/cart/"):
    request = RequestFactory().get(path)
    request.session = client.session  # type: ignore[attr-defined]
    return request


def _login_as_customer(client: Client, customer: Customer, settings) -> None:
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    settings.DOORMAN = DOORMAN_SETTINGS
    settings.AUTHENTICATION_BACKENDS = AUTH_BACKENDS

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=customer.email or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")


def _open_cart_session(client: Client) -> Session:
    return Session.objects.get(
        session_key=client.session["cart_session_key"],
        channel_ref=STOREFRONT_CHANNEL_REF,
        state="open",
    )


def test_available_menu_pdp_cart_checkout_flow(
    client: Client,
    settings,
    channel,
    listing,
    collection,
    customer,
):
    """Scenario 1: menu -> PDP -> add 2 -> cart -> checkout."""
    product = _make_product("AV-E2E-READY", "Brioche do Dia", price_q=1200)
    _publish(listing, product)
    _categorize(collection, product)
    _seed_stock(product.sku, Decimal("10"))

    menu = client.get("/menu/")
    assert menu.status_code == 200
    assert "Brioche do Dia" in menu.content.decode()

    pdp = client.get(f"/produto/{product.sku}/")
    assert pdp.status_code == 200
    assert "Adicionar" in pdp.content.decode()

    add = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "2"})
    assert add.status_code == 200
    assert add.headers.get("X-Shopman-Error-UI") is None

    cart = client.get("/cart/")
    assert cart.status_code == 200
    cart_body = cart.content.decode()
    assert "Brioche do Dia" in cart_body
    assert "Aguardando confirmação" not in cart_body
    assert "Indisponível" not in cart_body

    _login_as_customer(client, customer, settings)
    future_date = (date.today() + timedelta(days=3)).isoformat()
    checkout = client.post(
        "/checkout/",
        {
            "phone": customer.phone,
            "name": customer.name,
            "fulfillment_type": "pickup",
            "delivery_date": future_date,
            "delivery_time_slot": "slot-09",
        },
    )
    assert checkout.status_code == 302


def test_low_stock_adds_max_without_warning_and_cart_clamps(
    client: Client,
    channel,
    listing,
    collection,
):
    """Scenario 2: last units show low-stock state and clamp at max."""
    product = _make_product("AV-E2E-LOW", "Último Croissant", price_q=1500)
    _publish(listing, product)
    _categorize(collection, product)
    _seed_stock(product.sku, Decimal("3"))

    catalog = build_catalog(channel_ref=STOREFRONT_CHANNEL_REF)
    item = next(i for i in catalog.items if i.sku == product.sku)
    assert item.availability is Availability.LOW_STOCK
    assert item.availability_label == "Últimas unidades"
    assert item.available_qty == 3

    add = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "3"})
    assert add.status_code == 200
    assert add.headers.get("X-Shopman-Error-UI") is None

    cart = client.get("/cart/")
    assert cart.status_code == 200
    body = cart.content.decode()
    assert "max: 3" in body
    assert "Estoque máximo atingido" in body


def test_adjustment_and_pdp_substitution_modal_contract(client: Client, listing):
    """Scenarios 3 and 4: accept smaller qty or choose substitute from PDP."""
    product = _make_product("AV-E2E-SHORT", "Pão em Disputa", price_q=1000)
    substitute = _make_product("AV-E2E-SUB", "Pão Substituto", price_q=1100)
    _publish(listing, product)
    _publish(listing, substitute)

    from shopman.shop.services.cart import CartUnavailableError

    exc = CartUnavailableError(
        sku=product.sku,
        requested_qty=10,
        available_qty=3,
        is_paused=False,
        error_code="insufficient_stock",
        substitutes=[
            {
                "sku": substitute.sku,
                "name": substitute.name,
                "price_display": "R$ 11,00",
                "price_q": substitute.base_price_q,
                "available_qty": 5,
                "can_order": True,
                "target_qty": 1,
            },
        ],
    )

    with patch("shopman.storefront.cart.CartService.add_item", side_effect=exc):
        response = client.post(
            "/cart/set-qty/",
            {"sku": product.sku, "qty": "10"},
            HTTP_HX_CURRENT_URL=f"https://shop.example/produto/{product.sku}/",
        )

    assert response.status_code == 422
    assert response["X-Shopman-Error-UI"] == "1"
    body = response.content.decode()
    assert "Adicionar 3 dispon" in body
    assert "origin: 'pdp'" in body
    assert "Pão Substituto" in body
    assert substitute.sku.replace("-", "\\u002D") in body
    assert ", true)" in body
    assert "window.location.href = '/cart/'" in body


def test_fermata_add_materialize_notify_and_countdown(
    client: Client,
    settings,
    channel,
    listing,
    collection,
    customer,
):
    """Scenario 5: demand hold -> awaiting badge -> materialization notification + countdown."""
    settings.SHOPMAN_BASE_URL = "https://shop.example"
    _use_offerman_sku_validator(settings)
    product = _make_product(
        "AV-E2E-FERMATA",
        "Focaccia por Encomenda",
        price_q=1800,
        availability_policy=AvailabilityPolicy.DEMAND_OK,
    )
    _publish(listing, product)
    _categorize(collection, product)
    _seed_tracked_sold_out(product.sku)

    add = client.post("/cart/set-qty/", {"sku": product.sku, "qty": "1"})
    assert add.status_code == 200, add.content.decode()[:1200]

    session = _open_cart_session(client)
    session.data = {**(session.data or {}), "customer_id": str(customer.uuid)}
    session.save(update_fields=["data"])

    hold = Hold.objects.get(sku=product.sku, metadata__reference=session.session_key)
    assert hold.expires_at is None
    assert (hold.metadata or {}).get("planned") is True

    awaiting = build_cart(
        request=_request_with_session(client),
        channel_ref=STOREFRONT_CHANNEL_REF,
    )
    assert awaiting.items[0].is_awaiting_confirmation is True
    assert awaiting.items[0].is_ready_for_confirmation is False

    cart_before = client.get("/cart/")
    assert "Aguardando confirmação" in cart_before.content.decode()

    quant = _seed_stock(product.sku, Decimal("1"))
    deadline = timezone.now() + timedelta(minutes=55)
    hold.quant = quant
    hold.expires_at = deadline
    hold.save(update_fields=["quant", "expires_at"])

    from shopman.shop.handlers._stock_receivers import on_holds_materialized

    with patch("shopman.shop.notifications.notify") as notify:
        on_holds_materialized(
            sender=None,
            hold_ids=[hold.hold_id],
            sku=product.sku,
            target_date=date.today(),
        )

    notify.assert_called_once()
    kwargs = notify.call_args.kwargs
    assert kwargs["event"] == "stock.arrived"
    assert kwargs["context"]["product_name"] == product.name
    assert kwargs["context"]["deadline_at"] == deadline.isoformat()
    assert kwargs["context"]["cart_url"] == "https://shop.example/cart/"

    ready = build_cart(
        request=_request_with_session(client),
        channel_ref=STOREFRONT_CHANNEL_REF,
    )
    assert ready.items[0].is_awaiting_confirmation is False
    assert ready.items[0].is_ready_for_confirmation is True
    assert ready.items[0].confirmation_deadline_iso == deadline.isoformat()

    cart_after = client.get("/cart/")
    body = cart_after.content.decode()
    assert "Tudo pronto! Confirme até" in body
    assert "Tempo restante:" in body


def test_product_not_listed_in_channel_returns_404(client: Client, channel, listing):
    """Scenario 6: published product outside the channel listing is not public."""
    product = _make_product("AV-E2E-NOT-LISTED", "Produto Fora do Canal")

    response = client.get(f"/produto/{product.sku}/")

    assert response.status_code == 404
