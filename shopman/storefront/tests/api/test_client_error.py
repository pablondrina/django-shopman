"""Ingestão de erro do cliente (WP-S3): sanitização de PII + endpoint."""

from __future__ import annotations

import json

import pytest
from django.test import Client

from shopman.storefront.api.telemetry import sanitize_client_report

pytestmark = pytest.mark.django_db

ENDPOINT = "/api/v1/storefront/client-error/"


class TestSanitizeClientReport:
    def test_keeps_only_allow_listed_string_fields(self):
        report = sanitize_client_report(
            {
                "message": "Boom",
                "kind": "unhandledrejection",
                "secret": "drop-me",
                "count": 3,
            }
        )
        assert report == {"message": "Boom", "kind": "unhandledrejection"}

    def test_redacts_email_and_phone_from_message_and_stack(self):
        report = sanitize_client_report(
            {
                "message": "falhou para ana@example.com no +55 43 98404-9009",
                "stack": "at fn (ana@example.com)",
            }
        )
        assert "example.com" not in report["message"]
        assert "[email]" in report["message"]
        assert "[phone]" in report["message"]
        assert "[email]" in report["stack"]

    def test_strips_query_and_fragment_from_url(self):
        report = sanitize_client_report({"message": "x", "url": "/pedido/ORD-1?token=abc#frag"})
        assert report["url"] == "/pedido/ORD-1"

    def test_truncates_oversized_fields(self):
        report = sanitize_client_report({"message": "x" * 5000})
        assert len(report["message"]) == 500

    def test_non_dict_payload_is_empty(self):
        assert sanitize_client_report("nope") == {}
        assert sanitize_client_report(None) == {}


class TestClientErrorEndpoint:
    def test_accepts_and_logs_a_sanitized_report(self, client: Client, monkeypatch):
        from shopman.storefront.api import telemetry

        calls: list = []
        monkeypatch.setattr(telemetry.logger, "error", lambda *a, **k: calls.append((a, k)))
        resp = client.post(
            ENDPOINT,
            data=json.dumps({"message": "TypeError x", "kind": "vue:error", "url": "/menu?q=1"}),
            content_type="application/json",
        )
        assert resp.status_code == 202
        assert resp.json() == {"ok": True}
        assert calls, "esperava um log de erro"
        assert "storefront_client_error" in calls[0][0][0]
        # a URL virou só o caminho no relatório sanitizado
        assert calls[0][1]["extra"]["client_report"]["url"] == "/menu"

    def test_empty_message_is_accepted_but_not_logged(self, client: Client, monkeypatch):
        from shopman.storefront.api import telemetry

        calls: list = []
        monkeypatch.setattr(telemetry.logger, "error", lambda *a, **k: calls.append((a, k)))
        resp = client.post(
            ENDPOINT,
            data=json.dumps({"kind": "vue:error"}),
            content_type="application/json",
        )
        assert resp.status_code == 202
        assert not calls

    def test_no_csrf_required(self, client: Client):
        # authentication_classes=[] → sem enforcement de CSRF (erros podem ocorrer
        # antes de a sessão/token existirem). Client enforce_csrf p/ garantir.
        csrf_client = Client(enforce_csrf_checks=True)
        resp = csrf_client.post(
            ENDPOINT,
            data=json.dumps({"message": "no csrf"}),
            content_type="application/json",
        )
        assert resp.status_code == 202
