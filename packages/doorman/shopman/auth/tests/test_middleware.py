"""Tests for AUTH-5: Middleware + request.customer."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory

from shopman.auth.conf import reset_adapter
from shopman.auth.middleware import AuthCustomerMiddleware, _CACHE_ATTR
from shopman.auth.models import CustomerUser

pytestmark = pytest.mark.django_db


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def middleware():
    return AuthCustomerMiddleware(get_response=lambda r: None)


@pytest.fixture
def django_user(db):
    return User.objects.create_user(username="testuser", password="pass")


class TestAuthCustomerMiddleware:

    def test_anonymous_user_gets_none(self, rf, middleware):
        """Anonymous request → request.customer = None."""
        request = rf.get("/")
        request.user = AnonymousUser()
        middleware.process_request(request)
        assert request.customer is None

    def test_authenticated_user_without_link_gets_none(self, rf, middleware, django_user):
        """Authenticated user with no CustomerUser link → None."""
        request = rf.get("/")
        request.user = django_user
        middleware.process_request(request)
        assert request.customer is None

    def test_authenticated_user_with_link_resolves_customer(
        self, rf, middleware, django_user
    ):
        """Authenticated user with CustomerUser link → resolved customer."""
        from shopman.customers.models import Customer

        customer = Customer.objects.create(
            ref="MW-001", first_name="Ana", phone="5543999990099",
        )
        CustomerUser.objects.create(
            user=django_user, customer_id=customer.uuid,
        )

        request = rf.get("/")
        request.user = django_user
        middleware.process_request(request)

        assert request.customer is not None
        assert request.customer.uuid == customer.uuid
        assert request.customer.name == "Ana"

    def test_cache_avoids_repeated_queries(self, rf, middleware, django_user):
        """Second call uses cached value on user, no extra query."""
        from shopman.customers.models import Customer

        customer = Customer.objects.create(
            ref="MW-002", first_name="Carlos", phone="5543999990098",
        )
        CustomerUser.objects.create(
            user=django_user, customer_id=customer.uuid,
        )

        request = rf.get("/")
        request.user = django_user

        # First call
        middleware.process_request(request)
        assert request.customer is not None

        # Cache should be set
        assert hasattr(django_user, _CACHE_ATTR)
        cached_value = getattr(django_user, _CACHE_ATTR)
        assert cached_value is not None

        # Second call — should use cache (same result)
        middleware.process_request(request)
        assert request.customer is not None
        assert request.customer.uuid == customer.uuid

    def test_no_user_attribute_gets_none(self, rf, middleware):
        """Request without user attribute → None."""
        request = rf.get("/")
        # Don't set request.user at all
        if hasattr(request, "user"):
            delattr(request, "user")
        middleware.process_request(request)
        assert request.customer is None

    def teardown_method(self):
        reset_adapter()


class TestCustomerContextProcessor:

    def test_returns_customer_from_request(self, rf):
        """Context processor reads request.customer."""
        from shopman.auth.context_processors import customer

        request = rf.get("/")
        request.customer = "sentinel"
        ctx = customer(request)
        assert ctx == {"auth_customer": "sentinel"}

    def test_returns_none_when_no_customer(self, rf):
        """No request.customer attribute → None."""
        from shopman.auth.context_processors import customer

        request = rf.get("/")
        ctx = customer(request)
        assert ctx == {"auth_customer": None}
