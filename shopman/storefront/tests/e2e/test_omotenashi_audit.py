"""OMOTENASHI & UX quality audit — storefront (headless JSON API).

Pre-alpha validation. Omotenashi is not pretty copy — it is STRUCTURE and
TIMING: every screen needs an empty state with a way forward, an error state
that offers an ACTION (not just text), and the system should anticipate the
customer's next need.

This started as an audit harness and is now the regression suite for the
omotenashi contract: every empty/error surface must offer a way forward, with
copy resolved from ``OmotenashiCopy`` (operator-configurable), consistently.
It drives the same ``/api/v1/...`` surface the Nuxt storefront consumes (via
``_journey``). The eight gaps the audit found (WP: empty states + error actions)
are now fixed; each ``_b`` test guards one of them.

Each verdict was verified against real endpoint behaviour, not inferred.
Run: ``.venv/bin/python -m pytest shopman/storefront/tests/e2e/test_omotenashi_audit.py``
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from . import _journey as J

pytestmark = pytest.mark.django_db

SKU = "PAO-FRANCES"
SKU_B = "CROISSANT"


def _seed(stock_qty=10):
    J.seed_shop()
    J.seed_web_channel()
    collection = J.seed_collection()
    J.seed_product(SKU, "Pão Francês", 500, collection=collection, stock_qty=stock_qty)
    return collection


# ══════════════════════════════════════════════════════════════════════════
# EMPTY STATES — every empty surface must offer a way forward, not just "vazio".
# ══════════════════════════════════════════════════════════════════════════


def test_01_empty_cart_offers_cta_to_catalog(client):
    """✅ Empty cart exposes a ``continue_shopping`` action → /menu (not bare 'vazio')."""
    _seed()
    status, body = J.get_json(client, "/api/v1/storefront/cart/")
    assert status == 200
    cart = body["cart"]
    assert cart["is_empty"] is True
    refs = {a["ref"]: a for a in cart.get("actions", [])}
    assert "continue_shopping" in refs, "empty cart has no way back to the catalogue"
    cta = refs["continue_shopping"]
    assert cta["enabled"] is True
    assert cta["href"] == "/menu"
    # The disabled checkout action explains *why* it's disabled — actionable copy.
    assert refs["checkout"]["reason"] == "Sacola vazia."


def test_02_empty_order_history_is_structured_with_guidance(client):
    """✅ New customer's order history returns a structured empty state (title+message→cardápio)."""
    _seed()
    customer = J.make_customer()
    J.authenticate(client, customer)
    status, body = J.get_json(client, "/api/v1/account/orders/")
    assert status == 200
    assert body["orders"] == []
    empty = body.get("copy", {}).get("empty", {})
    assert empty.get("title"), "empty order history has no guiding title"
    assert empty.get("message"), "empty order history has no guiding message"
    # Guidance points somewhere ('cardápio'/'começar'), not a dead end.
    assert "cardápio" in empty["message"].lower() or "começ" in empty["message"].lower()


def test_03_empty_address_list_has_omotenashi_copy_on_optin(client):
    """✅ Addresses empty-state copy exists (OmotenashiCopy ADDRESSES_EMPTY) via ?include=copy."""
    _seed()
    customer = J.make_customer()
    J.authenticate(client, customer)
    status, body = J.get_json(client, "/api/v1/account/addresses/?include=copy")
    assert status == 200
    copy = body.get("copy", {})
    assert copy.get("empty_title"), "addresses empty state has no title"
    assert copy.get("empty_message"), "addresses empty state has no message"


def test_03b_addresses_default_is_bare_list_by_design(client):
    """✅ The default addresses response is a bare list ON PURPOSE.

    The checkout page consumes the raw array (``list.filter``); the Endereços
    screen — the only surface that renders an empty state — opts in with
    ``?include=copy`` and gets the omotenashi block (see test_03). Making the
    envelope the default would break the checkout consumer, so the opt-in split
    is the correct design, not a gap.
    """
    _seed()
    customer = J.make_customer()
    J.authenticate(client, customer)
    status, body = J.get_json(client, "/api/v1/account/addresses/")
    assert status == 200
    assert isinstance(body, list)  # raw array — checkout relies on this
    status, enveloped = J.get_json(client, "/api/v1/account/addresses/?include=copy")
    assert enveloped["copy"]["empty_title"]  # the empty-state surface opts in


