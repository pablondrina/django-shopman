from __future__ import annotations

import pytest
from django.test import Client
from django.utils import timezone
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


def _mint_login_code(phone: str) -> str:
    """Create a valid LOGIN verification code for ``phone`` and return the raw digits."""
    from shopman.doorman.models.verification_code import VerificationCode, generate_raw_code

    raw_code, hmac_digest = generate_raw_code()
    code = VerificationCode.objects.create(
        code_hash=hmac_digest,
        target_value=phone,
        purpose=VerificationCode.Purpose.LOGIN,
    )
    code.mark_sent()
    return raw_code


def test_delete_requires_step_up(client: Client):
    customer = Customer.objects.create(ref="CUS-SU-DEL", first_name="Ana", phone="+5543999990010")
    _login_as_customer(client, customer)

    response = client.post(
        "/api/v1/account/delete/",
        data={"acknowledged": True},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["code"] == "step_up_required"
    customer.refresh_from_db()
    assert customer.phone == "+5543999990010"  # NÃO anonimizado


def test_export_requires_step_up(client: Client):
    customer = Customer.objects.create(ref="CUS-SU-EXP", first_name="Bia", phone="+5543999990011")
    _login_as_customer(client, customer)

    response = client.get("/api/v1/account/export/")

    assert response.status_code == 403
    assert response.json()["code"] == "step_up_required"


def test_step_up_with_wrong_code_is_rejected(client: Client):
    customer = Customer.objects.create(ref="CUS-SU-BAD", first_name="Caio", phone="+5543999990012")
    _login_as_customer(client, customer)

    response = client.post(
        "/api/v1/account/step-up/",
        data={"code": "000000"},
        content_type="application/json",
    )

    assert response.status_code == 400


def test_step_up_then_delete_succeeds(client: Client):
    phone = "+5543999990013"
    customer = Customer.objects.create(ref="CUS-SU-OK", first_name="Duda", phone=phone)
    _login_as_customer(client, customer)
    raw_code = _mint_login_code(phone)

    step_up = client.post(
        "/api/v1/account/step-up/",
        data={"code": raw_code},
        content_type="application/json",
    )
    assert step_up.status_code == 200

    deleted = client.post(
        "/api/v1/account/delete/",
        data={"acknowledged": True},
        content_type="application/json",
    )
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True


def test_fresh_step_up_flag_lets_export_through(client: Client):
    from shopman.storefront.api.account import STEP_UP_SESSION_KEY

    customer = Customer.objects.create(ref="CUS-SU-FLAG", first_name="Edu", phone="+5543999990014")
    _login_as_customer(client, customer)

    session = client.session
    session[STEP_UP_SESSION_KEY] = timezone.now().isoformat()
    session.save()

    response = client.get("/api/v1/account/export/")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")
