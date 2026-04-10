"""
Tests for PhoneOTPBackend, verify_for_login login(), and LogoutView (AUTH-1).
"""

import uuid

import pytest
from django.contrib.auth import get_user_model, login
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, override_settings

from shopman.doorman.backends import PhoneOTPBackend
from shopman.doorman.models import CustomerUser
from shopman.doorman.services.verification import AuthService
from shopman.doorman.views.logout import LogoutView

User = get_user_model()

DOORMAN_SETTINGS = {
    "CUSTOMER_RESOLVER_CLASS": "shopman.guestman.adapters.auth.CustomerResolver",
    "MESSAGE_SENDER_CLASS": "shopman.doorman.senders.LogSender",
    "DEVICE_TRUST_COOKIE_NAME": "shopman_auth_dt",
    "LOGOUT_REDIRECT_URL": "/",
}

BACKENDS = [
    "shopman.doorman.backends.PhoneOTPBackend",
    "django.contrib.auth.backends.ModelBackend",
]


def _make_request(method="get", path="/"):
    from django.contrib.auth.models import AnonymousUser

    factory = RequestFactory()
    request = getattr(factory, method)(path)
    request.session = SessionStore()
    request.session.create()
    request.user = AnonymousUser()
    return request


# ===========================================
# PhoneOTPBackend
# ===========================================


@pytest.mark.django_db
def test_backend_authenticate_valid_customer(customer):
    backend = PhoneOTPBackend()
    request = _make_request()
    user = backend.authenticate(request, customer_id=customer.uuid)

    assert user is not None
    assert user.is_active
    assert CustomerUser.objects.filter(user=user, customer_id=customer.uuid).exists()


@pytest.mark.django_db
def test_backend_returns_existing_user(customer):
    backend = PhoneOTPBackend()
    request = _make_request()

    user1 = backend.authenticate(request, customer_id=customer.uuid)
    user2 = backend.authenticate(request, customer_id=customer.uuid)

    assert user1.pk == user2.pk


@pytest.mark.django_db
def test_backend_invalid_customer_id(db):
    backend = PhoneOTPBackend()
    request = _make_request()

    user = backend.authenticate(request, customer_id=uuid.uuid4())
    assert user is None


@pytest.mark.django_db
def test_backend_inactive_customer(customer):
    customer.is_active = False
    customer.save(update_fields=["is_active"])

    backend = PhoneOTPBackend()
    request = _make_request()
    user = backend.authenticate(request, customer_id=customer.uuid)

    assert user is None


@pytest.mark.django_db
def test_backend_no_customer_id(db):
    backend = PhoneOTPBackend()
    request = _make_request()

    assert backend.authenticate(request) is None


@pytest.mark.django_db
def test_backend_get_user_valid(customer):
    backend = PhoneOTPBackend()
    request = _make_request()
    user = backend.authenticate(request, customer_id=customer.uuid)

    assert backend.get_user(user.pk) is not None


@pytest.mark.django_db
def test_backend_get_user_invalid(db):
    backend = PhoneOTPBackend()
    assert backend.get_user(999999) is None


# ===========================================
# verify_for_login sets request.user
# ===========================================


@pytest.mark.django_db
@override_settings(
    DOORMAN=DOORMAN_SETTINGS,
    AUTHENTICATION_BACKENDS=BACKENDS,
)
def test_verify_login_with_request_sets_user(customer, verification_code):
    """verify_for_login with request should call login() and set request.user."""
    request = _make_request()
    result = AuthService.verify_for_login(
        target_value=verification_code.target_value,
        code_input=verification_code._raw_code,
        request=request,
    )

    assert result.success
    assert result.customer is not None
    assert hasattr(request, "user")
    assert request.user.is_authenticated


@pytest.mark.django_db
@override_settings(DOORMAN=DOORMAN_SETTINGS)
def test_verify_login_without_request_no_login(customer, verification_code):
    """verify_for_login without request does not attempt login."""
    result = AuthService.verify_for_login(
        target_value=verification_code.target_value,
        code_input=verification_code._raw_code,
        request=None,
    )

    assert result.success
    assert result.customer is not None


# ===========================================
# LogoutView
# ===========================================


@pytest.mark.django_db
@override_settings(
    DOORMAN=DOORMAN_SETTINGS,
    AUTHENTICATION_BACKENDS=BACKENDS,
)
def test_logout_clears_session(customer):
    backend = PhoneOTPBackend()
    request = _make_request("post", "/auth/logout/")
    user = backend.authenticate(request, customer_id=customer.uuid)
    login(request, user, backend="shopman.doorman.backends.PhoneOTPBackend")
    assert request.user.is_authenticated

    response = LogoutView.as_view()(request)

    assert response.status_code == 302
    assert response["Location"] == "/"


@pytest.mark.django_db
@override_settings(DOORMAN=DOORMAN_SETTINGS)
def test_logout_clears_device_trust_cookie(customer):
    request = _make_request("post", "/auth/logout/")
    request.COOKIES["shopman_auth_dt"] = "some-token"

    response = LogoutView.as_view()(request)

    assert response.status_code == 302
    assert "shopman_auth_dt" in response.cookies
    assert response.cookies["shopman_auth_dt"]["max-age"] == 0


@pytest.mark.django_db
@override_settings(DOORMAN=DOORMAN_SETTINGS)
def test_logout_get_not_allowed():
    request = _make_request("get", "/auth/logout/")
    response = LogoutView.as_view()(request)
    assert response.status_code == 405


@pytest.mark.django_db
@override_settings(DOORMAN={**DOORMAN_SETTINGS, "LOGOUT_REDIRECT_URL": "/goodbye/"})
def test_logout_redirect_url_configurable(customer):
    request = _make_request("post", "/auth/logout/")
    response = LogoutView.as_view()(request)

    assert response.status_code == 302
    assert response["Location"] == "/goodbye/"