def test_04_empty_favorites_offers_guidance(client):
    """✅ Empty favorites carries an OmotenashiCopy empty state with a CTA to the menu."""
    _seed()
    customer = J.make_customer()
    J.authenticate(client, customer)
    status, body = J.get_json(client, "/api/v1/account/favorites/")
    assert status == 200
    assert body["items"] == []
    empty = body["copy"]["empty"]
    assert empty["title"] and empty["message"]
    assert empty["cta_label"] and empty["cta_href"] == "/menu"


def test_05_empty_catalog_and_search_offer_guidance(client):
    """✅ Empty catalogue and fruitless search both carry a configurable empty-state block."""
    J.seed_shop()
    J.seed_web_channel()  # no products
    status, body = J.get_json(client, "/api/v1/storefront/menu/")
    assert status == 200
    catalog = body["catalog"]
    assert catalog["has_items"] is False
    # Empty catalogue: a title + message, not just empty arrays.
    assert catalog["empty_state"]["title"] and catalog["empty_state"]["message"]
    # Client-side search "no results" copy travels too, with a CTA back to the menu.
    search = catalog["search_empty_state"]
    assert search["title"] and search["message"]
    assert search["cta_label"] and search["cta_href"] == "/menu"


# ══════════════════════════════════════════════════════════════════════════
# ERROR STATES — an error must offer an ACTION, not just text.
# ══════════════════════════════════════════════════════════════════════════


def test_06_soldout_in_cart_offers_alternatives(client):
    """✅ Over-requesting stock → 409 rich payload: clamp-to-available action + substitutes."""
    _seed(stock_qty=2)
    J.seed_product(SKU_B, "Croissant", 700, stock_qty=50)  # a substitute exists
    status, body = J.set_cart_qty(client, SKU, 5)
    assert status == 409, body
    assert body["title"] == "Revise este item"
    assert body["detail"] and body["available_qty"] == 2
    refs = {a["ref"] for a in body.get("actions", [])}
    # One-tap recovery: clamp to what's available.
    assert "set_available_qty" in refs
    assert "substitutes" in body  # alternatives channel present (may be empty)


def test_06b_soldout_offers_notify_cta(client):
    """✅ The sold-out 409 offers a 'Me avise quando disponível' action to the notify endpoint."""
    _seed(stock_qty=2)
    status, body = J.set_cart_qty(client, SKU, 5)
    assert status == 409
    assert body["is_notifiable"] is True
    notify = next(a for a in body["actions"] if a["ref"] == "notify_when_available")
    assert notify["href"] == f"/api/v1/availability/{SKU}/notify/"
    assert notify["method"] == "POST"
    assert "avise" in notify["label"].lower()


def test_07_checkout_rejected_date_is_actionable(client):
    """✅ A checkout for a date we cannot serve returns a field-routed, pt-BR error."""
    _seed()
    J.set_cart_qty(client, SKU, 1)
    status, body = J.checkout(
        client,
        fulfillment_type="pickup",
        delivery_date=J.days_ahead_iso(-1),  # yesterday
        delivery_time_slot=J.last_pickup_slot(),
    )
    assert status == 400, body
    assert body["field"] == "delivery_date"
    assert body["detail"]  # human message, routed to the owning field
    # pt-BR, not a raw code.
    assert any(w in body["detail"].lower() for w in ("data", "encomendar", "dia"))


