from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.test import Client
from shopman.guestman.models import Customer

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _disable_request_rate_limits(settings):
    settings.RATELIMIT_ENABLE = False


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


def test_auth_session_returns_anonymous_identity(client: Client):
    response = client.get("/api/v1/auth/session/")

    assert response.status_code == 200
    assert response.json() == {
        "is_authenticated": False,
        "customer_ref": "",
        "customer_name": "",
        "customer_phone": "",
        "customer_email": "",
        "requires_welcome": False,
        "welcome_suggested_name": "",
    }


def test_auth_session_returns_customer_identity(client: Client):
    customer = Customer.objects.create(
        ref="CUS-AUTH-01",
        first_name="Ana",
        last_name="Silva",
        phone="+5543999990001",
        email="ana@example.com",
    )
    _login_as_customer(client, customer)

    response = client.get("/api/v1/auth/session/")

    assert response.status_code == 200
    data = response.json()
    assert data["is_authenticated"] is True
    assert data["customer_ref"] == customer.ref
    assert data["customer_name"] == customer.name
    assert data["customer_phone"] == customer.phone
    assert data["customer_email"] == customer.email
    assert data["requires_welcome"] is False
    assert data["welcome_suggested_name"] == customer.name


def test_auth_session_marks_nameless_customer_for_welcome(client: Client):
    customer = Customer.objects.create(
        ref="CUS-AUTH-WELCOME",
        first_name="",
        last_name="",
        phone="+5543999990010",
    )
    _login_as_customer(client, customer)

    response = client.get("/api/v1/auth/session/")

    assert response.status_code == 200
    data = response.json()
    assert data["is_authenticated"] is True
    assert data["requires_welcome"] is True
    assert data["welcome_suggested_name"] == ""


def test_auth_session_marks_dirty_customer_name_for_welcome(client: Client):
    customer = Customer.objects.create(
        ref="CUS-AUTH-DIRTY",
        first_name="João & Maria 🥐",
        last_name="",
        phone="+5543999990011",
    )
    _login_as_customer(client, customer)

    response = client.get("/api/v1/auth/session/")

    assert response.status_code == 200
    data = response.json()
    assert data["requires_welcome"] is True
    assert data["welcome_suggested_name"] == "João & Maria"


def test_auth_logout_is_json_and_does_not_require_csrf():
    customer = Customer.objects.create(
        ref="CUS-AUTH-02",
        first_name="Bia",
        phone="+5543999990002",
    )
    client = Client(enforce_csrf_checks=True)
    _login_as_customer(client, customer)

    response = client.post("/api/v1/auth/logout/", content_type="application/json")

    assert response.status_code == 200
    assert response.json()["is_authenticated"] is False
    assert client.get("/api/v1/auth/session/").json()["is_authenticated"] is False


def test_auth_logout_preserves_cart_session_key(settings):
    customer = Customer.objects.create(
        ref="CUS-AUTH-03",
        first_name="Caio",
        phone="+5543999990003",
    )
    settings.DOORMAN = {**settings.DOORMAN, "PRESERVE_SESSION_KEYS": ["cart_session_key"]}
    client = Client()
    _login_as_customer(client, customer)
    session = client.session
    session["cart_session_key"] = "cart-local-123"
    session["unrelated"] = "drop-me"
    session.save()

    response = client.post("/api/v1/auth/logout/", content_type="application/json")

    assert response.status_code == 200
    assert client.session.get("cart_session_key") == "cart-local-123"
    assert client.session.get("unrelated") is None


