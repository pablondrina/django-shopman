"""POST /api/v1/auth/access/ — magic-link token → store-domain session.

The destination is derived from the token metadata (no client `next`), so a link
can only ever land on a safe in-store path. The session cookie is set on the
store host (the Nuxt page posts here through the BFF).
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone
from shopman.doorman.models import AccessLink

pytestmark = pytest.mark.django_db


class TestAccessLinkExchangeApi:
    URL = "/api/v1/auth/access/"

    def _token(self, customer, *, metadata=None, minutes=5):
        return AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=AccessLink.Source.INTERNAL,
            metadata=metadata or {},
            expires_at=timezone.now() + timedelta(minutes=minutes),
        )

    def test_valid_token_creates_session_and_defaults_to_account(self, client: Client, customer):
        _link, raw_token = self._token(customer)

        response = client.post(self.URL, {"token": raw_token})

        assert response.status_code == 200
        assert client.session.get("_auth_user_id") is not None
        body = response.json()
        assert body["redirect"] == "/account"
        assert body["is_authenticated"] is True

    def test_order_metadata_grants_access_and_redirects_to_tracking(self, client: Client, customer):
        _link, raw_token = self._token(customer, metadata={"order_ref": "ORD-NUXT-1"})

        response = client.post(self.URL, {"token": raw_token})

        assert response.status_code == 200
        assert response.json()["redirect"] == "/tracking/ORD-NUXT-1"
        assert "ORD-NUXT-1" in client.session.get("shopman_order_access_refs", [])

    def test_payment_action_redirects_to_payment_page(self, client: Client, customer):
        _link, raw_token = self._token(customer, metadata={"order_ref": "ORD-PAY-1", "action": "payment"})

        response = client.post(self.URL, {"token": raw_token})

        assert response.json()["redirect"] == "/pedido/ORD-PAY-1/pagamento"

    def test_reorder_action_redirects_to_order_history(self, client: Client, customer):
        _link, raw_token = self._token(customer, metadata={"order_ref": "ORD-RE-1", "action": "reorder"})

        response = client.post(self.URL, {"token": raw_token})

        assert response.json()["redirect"] == "/account/pedidos"

    def test_expired_token_is_rejected_without_session(self, client: Client, customer):
        _link, raw_token = self._token(customer, minutes=-1)

        response = client.post(self.URL, {"token": raw_token})

        assert response.status_code == 400
        assert client.session.get("_auth_user_id") is None

    def test_invalid_token_is_rejected(self, client: Client):
        response = client.post(self.URL, {"token": "nonexistent-token"})

        assert response.status_code == 400
        assert client.session.get("_auth_user_id") is None

    def test_used_token_is_rejected(self, client: Client, customer):
        link, raw_token = self._token(customer)
        link.used_at = timezone.now() - timedelta(minutes=5)
        link.save()

        response = client.post(self.URL, {"token": raw_token})

        assert response.status_code == 400
        assert client.session.get("_auth_user_id") is None

    def test_cart_session_key_adopted_when_session_empty(self, client: Client, customer):
        # Fluxo do site: o código NB dobrou a sacola anônima na metadata do token.
        _link, raw_token = self._token(customer, metadata={"cart_session_key": "sk_from_site"})

        response = client.post(self.URL, {"token": raw_token})

        assert response.status_code == 200
        assert client.session.get("cart_session_key") == "sk_from_site"

    def test_cart_session_key_not_overridden_when_session_has_cart(self, client: Client, customer):
        session = client.session
        session["cart_session_key"] = "sk_local"
        session.save()
        _link, raw_token = self._token(customer, metadata={"cart_session_key": "sk_from_site"})

        response = client.post(self.URL, {"token": raw_token})

        assert response.status_code == 200
        assert client.session.get("cart_session_key") == "sk_local"

    def test_missing_token_is_rejected(self, client: Client):
        response = client.post(self.URL, {})

        assert response.status_code == 400
