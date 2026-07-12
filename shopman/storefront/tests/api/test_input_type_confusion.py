"""Type-confusion em campos de texto → 400 limpo, nunca 500 com traceback.

Regressão do QA exploratório (P1): o padrão ``(request.data.get("x") or "").strip()``
assumia string; um corpo JSON com o campo como int/list/dict truthy estourava
``AttributeError → 500`` (traceback vazando paths do servidor em DEBUG). Repro:

- ``POST /api/v1/cart/coupon/`` ``{"code": 42}``          — público, sem login
- ``POST /api/v1/account/addresses/`` ``{"formatted_address": 999}``
- ``PATCH /api/v1/account/profile/`` ``{"first_name": 12345}``
"""

from __future__ import annotations

import pytest
from django.test import Client
from shopman.guestman.models import Customer

pytestmark = pytest.mark.django_db


def _login_as_customer(client: Client, customer: Customer):
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=getattr(customer, "email", None) or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return user


@pytest.mark.parametrize("bad_code", [42, ["x"], {"a": 1}, True])
def test_coupon_code_non_string_returns_clean_400(client: Client, bad_code):
    resp = client.post(
        "/api/v1/cart/coupon/",
        data={"code": bad_code},
        content_type="application/json",
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error_code"] == "empty_code"


def test_profile_first_name_non_string_returns_clean_400(client: Client):
    customer = Customer.objects.create(
        ref="CUS-TC-01",
        first_name="Ana",
        last_name="Silva",
        phone="+5543999990101",
    )
    _login_as_customer(client, customer)

    resp = client.patch(
        "/api/v1/account/profile/",
        data={"first_name": 12345},
        content_type="application/json",
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["field"] == "first_name"


def test_address_formatted_address_non_string_returns_clean_400(client: Client):
    customer = Customer.objects.create(
        ref="CUS-TC-02",
        first_name="Bia",
        last_name="Souza",
        phone="+5543999990102",
    )
    _login_as_customer(client, customer)

    resp = client.post(
        "/api/v1/account/addresses/",
        data={"formatted_address": 999},
        content_type="application/json",
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["field"] == "formatted_address"
