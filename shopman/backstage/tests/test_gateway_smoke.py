from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings
from shopman.orderman.models import IdempotencyKey, Order
from shopman.payman.models import PaymentIntent, PaymentTransaction

from shopman.backstage.services.gateway_smoke import run_gateway_smoke


@pytest.mark.django_db
def test_gateway_smoke_local_fixtures_pass_and_rollback():
    before = {
        "orders": Order.objects.count(),
        "intents": PaymentIntent.objects.count(),
        "transactions": PaymentTransaction.objects.count(),
        "idempotency": IdempotencyKey.objects.count(),
    }

    report = run_gateway_smoke(
        include_local=True,
        include_sandbox_readiness=False,
        rollback=True,
    )

    assert report.status == "passed"
    assert report.counts["passed"] == 5
    assert not report.failed
    assert Order.objects.count() == before["orders"]
    assert PaymentIntent.objects.count() == before["intents"]
    assert PaymentTransaction.objects.count() == before["transactions"]
    assert IdempotencyKey.objects.count() == before["idempotency"]


@pytest.mark.django_db
def test_gateway_smoke_command_outputs_json_for_local_contract():
    stdout = StringIO()

    call_command("smoke_gateways", local_only=True, json=True, stdout=stdout)

    data = json.loads(stdout.getvalue())
    assert data["status"] == "passed"
    assert data["rolled_back"] is True
    assert data["counts"]["passed"] == 5
    assert {check["provider"] for check in data["checks"]} == {"efi", "stripe", "ifood"}


@pytest.mark.django_db
@override_settings(
    SHOPMAN_EFI={"sandbox": True, "client_id": "", "client_secret": "", "certificate_path": "", "pix_key": ""},
    SHOPMAN_EFI_WEBHOOK={"webhook_token": ""},
    SHOPMAN_STRIPE={"secret_key": "", "webhook_secret": ""},
    SHOPMAN_IFOOD={"webhook_token": "", "merchant_id": ""},
    MANYCHAT_API_TOKEN="",
    MANYCHAT_WEBHOOK_SECRET="",
    DOORMAN={"ACCESS_LINK_API_KEY": ""},
)
def test_gateway_smoke_sandbox_required_blocks_without_credentials():
    stdout = StringIO()

    with pytest.raises(CommandError):
        call_command("smoke_gateways", sandbox_only=True, require_sandbox=True, json=True, stdout=stdout)

    data = json.loads(stdout.getvalue())
    assert data["status"] == "blocked_by_credentials"
    assert data["counts"]["blocked_by_credentials"] == 4
    assert all(check["scope"] == "sandbox_readiness" for check in data["checks"])