def test_07b_checkout_closed_day_surfaces_reopening_and_preorder(client):
    """✅ A checkout for a CLOSED day returns the earliest servable date + a preorder hint."""
    from datetime import timedelta

    from django.utils import timezone

    from shopman.shop.models import Shop

    _seed()
    # Shop open every day except the target weekday, so a specific future date is
    # deterministically closed (weekly closure), not just "in the past".
    shop = Shop.objects.first()
    closed_weekday = (timezone.localdate() + timedelta(days=2)).weekday()  # 0=Mon
    week = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    shop.opening_hours = {
        day: ({} if i == closed_weekday else {"open": "07:00", "close": "19:00"})
        for i, day in enumerate(week)
    }
    shop.save()
    from django.core.cache import cache

    from shopman.shop.models.shop import SHOP_CACHE_KEY
    cache.delete(SHOP_CACHE_KEY)

    # First future date that lands on the closed weekday (within the preorder window).
    closed_date = timezone.localdate() + timedelta(days=2)
    while closed_date.weekday() != closed_weekday:
        closed_date += timedelta(days=1)

    J.set_cart_qty(client, SKU, 1)
    status, body = J.checkout(
        client,
        fulfillment_type="pickup",
        delivery_date=closed_date.isoformat(),
        delivery_time_slot=J.last_pickup_slot(),
    )
    assert status == 400, body
    assert body["field"] == "delivery_date"
    # Steered forward, not just blocked: earliest servable date + a preorder hint.
    assert body["earliest_available_date"]
    assert body["preorder_hint"]


def test_08_payment_failure_offers_retry_copy(client):
    """✅ A failed/errored payment has retry affordance in the omotenashi copy layer."""
    from shopman.shop.omotenashi import resolve_copy

    _seed()
    retry = resolve_copy("PAYMENT_RETRY_CTA", moment="*", audience="*")
    err_title = resolve_copy("PAYMENT_PROMISE_ERROR_TITLE", moment="*", audience="*")
    err_message = resolve_copy("PAYMENT_PROMISE_ERROR_MESSAGE", moment="*", audience="*")
    assert retry.title, "no retry CTA copy for payment"
    assert "tentar" in retry.title.lower()  # explicit "Tentar novamente"
    assert err_title.title and err_message.message
    # Error copy tells the customer the order is NOT lost and to try again.
    assert "novamente" in err_message.message.lower() or "tente" in err_message.message.lower()


def test_09_coupon_errors_are_specific_not_generic(client):
    """✅ Coupon rejection is specific: expired / exhausted / not-found each get a distinct code."""
    from datetime import timedelta

    from django.utils import timezone

    from shopman.storefront.models import Coupon, Promotion

    _seed(stock_qty=50)
    now = timezone.now()
    expired = Promotion.objects.create(
        name="Exp", type=Promotion.PERCENT, value=10,
        valid_from=now - timedelta(days=5), valid_until=now - timedelta(days=1),
    )
    Coupon.objects.create(code="EXPIRADO", promotion=expired, max_uses=0)
    exhausted_promo = Promotion.objects.create(
        name="Exh", type=Promotion.PERCENT, value=10,
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
    )
    c = Coupon.objects.create(code="ESGOTADO", promotion=exhausted_promo, max_uses=1)
    c.uses_count = 1
    c.save()

    J.set_cart_qty(client, SKU, 1)

    seen = {}
    for code in ("EXPIRADO", "ESGOTADO", "NAOEXISTE"):
        status, body = J.apply_coupon(client, code)
        assert status == 400, body
        seen[code] = body["error_code"]
        assert body["detail"]  # every rejection carries a human reason

    assert seen["EXPIRADO"] == "coupon_expired"
    assert seen["ESGOTADO"] == "coupon_exhausted"
    assert seen["NAOEXISTE"] == "invalid_coupon"
    # Genuinely distinct — not one generic "cupom inválido" for all three.
    assert len(set(seen.values())) == 3


def test_10_delivery_zone_error_routes_to_address_field(client):
    """✅ An out-of-zone address error is routed to the delivery_address field (not a blob)."""
    from shopman.orderman.exceptions import ValidationError

    from shopman.shop.services import checkout as checkout_service

    exc = ValidationError("delivery_zone_not_covered", "Ainda não entregamos nesse endereço.")
    mapped = checkout_service.map_checkout_error(exc)
    assert mapped == {"delivery_address": "Ainda não entregamos nesse endereço."}


