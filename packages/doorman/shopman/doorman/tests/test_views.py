"""
Integration tests for Auth views (Phase 4.2).

Tests the full request/verify flow via RequestFactory, including
form and JSON content negotiation.

Note: Since auth URLs may not be registered in the test project,
form-based redirects are patched to avoid NoReverseMatch errors.
JSON responses don't redirect, so they test the full flow without mocks.
"""

import json
from unittest.mock import patch

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponseRedirect
from django.test import RequestFactory, override_settings
from shopman.doorman.models import VerificationCode
from shopman.doorman.models.verification_code import generate_raw_code
from shopman.doorman.services.access_link import AccessLinkService
from shopman.doorman.views.access_link import AccessLinkCreateView
from shopman.doorman.views.health import HealthCheckView
from shopman.doorman.views.verification_code import VerificationCodeRequestView, VerificationCodeVerifyView

# Patch _build_url globally for all verify-success tests since
# auth URLs are not registered in the test project.
_PATCH_BUILD_URL = patch.object(
    AccessLinkService, "_build_url", return_value="https://test.local/auth/access-link/?t=mock"
)


class FakeSender:
    """Sender that captures the raw code instead of sending it."""

    def __init__(self):
        self.last_code = None

    def send_code(self, target, code, method):
        self.last_code = code
        return True


def _fake_redirect(to, *args, **kwargs):
    """Redirect without URL reversal — just use the name as-is."""
    return HttpResponseRedirect(f"/{to}/")


def _make_request(method="get", path="/", data=None, content_type=None, session=None):
    """Build a request with a real session."""
    factory = RequestFactory()
    kwargs = {}
    if content_type:
        kwargs["content_type"] = content_type
    if method == "get":
        request = factory.get(path, data or {})
    else:
        request = factory.post(path, data or "", **kwargs)
    request.session = session or SessionStore()
    return request


# ===================================================
# VerificationCodeRequestView
# ===================================================


@pytest.mark.django_db
class TestVerificationCodeRequestViewForm:
    """Test code request view with form POST."""

    def test_get_renders_template(self):
        request = _make_request("get")
        response = VerificationCodeRequestView.as_view()(request)
        assert response.status_code == 200

    def test_post_empty_phone_returns_error(self):
        request = _make_request(
            "post",
            data="phone=",
            content_type="application/x-www-form-urlencoded",
        )
        response = VerificationCodeRequestView.as_view()(request)
        assert response.status_code == 200  # re-renders form

    @patch("shopman.doorman.views.verification_code.redirect", side_effect=_fake_redirect)
    def test_post_valid_phone_redirects(self, mock_redirect):
        sender = FakeSender()

        request = _make_request(
            "post",
            data="phone=41999999999",
            content_type="application/x-www-form-urlencoded",
        )
        with patch("shopman.doorman.adapter.DefaultAuthAdapter.send_code", sender.send_code):
            response = VerificationCodeRequestView.as_view()(request)

        assert response.status_code == 302
        assert sender.last_code is not None
        assert len(sender.last_code) == 6
        # Phone stored in session
        assert request.session.get("auth_target") == "+5541999999999"


