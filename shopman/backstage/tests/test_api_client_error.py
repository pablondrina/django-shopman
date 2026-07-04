"""Telemetria de erro de cliente das superfícies de operador (api/v1/backstage/client-error/).

Gêmeo operador do endpoint do storefront: o ``operator-kit`` (Nuxt layer) posta erros
não-tratados aqui. Sem auth (o erro pode ocorrer antes/na expiração da sessão), PII
sanitizada, rate-limited, write-only. Loga em nível error → Sentry opt-in.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse

from shopman.backstage.api.telemetry import sanitize_client_report


@pytest.mark.django_db
def test_valid_report_is_accepted_and_logged(client):
    # Patch no logger (independente do LOGGING/propagate do deployment).
    with patch("shopman.backstage.api.telemetry.logger") as logger:
        response = client.post(
            reverse("api-backstage-client-error"),
            data={"message": "TypeError: x is undefined", "source": "vue", "kind": "render"},
            content_type="application/json",
        )
    assert response.status_code == 202
    assert response.json() == {"ok": True}
    logger.error.assert_called_once()
    assert "TypeError: x is undefined" in logger.error.call_args.args[1]


@pytest.mark.django_db
def test_no_auth_required(client):
    # Sem sessão de operador — ainda aceita (erro pode ocorrer antes de logar).
    response = client.post(
        reverse("api-backstage-client-error"),
        data={"message": "boom"},
        content_type="application/json",
    )
    assert response.status_code == 202


@pytest.mark.django_db
def test_empty_message_is_accepted_but_not_logged(client):
    with patch("shopman.backstage.api.telemetry.logger") as logger:
        response = client.post(
            reverse("api-backstage-client-error"),
            data={"source": "vue"},
            content_type="application/json",
        )
    assert response.status_code == 202
    logger.error.assert_not_called()


class TestSanitize:
    def test_redacts_email_and_phone(self):
        report = sanitize_client_report(
            {"message": "falha para joao@ex.com no fone +55 43 99999-8888"}
        )
        assert "joao@ex.com" not in report["message"]
        assert "99999-8888" not in report["message"]
        assert "[email]" in report["message"] and "[phone]" in report["message"]

    def test_strips_url_query_and_fragment(self):
        report = sanitize_client_report({"message": "x", "url": "https://pos/venda?token=abc#y"})
        assert report["url"] == "https://pos/venda"

    def test_drops_unknown_fields_and_non_str(self):
        report = sanitize_client_report({"message": "x", "evil": {"a": 1}, "stack": 123})
        assert set(report) == {"message"}

    def test_truncates_long_fields(self):
        report = sanitize_client_report({"message": "x" * 999})
        assert len(report["message"]) == 500

    def test_non_dict_payload_is_empty(self):
        assert sanitize_client_report("not a dict") == {}
        assert sanitize_client_report(None) == {}