def test_10b_delivery_zone_error_enables_pickup_swap(client):
    """✅ The zone error routes to `delivery_address` — the exact signal the front uses
    to offer a one-click 'Mudar para retirada' (shouldOfferPickupSwap). The pickup
    fallback is offered end-to-end: BE routes the field, FE renders the swap.
    """
    from shopman.orderman.exceptions import ValidationError

    from shopman.shop.services import checkout as checkout_service

    for code in ("delivery_zone_not_covered", "delivery_zone_unverified"):
        exc = ValidationError(code, "Ainda não entregamos nesse endereço.")
        mapped = checkout_service.map_checkout_error(exc)
        assert set(mapped) == {"delivery_address"}
        assert mapped["delivery_address"]


# ══════════════════════════════════════════════════════════════════════════
# COPY CONSISTENCY
# ══════════════════════════════════════════════════════════════════════════


def test_11_customer_facing_errors_are_pt_br(client):
    """✅ Framework error paths speak pt-BR (DRF locale is pt_BR — no 'Not found.'/'required')."""
    _seed()
    # Unknown SKU → DRF Http404, localised.
    status, body = J.get_json(client, "/api/v1/availability/GHOST-SKU/")
    assert status == 404
    assert body["detail"] == "Não encontrado."
    assert "not found" not in body["detail"].lower()

    # Serializer validation → localised field errors, not English DRF defaults.
    resp = client.post("/api/v1/checkout/", data=json.dumps({}), content_type="application/json")
    body = resp.json()
    assert resp.status_code == 400
    joined = json.dumps(body, ensure_ascii=False).lower()
    assert "obrigatório" in joined
    assert "this field is required" not in joined
    assert "ensure this value" not in joined


def test_12_error_responses_dont_leak_tracebacks(client):
    """✅ Degradable write paths return a clean pt-BR message, never a traceback/class name."""
    _seed()
    customer = J.make_customer()
    J.authenticate(client, customer)
    # Force the address service to blow up; the endpoint must degrade gracefully.
    with patch(
        "shopman.storefront.api.account.account_service.add_address",
        side_effect=Exception("IntegrityError: null value in column \"_internal_fk\""),
    ):
        resp = client.post(
            "/api/v1/account/addresses/",
            data=json.dumps({"formatted_address": "Rua X, 1", "label": "home"}),
            content_type="application/json",
        )
    body = resp.json()
    assert resp.status_code == 400
    blob = json.dumps(body, ensure_ascii=False)
    assert "Traceback" not in blob
    assert "IntegrityError" not in blob and "_internal_fk" not in blob
    assert body["detail"]  # a human, generic message


def test_12b_profile_update_error_does_not_leak_exception(client):
    """✅ ProfileView.patch returns a fixed pt-BR message on failure, never `str(exc)`."""
    _seed()
    customer = J.make_customer()
    J.authenticate(client, customer)
    with patch(
        "shopman.storefront.api.account.account_service.update_profile",
        side_effect=Exception("Customer.DoesNotExist at column _secret_internal_id"),
    ):
        resp = client.patch(
            "/api/v1/account/profile/",
            data=json.dumps({"first_name": "Ana"}),
            content_type="application/json",
        )
    body = resp.json()
    assert resp.status_code == 400
    # Ideal: the internal exception text must not reach the customer.
    assert "DoesNotExist" not in body["detail"]
    assert "_secret_internal_id" not in body["detail"]