def test_auth_request_code_accepts_json_without_csrf(monkeypatch):
    from shopman.storefront.api import auth as auth_api

    sent = {}

    def fake_request_code(*, phone, delivery_method, ip_address):
        sent.update(phone=phone, delivery_method=delivery_method, ip_address=ip_address)
        return SimpleNamespace(success=True)

    monkeypatch.setattr(auth_api, "HAS_AUTH", True)
    monkeypatch.setattr(auth_api.auth_service, "request_code", fake_request_code)
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        "/api/v1/auth/request-code/",
        data={"target": "43999997777", "delivery_method": "whatsapp"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert sent["phone"] == "+5543999997777"
    assert sent["delivery_method"] == "whatsapp"


def test_auth_request_code_preserves_brazilian_ddi_without_plus(monkeypatch, client: Client):
    from shopman.storefront.api import auth as auth_api

    sent = {}

    def fake_request_code(*, phone, delivery_method, ip_address):
        sent.update(phone=phone, delivery_method=delivery_method, ip_address=ip_address)
        return SimpleNamespace(success=True)

    monkeypatch.setattr(auth_api, "HAS_AUTH", True)
    monkeypatch.setattr(auth_api.auth_service, "request_code", fake_request_code)

    response = client.post(
        "/api/v1/auth/request-code/",
        data={"target": "55 43 98404-9009", "delivery_method": "whatsapp"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["phone"] == "+5543984049009"
    assert sent["phone"] == "+5543984049009"


def test_auth_request_code_preserves_international_phone(monkeypatch, client: Client):
    from shopman.storefront.api import auth as auth_api

    sent = {}

    def fake_request_code(*, phone, delivery_method, ip_address):
        sent.update(phone=phone, delivery_method=delivery_method, ip_address=ip_address)
        return SimpleNamespace(success=True)

    monkeypatch.setattr(auth_api, "HAS_AUTH", True)
    monkeypatch.setattr(auth_api.auth_service, "request_code", fake_request_code)

    response = client.post(
        "/api/v1/auth/request-code/",
        data={"target": "+1 202 555 1234", "phone_region": "INTL", "delivery_method": "sms"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["phone"] == "+12025551234"
    assert sent["phone"] == "+12025551234"
    assert sent["delivery_method"] == "sms"


def test_auth_request_code_reports_actual_delivery_method(monkeypatch, client: Client):
    from shopman.storefront.api import auth as auth_api

    def fake_request_code(*, phone, delivery_method, ip_address):
        return SimpleNamespace(success=True, delivery_method="sms")

    monkeypatch.setattr(auth_api, "HAS_AUTH", True)
    monkeypatch.setattr(auth_api.auth_service, "request_code", fake_request_code)

    response = client.post(
        "/api/v1/auth/request-code/",
        data={"target": "43999998888", "delivery_method": "whatsapp"},
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["delivery_method"] == "sms"
    assert data["delivery_label"] == "SMS"


def test_auth_request_code_exposes_debug_otp_in_staging_only_when_enabled(monkeypatch, settings, client: Client):
    from shopman.storefront.api import auth as auth_api

    def fake_request_code(*, phone, delivery_method, ip_address):
        return SimpleNamespace(
            success=True,
            delivery_method="whatsapp",
            debug_code="123456",
            expires_at="2026-05-18T13:00:00+00:00",
        )

    settings.DEBUG = False
    settings.SHOPMAN_ENVIRONMENT = "staging"
    settings.SHOPMAN_EXPOSE_DEBUG_OTP = True
    monkeypatch.setattr(auth_api, "HAS_AUTH", True)
    monkeypatch.setattr(auth_api.auth_service, "request_code", fake_request_code)

    response = client.post(
        "/api/v1/auth/request-code/",
        data={"target": "43999998888", "delivery_method": "whatsapp"},
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["debug_otp_code"] == "123456"
    assert data["debug_otp_expires_at"] == "2026-05-18T13:00:00+00:00"


def test_auth_request_code_never_exposes_debug_otp_in_production(monkeypatch, settings, client: Client):
    from shopman.storefront.api import auth as auth_api

    def fake_request_code(*, phone, delivery_method, ip_address):
        return SimpleNamespace(
            success=True,
            delivery_method="whatsapp",
            debug_code="123456",
            expires_at="2026-05-18T13:00:00+00:00",
        )

    settings.DEBUG = False
    settings.SHOPMAN_ENVIRONMENT = "production"
    settings.SHOPMAN_EXPOSE_DEBUG_OTP = True
    monkeypatch.setattr(auth_api, "HAS_AUTH", True)
    monkeypatch.setattr(auth_api.auth_service, "request_code", fake_request_code)

    response = client.post(
        "/api/v1/auth/request-code/",
        data={"target": "43999998888", "delivery_method": "whatsapp"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert "debug_otp_code" not in response.json()


def test_auth_verify_code_accepts_json_and_creates_session_contract(monkeypatch):
    from shopman.storefront.api import auth as auth_api

    verified = {}

    def fake_verify_for_login(*, phone, code_input, request):
        verified.update(phone=phone, code_input=code_input)
        return SimpleNamespace(success=True)

    monkeypatch.setattr(auth_api, "HAS_AUTH", True)
    monkeypatch.setattr(auth_api.auth_service, "verify_for_login", fake_verify_for_login)
    monkeypatch.setattr(auth_api.auth_service, "confirmed_customer_name", lambda auth_result: "Ana")
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        "/api/v1/auth/verify-code/",
        data={"target": "43999998888", "code": "123456"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "phone": "+5543999998888",
        "is_authenticated": False,
        "customer_ref": "",
        "customer_name": "Ana",
        "customer_phone": "",
        "customer_email": "",
        "requires_welcome": False,
        "welcome_suggested_name": "",
    }
    assert verified == {"phone": "+5543999998888", "code_input": "123456"}


def test_auth_device_check_trusted_cookie_creates_json_session(client: Client):
    from shopman.doorman import TrustedDevice
    from shopman.doorman.conf import doorman_settings

    customer = Customer.objects.create(
        ref="CUS-AUTH-DEVICE",
        first_name="Dora",
        phone="+5543999990012",
    )
    _, raw_token = TrustedDevice.create_for_customer(
        customer_id=customer.uuid,
        user_agent="Mozilla/5.0 Test",
        ip_address="127.0.0.1",
    )
    client.cookies[doorman_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token

    response = client.post(
        "/api/v1/auth/device-check/",
        data={"target": customer.phone},
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["trusted"] is True
    assert data["is_authenticated"] is True
    assert data["customer_ref"] == customer.ref
    assert data["customer_name"] == customer.name
    assert client.session.get("_auth_user_id") is not None


def test_auth_device_check_wrong_customer_does_not_skip_otp(client: Client):
    from shopman.doorman import TrustedDevice
    from shopman.doorman.conf import doorman_settings

    trusted = Customer.objects.create(
        ref="CUS-AUTH-TRUSTED",
        first_name="Eva",
        phone="+5543999990013",
    )
    other = Customer.objects.create(
        ref="CUS-AUTH-OTHER",
        first_name="Fê",
        phone="+5543999990014",
    )
    _, raw_token = TrustedDevice.create_for_customer(
        customer_id=trusted.uuid,
        user_agent="Mozilla/5.0 Test",
        ip_address="127.0.0.1",
    )
    client.cookies[doorman_settings.DEVICE_TRUST_COOKIE_NAME] = raw_token

    response = client.post(
        "/api/v1/auth/device-check/",
        data={"target": other.phone},
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["trusted"] is False
    assert data["is_authenticated"] is False
    assert client.session.get("_auth_user_id") is None


def test_auth_trust_device_json_sets_httponly_cookie(client: Client):
    from shopman.doorman.conf import doorman_settings

    customer = Customer.objects.create(
        ref="CUS-AUTH-TRUST",
        first_name="Gabi",
        phone="+5543999990015",
    )
    _login_as_customer(client, customer)

    response = client.post(
        "/api/v1/auth/trust-device/",
        data={"trust": True},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["trusted"] is True
    cookie = response.cookies[doorman_settings.DEVICE_TRUST_COOKIE_NAME]
    assert cookie["httponly"] is True


def test_auth_trust_device_json_skip_does_not_set_cookie(client: Client):
    from shopman.doorman.conf import doorman_settings

    customer = Customer.objects.create(
        ref="CUS-AUTH-NOTRUST",
        first_name="Hugo",
        phone="+5543999990016",
    )
    _login_as_customer(client, customer)

    response = client.post(
        "/api/v1/auth/trust-device/",
        data={"trust": False},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["trusted"] is False
    assert doorman_settings.DEVICE_TRUST_COOKIE_NAME not in response.cookies