@pytest.mark.django_db
class TestVerificationCodeRequestViewJSON:
    """Test code request view with JSON POST."""

    def test_json_empty_phone_returns_400(self):
        body = json.dumps({"phone": ""})
        request = _make_request("post", data=body, content_type="application/json")
        response = VerificationCodeRequestView.as_view()(request)
        assert response.status_code == 400

    def test_json_invalid_json_returns_400(self):
        request = _make_request("post", data="not json", content_type="application/json")
        response = VerificationCodeRequestView.as_view()(request)
        assert response.status_code == 400

    def test_json_valid_phone_returns_success(self):
        sender = FakeSender()

        body = json.dumps({"phone": "41999999999"})
        request = _make_request("post", data=body, content_type="application/json")
        with patch("shopman.doorman.adapter.DefaultAuthAdapter.send_code", sender.send_code):
            response = VerificationCodeRequestView.as_view()(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert data["phone"] == "+5541999999999"


# ===================================================
# VerificationCodeVerifyView
# ===================================================


@pytest.mark.django_db
class TestVerificationCodeVerifyViewForm:
    """Test code verify view with form POST."""

    @patch("shopman.doorman.views.verification_code.redirect", side_effect=_fake_redirect)
    def test_get_without_session_phone_redirects(self, mock_redirect):
        request = _make_request("get")
        response = VerificationCodeVerifyView.as_view()(request)
        assert response.status_code == 302  # redirect to code-request

    def test_get_with_session_phone_renders(self):
        session = SessionStore()
        session["auth_target"] = "+5541999999999"
        session.save()
        request = _make_request("get", session=session)
        response = VerificationCodeVerifyView.as_view()(request)
        assert response.status_code == 200

    def test_post_missing_code_returns_error(self):
        request = _make_request(
            "post",
            data="phone=%2B5541999999999&code=",
            content_type="application/x-www-form-urlencoded",
        )
        response = VerificationCodeVerifyView.as_view()(request)
        assert response.status_code == 200  # re-renders form with error

    def test_post_wrong_code_returns_error(self):
        raw_code, hmac_digest = generate_raw_code()
        VerificationCode.objects.create(
            code_hash=hmac_digest,
            target_value="+5541999999999",
            purpose=VerificationCode.Purpose.LOGIN,
            status=VerificationCode.Status.SENT,
        )
        request = _make_request(
            "post",
            data="phone=%2B5541999999999&code=000000",
            content_type="application/x-www-form-urlencoded",
        )
        response = VerificationCodeVerifyView.as_view()(request)
        assert response.status_code == 200  # re-renders form


@pytest.mark.django_db
class TestVerificationCodeVerifyViewJSON:
    """Test code verify view with JSON POST."""

    def test_json_missing_fields_returns_400(self):
        body = json.dumps({"phone": "", "code": ""})
        request = _make_request("post", data=body, content_type="application/json")
        response = VerificationCodeVerifyView.as_view()(request)
        assert response.status_code == 400

    def test_json_wrong_code_returns_400(self):
        raw_code, hmac_digest = generate_raw_code()
        VerificationCode.objects.create(
            code_hash=hmac_digest,
            target_value="+5541999999999",
            purpose=VerificationCode.Purpose.LOGIN,
            status=VerificationCode.Status.SENT,
        )
        body = json.dumps({"phone": "+5541999999999", "code": "000000"})
        request = _make_request("post", data=body, content_type="application/json")
        response = VerificationCodeVerifyView.as_view()(request)

        assert response.status_code == 400
        data = json.loads(response.content)
        assert "error" in data
        assert "attempts_remaining" in data

    @_PATCH_BUILD_URL
    def test_json_correct_code_returns_success(self, _mock_url):
        from shopman.guestman.models import Customer

        Customer.objects.create(
            ref="VIEW-001",
            first_name="View",
            last_name="Test",
            phone="+5541999999999",
        )

        raw_code, hmac_digest = generate_raw_code()
        VerificationCode.objects.create(
            code_hash=hmac_digest,
            target_value="+5541999999999",
            purpose=VerificationCode.Purpose.LOGIN,
            status=VerificationCode.Status.SENT,
        )
        body = json.dumps({"phone": "+5541999999999", "code": raw_code})
        request = _make_request("post", data=body, content_type="application/json")
        response = VerificationCodeVerifyView.as_view()(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert "customer_id" in data

    @_PATCH_BUILD_URL
    def test_json_correct_email_code_returns_success(self, _mock_url):
        from shopman.guestman.models import Customer

        Customer.objects.create(
            ref="VIEW-EMAIL-001",
            first_name="Email",
            last_name="Test",
            email="email@example.com",
        )

        raw_code, hmac_digest = generate_raw_code()
        VerificationCode.objects.create(
            code_hash=hmac_digest,
            target_value="email@example.com",
            purpose=VerificationCode.Purpose.LOGIN,
            status=VerificationCode.Status.SENT,
            delivery_method=VerificationCode.DeliveryMethod.EMAIL,
        )
        body = json.dumps({"target": "email@example.com", "code": raw_code})
        request = _make_request("post", data=body, content_type="application/json")
        response = VerificationCodeVerifyView.as_view()(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True


# ===================================================
# Full Flow: Request -> Verify
# ===================================================


@pytest.mark.django_db
class TestFullFlow:
    """End-to-end flow: request code -> verify -> session created."""

    @_PATCH_BUILD_URL
    def test_full_flow_json(self, _mock_url):
        """Request code via JSON, then verify via JSON."""
        from shopman.guestman.models import Customer

        Customer.objects.create(
            ref="FLOW-001",
            first_name="Flow",
            last_name="Test",
            phone="+5541888888888",
        )

        sender = FakeSender()

        # Step 1: Request code
        body = json.dumps({"phone": "41888888888"})
        request1 = _make_request("post", data=body, content_type="application/json")
        with patch("shopman.doorman.adapter.DefaultAuthAdapter.send_code", sender.send_code):
            response1 = VerificationCodeRequestView.as_view()(request1)

        assert response1.status_code == 200
        raw_code = sender.last_code
        assert raw_code is not None

        # Step 2: Verify code
        body2 = json.dumps({"phone": "+5541888888888", "code": raw_code})
        request2 = _make_request("post", data=body2, content_type="application/json")
        response2 = VerificationCodeVerifyView.as_view()(request2)

        assert response2.status_code == 200
        data = json.loads(response2.content)
        assert data["success"] is True
        assert "customer_id" in data


# ===================================================
# AccessLinkCreateView edge cases
# ===================================================

TEST_API_KEY = "test-auth-api-key-2026"


@pytest.mark.django_db
class TestAccessLinkCreateViewEdges:
    """Edge case tests for AccessLinkCreateView."""

    def _post_create(self, data, headers=None):
        factory = RequestFactory()
        body = json.dumps(data)
        kwargs = {"content_type": "application/json"}
        if headers:
            kwargs.update(headers)
        request = factory.post("/auth/access-link/create/", body, **kwargs)
        view = AccessLinkCreateView.as_view()
        with patch.object(
            AccessLinkService,
            "_build_url",
            return_value="https://test.local/auth/access-link/?t=mock",
        ):
            return view(request)

    @override_settings(DOORMAN={"ACCESS_LINK_API_KEY": ""})
    def test_create_invalid_json(self):
        """Invalid JSON should return 400."""
        factory = RequestFactory()
        request = factory.post(
            "/auth/access-link/create/",
            "not-json",
            content_type="application/json",
        )
        response = AccessLinkCreateView.as_view()(request)
        assert response.status_code == 400

    @override_settings(DOORMAN={"ACCESS_LINK_API_KEY": ""})
    def test_create_missing_customer_id(self):
        """Missing customer_id should return 400."""
        response = self._post_create({})
        assert response.status_code == 400

    @override_settings(DOORMAN={"ACCESS_LINK_API_KEY": ""})
    def test_create_customer_not_found(self):
        """Non-existent customer_id should return 404."""
        import uuid

        response = self._post_create({"customer_id": str(uuid.uuid4())})
        assert response.status_code == 404

    @override_settings(DOORMAN={"ACCESS_LINK_API_KEY": ""})
    def test_create_customer_inactive(self, customer):
        """Inactive customer should return 400."""
        from shopman.doorman.protocols.customer import AuthCustomerInfo

        inactive = AuthCustomerInfo(
            uuid=customer.uuid, name="Inactive", phone=customer.phone,
            email=customer.email, is_active=False,
        )
        with patch("shopman.doorman.views.access_link.get_customer_resolver") as mock_resolver:
            mock_resolver.return_value.get_by_uuid.return_value = inactive
            response = self._post_create({"customer_id": str(customer.uuid)})
        assert response.status_code == 400


# ===================================================
# HealthCheckView
# ===================================================


@pytest.mark.django_db
class TestHealthCheckView:
    """Tests for health check endpoint."""

    def test_health_returns_200(self):
        factory = RequestFactory()
        request = factory.get("/auth/health/")
        response = HealthCheckView.as_view()(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "ok"