def test_13_mutation_success_shape_is_consistent(client):
    """✅ Simple mutations answer with a consistent `{ok: true}` acknowledgement."""
    _seed(stock_qty=5)
    # Stock-alert subscribe.
    resp = client.post(
        f"/api/v1/availability/{SKU}/notify/",
        data=json.dumps({"phone": "43999998888"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    # Cart mutation also acknowledges with ok:true (plus its projection).
    status, add = J.set_cart_qty(client, SKU, 1)
    assert status == 200
    assert add["ok"] is True


def test_14_user_copy_is_overridable_via_omotenashi_copy(client):
    """✅ Customer-facing copy is DB-overridable (OmotenashiCopy), not frozen in code."""
    from shopman.shop.models import OmotenashiCopy
    from shopman.shop.omotenashi import resolve_copy
    from shopman.shop.omotenashi.copy import invalidate_cache

    _seed()
    OmotenashiCopy.objects.create(
        key="CART_UNAVAILABLE_BANNER", moment="*", audience="*",
        message="Alguns itens mudaram — confira abaixo (override).",
    )
    invalidate_cache()
    entry = resolve_copy("CART_UNAVAILABLE_BANNER", moment="*", audience="*")
    assert entry.message == "Alguns itens mudaram — confira abaixo (override)."


def test_14b_empty_cart_reason_is_copy_driven(client):
    """✅ The empty-cart checkout-block reason resolves from OmotenashiCopy (operator-tunable)."""
    from shopman.shop.models import OmotenashiCopy
    from shopman.shop.omotenashi.copy import invalidate_cache

    _seed()
    OmotenashiCopy.objects.create(
        key="CART_CHECKOUT_BLOCK_EMPTY", moment="*", audience="*",
        message="Sua sacola está vazinha (override)",
    )
    invalidate_cache()
    status, body = J.get_json(client, "/api/v1/storefront/cart/")
    refs = {a["ref"]: a for a in body["cart"].get("actions", [])}
    assert refs["checkout"]["reason"] == "Sua sacola está vazinha (override)"


# ══════════════════════════════════════════════════════════════════════════
# FLOW & ANTICIPATION — the system should pre-empt the customer's next step.
# ══════════════════════════════════════════════════════════════════════════


def test_15_checkout_prefills_known_customer_data(client):
    """✅ Checkout pre-populates name, phone and saved address — no re-typing."""
    _seed()
    customer = J.make_customer(first_name="Marina", phone="+5543999990001")
    J.seed_address(customer, is_default=True)
    J.authenticate(client, customer)
    status, body = J.get_json(client, "/api/v1/storefront/checkout/")
    assert status == 200
    ck = body["checkout"]
    assert ck["is_authenticated"] is True
    # Pre-filled from the account (full name = first + last), no re-typing.
    assert ck["customer_name"].startswith("Marina")
    assert ck["customer_phone"] == "+5543999990001"
    assert len(ck["saved_addresses"]) == 1
    # Anticipation: a default address is preselected, not left for the customer to pick.
    assert ck["preselected_address_id"] is not None


def test_16_reorder_readds_previous_order_in_one_call(client):
    """✅ Reorder re-adds a past order's items in one action and skips unavailable ones gracefully."""
    _seed(stock_qty=50)
    customer = J.make_customer()
    order = J.seed_past_order(
        customer,
        ref="ORD-AUDIT-1",
        items=[
            {"sku": SKU, "name": "Pão Francês", "qty": 2, "unit_price_q": 500},
            {"sku": "GHOST-SKU", "name": "Item Saído de Linha", "qty": 1, "unit_price_q": 300},
        ],
    )
    J.authenticate(client, customer)
    status, body = J.reorder(client, order.ref, mode="replace")
    assert status == 200, body
    # The available item lands in the cart…
    assert body["cart"]["items_count"] == 2
    # …and the unavailable one is reported (not silently dropped, not a hard failure).
    assert "GHOST-SKU" in body.get("skipped", [])
    assert body["skipped_items"][0]["reason"]


def test_17_anonymous_cart_survives_login(client):
    """✅ The anonymous bag is preserved across the login session rotation (merge)."""
    _seed(stock_qty=10)
    status, add = J.set_cart_qty(client, SKU, 2)
    assert status == 200 and add["cart"]["items_count"] == 2
    login = J.otp_login(client, J.DEFAULT_PHONE)
    assert login["status"] == 200, login
    status, cart = J.get_json(client, "/api/v1/storefront/cart/")
    assert status == 200
    assert cart["cart"]["items_count"] == 2, "cart was lost across login"


def test_18_unavailable_product_exposes_notify_affordance(client):
    """✅ Catalogue cards carry the 'Me avise' plumbing and the subscribe endpoint works."""
    _seed(stock_qty=5)
    status, menu = J.get_json(client, "/api/v1/storefront/menu/")
    card = next(c for c in menu["catalog"]["items"] if c["sku"] == SKU)
    # The affordance keys exist on every card (flip to True when UNAVAILABLE + sellable).
    assert "is_notifiable" in card
    assert "is_notify_subscribed" in card
    # And the back-in-stock subscription round-trips.
    resp = client.post(
        f"/api/v1/availability/{SKU}/notify/",
        data=json.dumps({"phone": "43999997777"}),
        content_type="application/json",
    )
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    from shopman.storefront.services import stock_alerts

    # The subscription was persisted (phone is normalised on the way in).
    assert stock_alerts.has_pending(SKU) is True


def test_19_catalog_carries_real_availability(client):
    """✅ The menu projection ships real availability per product — no click-to-discover-it's-gone."""
    _seed(stock_qty=5)
    status, menu = J.get_json(client, "/api/v1/storefront/menu/")
    assert status == 200
    card = next(c for c in menu["catalog"]["items"] if c["sku"] == SKU)
    assert card["availability"] in {"available", "low_stock", "planned_ok", "unavailable"}
    assert card["availability_label"]  # human badge text
    assert isinstance(card["can_add_to_cart"], bool)


# ══════════════════════════════════════════════════════════════════════════
# RESILIENCE
# ══════════════════════════════════════════════════════════════════════════


def test_20_error_responses_are_json_across_status_codes(client):
    """✅ 404 / 400 / 401 / 409 all return valid JSON with `detail` — never debug HTML."""
    _seed(stock_qty=2)

    # 404 — unknown order.
    r404 = client.get("/api/v1/tracking/DOES-NOT-EXIST/")
    # 401 — protected account endpoint, anonymous.
    r401 = client.get("/api/v1/account/summary/")
    # 400 — empty checkout body (serializer).
    r400 = client.post("/api/v1/checkout/", data=json.dumps({}), content_type="application/json")
    # 409 — oversell.
    r409 = client.put(
        f"/api/v1/cart/skus/{SKU}/", data=json.dumps({"qty": 9}), content_type="application/json"
    )

    for resp, expected in ((r404, 404), (r401, 401), (r400, 400), (r409, 409)):
        assert resp.status_code == expected, resp.content
        assert resp["Content-Type"].startswith("application/json"), resp["Content-Type"]
        assert "detail" in resp.json()


def test_21_internal_failure_degrades_not_crashes(client):
    """✅ An internal service failure in a read path degrades to a friendly answer, not a 500 crash."""
    _seed()
    customer = J.make_customer()
    J.authenticate(client, customer)
    # Break the order-history service; the account summary must still answer cleanly.
    with patch(
        "shopman.storefront.presentation.account.order_history_for_customer",
        side_effect=Exception("db connection reset"),
    ):
        resp = client.get("/api/v1/account/summary/")
    # Either a graceful 200 (degraded) or a clean JSON error — never an HTML 500 traceback.
    assert resp["Content-Type"].startswith("application/json")
    assert resp.status_code in (200, 500)
    assert "Traceback" not in resp.content.decode("utf-8", "replace")
    if resp.status_code == 500:
        assert "detail" in resp.json()


def test_22_optional_fields_are_truly_optional(client):
    """✅ A bare product (no nutrition/allergen/etc.) and a minimal pickup checkout don't explode."""
    _seed(stock_qty=5)
    # Minimal product detail — optional panels collapse, no crash.
    status, detail = J.get_json(client, f"/api/v1/catalog/products/{SKU}/")
    assert status == 200, detail
    assert detail["sku"] == SKU

    # Minimal checkout: only the required fields (name/phone/fulfillment/payment).
    J.set_cart_qty(client, SKU, 1)
    status, body = J.checkout(client)  # pickup + cash defaults, nothing else supplied
    assert status == 201, body
    assert body["order_ref"]
