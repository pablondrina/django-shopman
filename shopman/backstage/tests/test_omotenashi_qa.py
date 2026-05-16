from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command

from shopman.backstage.services.omotenashi_qa import OmotenashiQACheck, OmotenashiQAReport


def test_omotenashi_qa_command_outputs_json():
    report = OmotenashiQAReport(
        generated_at="2026-05-05T12:00:00+00:00",
        checks=(
            OmotenashiQACheck(
                id="mobile.catalog.browse",
                surface="storefront",
                viewport="mobile 375x812",
                persona="cliente anonimo",
                title="Explorar cardapio",
                url="/menu/",
                expectation="Menu sem dead end.",
                evidence="sku=CROISSANT",
                status="ready",
            ),
        ),
    )
    stdout = StringIO()

    with patch(
        "shopman.backstage.management.commands.omotenashi_qa.build_omotenashi_qa_report",
        return_value=report,
    ):
        call_command("omotenashi_qa", json=True, stdout=stdout)

    data = json.loads(stdout.getvalue())
    assert data["status"] == "ready"
    assert data["counts"] == {"missing": 0, "ready": 1, "total": 1}
    assert data["checks"][0]["url"] == "/menu/"


def test_omotenashi_qa_strict_fails_when_seed_evidence_is_missing():
    report = OmotenashiQAReport(
        generated_at="2026-05-05T12:00:00+00:00",
        checks=(
            OmotenashiQACheck(
                id="mobile.payment.pix_expired",
                surface="storefront",
                viewport="mobile 375x812",
                persona="cliente distraido",
                title="PIX expirado",
                url="/pedido/ORDER_REF/pagamento/",
                expectation="Tela deve oferecer recuperacao.",
                evidence="-",
                status="missing",
                blocker="Rode make seed.",
            ),
        ),
    )

    with patch(
        "shopman.backstage.management.commands.omotenashi_qa.build_omotenashi_qa_report",
        return_value=report,
    ):
        with pytest.raises(CommandError):
            call_command("omotenashi_qa", strict=True, stdout=StringIO())
