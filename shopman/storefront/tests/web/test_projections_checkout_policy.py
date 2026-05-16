from __future__ import annotations

import pytest
from django.test import RequestFactory

from shopman.storefront.api.projections import projection_data
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.projections.checkout import build_checkout

pytestmark = pytest.mark.django_db


def _request(client):
    rf = RequestFactory()
    request = rf.get("/checkout/")
    request.session = client.session  # type: ignore[attr-defined]
    request.customer = None
    return request


def test_checkout_projection_uses_surface_policy_for_fulfillment_options(
    cart_session,
    channel,
):
    channel.config = {
        **(channel.config or {}),
            "surface_policy": {"fulfillment_types": ["pickup"]},
    }
    channel.save(update_fields=["config"])

    checkout = build_checkout(
        request=_request(cart_session),
        channel_ref=STOREFRONT_CHANNEL_REF,
    )

    assert checkout.fulfillment_options == ("pickup",)
    assert checkout.has_pickup is True
    assert checkout.has_delivery is False


def test_checkout_projection_serializes_actions_without_policy_payload(cart_session, channel):
    channel.config = {
        **(channel.config or {}),
        "payment": {"method": ["pix", "cash"], "timing": "at_commit"},
    }
    channel.save(update_fields=["config"])

    checkout = build_checkout(
        request=_request(cart_session),
        channel_ref=STOREFRONT_CHANNEL_REF,
    )

    payload = projection_data(checkout)

    assert "capabilities" not in payload
    assert payload["payment_methods"][0]["ref"] == "pix"
    assert payload["payment_methods"][1]["ref"] == "cash"
    assert payload["actions"][0]["ref"] == "checkout"
    assert payload["actions"][0]["kind"] == "mutation"
    assert payload["actions"][0]["idempotency"] == "required"
