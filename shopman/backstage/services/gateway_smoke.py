"""Gateway smoke checks for local fixtures and sandbox readiness."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from unittest.mock import patch

from django.conf import settings
from django.db import transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from shopman.orderman.models import IdempotencyKey, Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentTransaction

from shopman.backstage.services.financial_reconciliation import build_financial_reconciliation
from shopman.shop.models import Channel
from shopman.shop.services import sessions as session_service

SmokeStatus = Literal["passed", "failed", "ready", "blocked_by_credentials", "blocked_by_implementation"]
SmokeScope = Literal["local_fixture", "sandbox_readiness"]

_LOCAL_EFI_WEBHOOK = {"webhook_token": "gateway-smoke-efi-token"}
_LOCAL_IFOOD = {"webhook_token": "gateway-smoke-ifood-token", "merchant_id": "gateway-smoke-merchant"}
_LOCAL_STRIPE = {
    "secret_key": "sk_test_gateway_smoke",
    "webhook_secret": "whsec_gateway_smoke",
    "capture_method": "manual",
    "domain": "http://localhost:8000",
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GatewaySmokeCheck:
    provider: str
    name: str
    scope: SmokeScope
    status: SmokeStatus
    message: str
    details: dict[str, int | str | bool | list[str]] = field(default_factory=dict)

    @property
    def is_failure(self) -> bool:
        return self.status == "failed"

    @property
    def is_blocked(self) -> bool:
        return self.status.startswith("blocked_by_")

    def as_dict(self) -> dict:
        data = {
            "provider": self.provider,
            "name": self.name,
            "scope": self.scope,
            "status": self.status,
            "message": self.message,
        }
        if self.details:
            data["details"] = self.details
        return data


@dataclass(frozen=True)
class GatewaySmokeReport:
    generated_at: datetime
    checks: tuple[GatewaySmokeCheck, ...]
    rolled_back: bool
    sandbox_required: bool

    @property
    def failed(self) -> bool:
        return any(check.is_failure for check in self.checks)

    @property
    def sandbox_blocked(self) -> bool:
        return any(check.scope == "sandbox_readiness" and check.is_blocked for check in self.checks)

    @property
    def blocking(self) -> bool:
        return self.failed or (self.sandbox_required and self.sandbox_blocked)

    @property
    def status(self) -> str:
        if self.failed:
            return "failed"
        if self.sandbox_required and self.sandbox_blocked:
            return "blocked_by_credentials"
        if self.sandbox_blocked:
            return "passed_local_sandbox_blocked"
        return "passed"

    @property
    def counts(self) -> dict[str, int]:
        statuses = ("passed", "failed", "ready", "blocked_by_credentials", "blocked_by_implementation")
        return {status: sum(1 for check in self.checks if check.status == status) for status in statuses}

    def as_dict(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(),
            "status": self.status,
            "rolled_back": self.rolled_back,
            "sandbox_required": self.sandbox_required,
            "counts": self.counts,
            "checks": [check.as_dict() for check in self.checks],
        }


class GatewaySmokeError(Exception):
    """Raised by a local smoke fixture when the observed state is wrong."""

    def __init__(self, message: str, *, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


def run_gateway_smoke(
    *,
    include_local: bool = True,
    include_sandbox_readiness: bool = True,
    require_sandbox: bool = False,
    rollback: bool = True,
) -> GatewaySmokeReport:
    """Run gateway smoke checks and return a machine-readable report."""
    checks: list[GatewaySmokeCheck] = []
    if include_local:
        checks.extend(_run_local_fixtures(rollback=rollback))
    if include_sandbox_readiness:
        checks.extend(_sandbox_readiness_checks())
    return GatewaySmokeReport(
        generated_at=timezone.now(),
        checks=tuple(checks),
        rolled_back=rollback,
        sandbox_required=require_sandbox,
    )


def _run_local_fixtures(*, rollback: bool) -> tuple[GatewaySmokeCheck, ...]:
    checks: list[GatewaySmokeCheck] = []
    with override_settings(
        SHOPMAN_EFI_WEBHOOK=_LOCAL_EFI_WEBHOOK,
        SHOPMAN_IFOOD=_LOCAL_IFOOD,
        SHOPMAN_STRIPE=_LOCAL_STRIPE,
    ):
        with transaction.atomic():
            _ensure_channels()
            for provider, name, func in (
                ("efi", "pix_duplicate_webhook", _smoke_efi_pix_duplicate_webhook),
                ("efi", "pix_late_after_cancel_refund", _smoke_efi_late_after_cancel_refund),
                ("stripe", "payment_succeeded_duplicate_webhook", _smoke_stripe_duplicate_capture),
                ("stripe", "refund_cumulative_out_of_order", _smoke_stripe_refund_cumulative_out_of_order),
                ("ifood", "order_duplicate_webhook", _smoke_ifood_duplicate_order),
            ):
                checks.append(_execute_local_check(provider, name, func))
            if rollback:
                transaction.set_rollback(True)
    return tuple(checks)


def _execute_local_check(provider: str, name: str, func) -> GatewaySmokeCheck:
    try:
        with transaction.atomic():
            details = func()
    except GatewaySmokeError as exc:
        return GatewaySmokeCheck(
            provider=provider,
            name=name,
            scope="local_fixture",
            status="failed",
            message=exc.message,
            details=_clean_details(exc.details),
        )
    except Exception as exc:
        logger.exception("gateway_smoke.local_fixture_failed provider=%s name=%s", provider, name)
        return GatewaySmokeCheck(
            provider=provider,
            name=name,
            scope="local_fixture",
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )
    return GatewaySmokeCheck(
        provider=provider,
        name=name,
        scope="local_fixture",
        status="passed",
        message="Contrato local executado no caminho canônico.",
        details=_clean_details(details),
    )


def _ensure_channels() -> None:
    Channel.objects.get_or_create(ref="web", defaults={"name": "Web", "is_active": True})
    Channel.objects.get_or_create(ref="ifood", defaults={"name": "iFood", "is_active": True})


def _smoke_efi_pix_duplicate_webhook() -> dict:
    client = APIClient()
    order = _create_order_with_payment(payment_method="pix")
    intent = _create_pix_intent(order, gateway_id="smoke_efi_txid_duplicate")
    payload = {
        "pix": [
            {
                "txid": intent.gateway_id,
                "endToEndId": "E-SMOKE-EFI-DUPLICATE",
                "valor": _money(order.total_q),
            }
        ]
    }

    first = _post_efi(client, payload)
    second = _post_efi(client, payload)
    intent.refresh_from_db()
    captures = PaymentTransaction.objects.filter(intent=intent, type=PaymentTransaction.Type.CAPTURE).count()

    _expect(first.status_code == 200, "EFI PIX first webhook did not return 200", response=_response(first))
    _expect(second.status_code == 200, "EFI PIX replay did not return 200", response=_response(second))
    _expect(first.data.get("processed") == 1, "EFI PIX first webhook was not processed once", response=_response(first))
    _expect(second.data.get("replays") == 1, "EFI PIX replay was not detected", response=_response(second))
    _expect(intent.status == "captured", "EFI PIX intent was not captured", intent_status=intent.status)
    _expect(captures == 1, "EFI PIX duplicate created extra capture transaction", capture_count=captures)

    return {
        "order_ref": order.ref,
        "intent_ref": intent.ref,
        "capture_count": captures,
        "idempotency_rows": IdempotencyKey.objects.filter(scope="webhook:efi-pix").count(),
    }


def _smoke_efi_late_after_cancel_refund() -> dict:
    client = APIClient()
    order = _create_order_with_payment(payment_method="pix")
    intent = _create_pix_intent(order, gateway_id="smoke_efi_txid_late_cancel")
    order.transition_status(Order.Status.CANCELLED, actor="gateway-smoke")

    response = _post_efi(
        client,
        {
            "pix": [
                {
                    "txid": intent.gateway_id,
                    "endToEndId": "E-SMOKE-EFI-LATE-CANCEL",
                    "valor": _money(order.total_q),
                }
            ]
        },
    )
    intent.refresh_from_db()
    captured_q = PaymentService.captured_total(intent.ref)
    refunded_q = PaymentService.refunded_total(intent.ref)
    report = build_financial_reconciliation(reconciliation_date=timezone.localdate())
    issue_codes = [issue.code for issue in report.issues if issue.order_ref == order.ref]

    _expect(response.status_code == 200, "EFI late webhook after cancel did not return 200", response=_response(response))
    _expect(intent.status == "refunded", "EFI late webhook after cancel did not refund the intent", intent_status=intent.status)
    _expect(captured_q == order.total_q, "EFI late webhook did not record the capture", captured_q=captured_q)
    _expect(refunded_q == order.total_q, "EFI late webhook did not refund the captured balance", refunded_q=refunded_q)
    _expect(
        "terminal_order_with_captured_balance" not in issue_codes,
        "Daily reconciliation still sees captured balance after automatic refund",
        issue_codes=issue_codes,
    )

    return {
        "order_ref": order.ref,
        "intent_ref": intent.ref,
        "captured_q": captured_q,
        "refunded_q": refunded_q,
    }


def _smoke_stripe_duplicate_capture() -> dict:
    client = APIClient()
    order = _create_order_with_payment(payment_method="card")
    intent = _create_card_intent(order, gateway_id="pi_smoke_duplicate")
    event = _stripe_payment_succeeded_event(
        event_id="evt_smoke_stripe_duplicate",
        stripe_pi_id=intent.gateway_id,
        intent_ref=intent.ref,
        order_ref=order.ref,
    )

    first = _post_stripe(client, event)
    second = _post_stripe(client, event)
    intent.refresh_from_db()
    captures = PaymentTransaction.objects.filter(intent=intent, type=PaymentTransaction.Type.CAPTURE).count()

    _expect(first.status_code == 200, "Stripe first webhook did not return 200", response=_response(first))
    _expect(second.status_code == 200, "Stripe replay did not return 200", response=_response(second))
    _expect(intent.status == "captured", "Stripe intent was not captured", intent_status=intent.status)
    _expect(captures == 1, "Stripe duplicate created extra capture transaction", capture_count=captures)

    return {
        "order_ref": order.ref,
        "intent_ref": intent.ref,
        "capture_count": captures,
        "idempotency_rows": IdempotencyKey.objects.filter(scope="webhook:stripe").count(),
    }


def _smoke_stripe_refund_cumulative_out_of_order() -> dict:
    client = APIClient()
    order = _create_order_with_payment(payment_method="card")
    intent = _create_card_intent(order, gateway_id="pi_smoke_refund")
    PaymentService.authorize(intent.ref, gateway_id=intent.gateway_id)
    PaymentService.capture(intent.ref, gateway_id="ch_smoke_refund")

    full_refund = _stripe_charge_refunded_event(
        event_id="evt_smoke_refund_full",
        stripe_pi_id=intent.gateway_id,
        amount_q=order.total_q,
        amount_refunded_q=order.total_q,
        charge_id="ch_smoke_refund",
    )
    stale_partial = _stripe_charge_refunded_event(
        event_id="evt_smoke_refund_stale_partial",
        stripe_pi_id=intent.gateway_id,
        amount_q=order.total_q,
        amount_refunded_q=400,
        charge_id="ch_smoke_refund",
    )

    full_response = _post_stripe(client, full_refund)
    stale_response = _post_stripe(client, stale_partial)
    refunded_total = PaymentService.refunded_total(intent.ref)
    refund_rows = list(
        PaymentTransaction.objects.filter(intent=intent, type=PaymentTransaction.Type.REFUND)
        .order_by("created_at")
        .values_list("amount_q", flat=True)
    )

    _expect(full_response.status_code == 200, "Stripe full refund webhook did not return 200", response=_response(full_response))
    _expect(stale_response.status_code == 200, "Stripe stale refund webhook did not return 200", response=_response(stale_response))
    _expect(refunded_total == order.total_q, "Stripe cumulative refund total drifted", refunded_total=refunded_total)
    _expect(refund_rows == [order.total_q], "Stripe stale refund event created a backwards delta", refund_rows=refund_rows)

    return {
        "order_ref": order.ref,
        "intent_ref": intent.ref,
        "refunded_total_q": refunded_total,
        "refund_rows": [str(row) for row in refund_rows],
    }


def _smoke_ifood_duplicate_order() -> dict:
    client = APIClient()
    order_id = "IFOOD-SMOKE-DUPLICATE"
    payload = _ifood_payload(order_id)

    first = _post_ifood(client, payload)
    second = _post_ifood(client, payload)
    order_count = Order.objects.filter(channel_ref="ifood", external_ref=order_id).count()
    order_ref = Order.objects.filter(channel_ref="ifood", external_ref=order_id).values_list("ref", flat=True).first()

    _expect(first.status_code == 200, "iFood first webhook did not return 200", response=_response(first))
    _expect(second.status_code == 200, "iFood duplicate webhook did not return 200", response=_response(second))
    _expect(first.data.get("status") == "accepted", "iFood first webhook was not accepted", response=_response(first))
    _expect(order_count == 1, "iFood duplicate created more than one order", order_count=order_count)
    _expect(bool(order_ref), "iFood accepted webhook did not create an order")

    return {
        "order_ref": str(order_ref),
        "external_ref": order_id,
        "order_count": order_count,
        "idempotency_rows": IdempotencyKey.objects.filter(scope="webhook:ifood").count(),
    }


def _create_order_with_payment(*, payment_method: str) -> Order:
    session = session_service.create_session(
        "web",
        handle_type="gateway_smoke",
        handle_ref=f"gateway-smoke-{payment_method}",
        data={"origin_channel": "web"},
    )
    session_service.modify_session(
        session_key=session.session_key,
        channel_ref="web",
        ops=[
            {"op": "add_line", "sku": "GATEWAY-SMOKE-SKU", "qty": 1, "unit_price_q": 1000},
            {"op": "set_data", "path": "payment.method", "value": payment_method},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        ],
        ctx={"actor": "gateway-smoke"},
    )
    result = session_service.commit_session(
        session_key=session.session_key,
        channel_ref="web",
        idempotency_key=session_service.new_idempotency_key(),
        ctx={"actor": "gateway-smoke"},
    )
    return Order.objects.get(ref=result.order_ref)


def _create_pix_intent(order: Order, *, gateway_id: str):
    intent = PaymentService.create_intent(
        order_ref=order.ref,
        amount_q=order.total_q,
        method="pix",
        gateway="efi",
        gateway_id=gateway_id,
        gateway_data={"smoke": True},
    )
    _link_intent(order, intent.ref)
    return intent


def _create_card_intent(order: Order, *, gateway_id: str):
    intent = PaymentService.create_intent(
        order_ref=order.ref,
        amount_q=order.total_q,
        method="card",
        gateway="stripe",
        gateway_id=gateway_id,
        gateway_data={"smoke": True},
    )
    _link_intent(order, intent.ref)
    return intent


def _link_intent(order: Order, intent_ref: str) -> None:
    data = dict(order.data or {})
    payment = dict(data.get("payment") or {})
    payment["intent_ref"] = intent_ref
    data["payment"] = payment
    order.data = data
    order.save(update_fields=["data", "updated_at"])


def _post_efi(client: APIClient, payload: dict):
    return client.post(
        "/api/webhooks/efi/pix/",
        payload,
        format="json",
        HTTP_HOST="localhost",
        HTTP_X_EFI_WEBHOOK_TOKEN=_LOCAL_EFI_WEBHOOK["webhook_token"],
    )


def _post_ifood(client: APIClient, payload: dict):
    return client.post(
        "/api/webhooks/ifood/",
        payload,
        format="json",
        HTTP_HOST="localhost",
        HTTP_X_IFOOD_WEBHOOK_TOKEN=_LOCAL_IFOOD["webhook_token"],
    )


def _post_stripe(client: APIClient, event):
    payload = json.dumps({"id": event.id, "type": event.type}).encode()
    with patch("shopman.shop.adapters.payment_stripe.construct_webhook_event", return_value=event):
        return client.post(
            "/api/webhooks/stripe/",
            data=payload,
            content_type="application/json",
            HTTP_HOST="localhost",
            HTTP_STRIPE_SIGNATURE="gateway-smoke-signature",
        )


def _stripe_payment_succeeded_event(*, event_id: str, stripe_pi_id: str, intent_ref: str, order_ref: str):
    return SimpleNamespace(
        id=event_id,
        type="payment_intent.succeeded",
        data=SimpleNamespace(
            object=SimpleNamespace(
                id=stripe_pi_id,
                metadata={"shopman_ref": intent_ref, "order_ref": order_ref},
                last_payment_error=None,
            )
        ),
    )


def _stripe_charge_refunded_event(
    *,
    event_id: str,
    stripe_pi_id: str,
    amount_q: int,
    amount_refunded_q: int,
    charge_id: str,
):
    return SimpleNamespace(
        id=event_id,
        type="charge.refunded",
        data=SimpleNamespace(
            object=SimpleNamespace(
                id=charge_id,
                payment_intent=stripe_pi_id,
                amount=amount_q,
                amount_captured=amount_q,
                amount_refunded=amount_refunded_q,
            )
        ),
    )


def _ifood_payload(order_id: str) -> dict:
    return {
        "order_id": order_id,
        "merchant_id": _LOCAL_IFOOD["merchant_id"],
        "status": "PLACED",
        "total": 1500,
        "created_at": timezone.now().isoformat(),
        "customer": {"name": "Cliente Smoke", "phone": "+5543999999999"},
        "delivery": {"type": "DELIVERY", "address": "Rua Smoke, 123"},
        "items": [
            {"sku": "GATEWAY-SMOKE-SKU", "name": "Smoke", "qty": 1, "unit_price_q": 1500},
        ],
        "notes": "gateway smoke",
    }


def _sandbox_readiness_checks() -> tuple[GatewaySmokeCheck, ...]:
    return (
        _credential_check(
            provider="efi",
            name="sandbox_credentials",
            missing=_missing_efi_credentials(),
            ready_message="Credenciais EFI sandbox presentes para smoke real.",
            blocked_message="Credenciais EFI sandbox ausentes; smoke externo não executado.",
        ),
        _credential_check(
            provider="stripe",
            name="sandbox_credentials",
            missing=_missing_stripe_credentials(),
            ready_message="Credenciais Stripe test presentes para smoke real.",
            blocked_message="Credenciais Stripe test ausentes; smoke externo não executado.",
        ),
        _credential_check(
            provider="ifood",
            name="sandbox_credentials",
            missing=_missing_ifood_credentials(),
            ready_message="Credenciais iFood sandbox/staging presentes para smoke real.",
            blocked_message="Credenciais iFood sandbox/staging ausentes; smoke externo não executado.",
        ),
        _manychat_readiness_check(),
    )


def _credential_check(
    *,
    provider: str,
    name: str,
    missing: list[str],
    ready_message: str,
    blocked_message: str,
) -> GatewaySmokeCheck:
    if missing:
        return GatewaySmokeCheck(
            provider=provider,
            name=name,
            scope="sandbox_readiness",
            status="blocked_by_credentials",
            message=blocked_message,
            details={"missing": missing},
        )
    return GatewaySmokeCheck(
        provider=provider,
        name=name,
        scope="sandbox_readiness",
        status="ready",
        message=ready_message,
    )


def _manychat_readiness_check() -> GatewaySmokeCheck:
    missing = _missing_manychat_credentials()
    if missing:
        return GatewaySmokeCheck(
            provider="manychat",
            name="sandbox_credentials",
            scope="sandbox_readiness",
            status="blocked_by_credentials",
            message="Credenciais ManyChat/access-link ausentes; smoke externo não executado.",
            details={"missing": missing},
        )
    return GatewaySmokeCheck(
        provider="manychat",
        name="ordering_webhook",
        scope="sandbox_readiness",
        status="blocked_by_implementation",
        message=(
            "Credenciais existem, mas o webhook conversacional ManyChat -> pedido "
            "permanece pendente de reimplementação; não marcar como smoke real provado."
        ),
    )


def _missing_efi_credentials() -> list[str]:
    cfg = getattr(settings, "SHOPMAN_EFI", {}) or {}
    webhook = getattr(settings, "SHOPMAN_EFI_WEBHOOK", {}) or {}
    missing = [
        name
        for name in ("client_id", "client_secret", "certificate_path", "pix_key")
        if not str(cfg.get(name) or "").strip()
    ]
    certificate_path = str(cfg.get("certificate_path") or "").strip()
    if certificate_path and not Path(certificate_path).exists():
        missing.append("certificate_path_exists")
    if not str(webhook.get("webhook_token") or "").strip():
        missing.append("webhook_token")
    return missing


def _missing_stripe_credentials() -> list[str]:
    cfg = getattr(settings, "SHOPMAN_STRIPE", {}) or {}
    missing = [
        name
        for name in ("secret_key", "webhook_secret")
        if not str(cfg.get(name) or "").strip()
    ]
    secret_key = str(cfg.get("secret_key") or "")
    if secret_key and not secret_key.startswith("sk_test_"):
        missing.append("secret_key_must_be_test_key")
    return missing


def _missing_ifood_credentials() -> list[str]:
    cfg = getattr(settings, "SHOPMAN_IFOOD", {}) or {}
    return [
        name
        for name in ("webhook_token", "merchant_id")
        if not str(cfg.get(name) or "").strip()
    ]


def _missing_manychat_credentials() -> list[str]:
    missing = []
    if not str(getattr(settings, "MANYCHAT_API_TOKEN", "") or "").strip():
        missing.append("MANYCHAT_API_TOKEN")
    if not str(getattr(settings, "MANYCHAT_WEBHOOK_SECRET", "") or "").strip():
        missing.append("MANYCHAT_WEBHOOK_SECRET")
    doorman = getattr(settings, "DOORMAN", {}) or {}
    if not str(doorman.get("ACCESS_LINK_API_KEY") or "").strip():
        missing.append("DOORMAN.ACCESS_LINK_API_KEY")
    return missing


def _expect(condition: bool, message: str, **details) -> None:
    if not condition:
        raise GatewaySmokeError(message, details=details)


def _response(response) -> dict:
    return {
        "status_code": int(response.status_code),
        "data": _clean_details(getattr(response, "data", {})),
    }


def _clean_details(value):
    try:
        json.dumps(value)
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _clean_details(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_clean_details(item) for item in value]
        return str(value)
    return value


def _money(amount_q: int) -> str:
    return f"{amount_q / 100:.2f}"
