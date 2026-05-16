"""
EFI PIX payment adapter — Pix payments via Efi (Gerencianet).

Persists via PaymentService (DB) + communicates with Efi API.
Docs: https://dev.efipay.com.br/docs/api-pix
"""

from __future__ import annotations

import json
import logging
import ssl
import uuid
from base64 import b64encode
from datetime import timedelta
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from shopman.shop.adapters.payment_types import PaymentIntent, PaymentResult

logger = logging.getLogger(__name__)

SANDBOX_URL = "https://pix-h.api.efipay.com.br"
PRODUCTION_URL = "https://pix.api.efipay.com.br"

_EFI_TOKEN_CACHE_KEY = "efi_access_token"
_EFI_TOKEN_TTL = 3300  # 55 min — EFI tokens last 1h


def _get_config() -> dict:
    """Read EFI configuration from settings."""
    return getattr(settings, "SHOPMAN_EFI", {})


def _get_base_url() -> str:
    config = _get_config()
    return SANDBOX_URL if config.get("sandbox", True) else PRODUCTION_URL


def _get_access_token() -> str:
    """Obtain or renew access token. Token is cached — thread-safe across workers."""
    token = cache.get(_EFI_TOKEN_CACHE_KEY)
    if token:
        return token

    config = _get_config()
    client_id = config["client_id"]
    client_secret = config["client_secret"]
    certificate_path = config["certificate_path"]

    auth = b64encode(f"{client_id}:{client_secret}".encode()).decode()
    context = ssl.create_default_context()
    context.load_cert_chain(certificate_path)
    data = urlencode({"grant_type": "client_credentials"}).encode()

    request = Request(
        f"{_get_base_url()}/oauth/token",
        data=data,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    with urlopen(request, context=context, timeout=30) as response:
        result = json.loads(response.read().decode())
        token = result["access_token"]
        cache.set(_EFI_TOKEN_CACHE_KEY, token, timeout=_EFI_TOKEN_TTL)
        return token


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    """Make authenticated request to Efi API."""
    config = _get_config()
    token = _get_access_token()

    context = ssl.create_default_context()
    context.load_cert_chain(config["certificate_path"])

    data = json.dumps(payload).encode() if payload else None

    request = Request(
        f"{_get_base_url()}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method=method,
    )

    try:
        with urlopen(request, context=context, timeout=30) as response:
            return json.loads(response.read().decode())
    except HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        logger.error("Efi API error: %s - %s", e.code, error_body)
        raise


def create_intent(
    *,
    order_ref: str,
    amount_q: int,
    currency: str = "BRL",
    method: str = "pix",
    metadata: dict | None = None,
    **config,
) -> PaymentIntent:
    """Create a PIX charge via Efi gateway + persist via PaymentService."""
    from shopman.payman import PaymentService

    if method != "pix":
        raise ValueError("EFI adapter only supports PIX")

    metadata = metadata or {}
    idempotency_key = config.get("idempotency_key") or metadata.get("idempotency_key", "")
    efi_config = _get_config()
    pix_timeout_minutes = config.get("pix_timeout_minutes")
    if pix_timeout_minutes:
        pix_expiry_seconds = int(pix_timeout_minutes) * 60
    else:
        pix_expiry_seconds = getattr(settings, "SHOPMAN_PIX_EXPIRY_SECONDS", 3600)
    expires_at = timezone.now() + timedelta(seconds=pix_expiry_seconds)

    db_intent = PaymentService.create_intent(
        order_ref=order_ref,
        amount_q=amount_q,
        method="pix",
        gateway="efi",
        gateway_data=metadata,
        expires_at=expires_at,
        idempotency_key=idempotency_key,
    )
    if db_intent.gateway_id and db_intent.gateway_data.get("client_secret"):
        return _intent_from_db(db_intent, currency=currency)

    txid = uuid.uuid5(uuid.NAMESPACE_URL, f"shopman-efi:{idempotency_key}").hex if idempotency_key else uuid.uuid4().hex[:35]
    valor = f"{amount_q / 100:.2f}"

    payload = {
        "calendario": {"expiracao": pix_expiry_seconds},
        "valor": {"original": valor},
        "chave": efi_config.get("pix_key"),
        "infoAdicionais": [
            {"nome": "Referência", "valor": order_ref},
        ],
    }

    try:
        response = _request("PUT", f"/v2/cob/{txid}", payload)
        qr_response = _request("GET", f"/v2/loc/{response['loc']['id']}/qrcode")

        client_secret = json.dumps({
            "qrcode": qr_response.get("qrcode", ""),
            "imagemQrcode": qr_response.get("imagemQrcode", ""),
            "txid": txid,
        })

        db_intent.gateway_id = txid
        db_intent.gateway_data = {
            **metadata,
            "location": response.get("location", ""),
            "client_secret": client_secret,
        }
        db_intent.save(update_fields=["gateway_id", "gateway_data"])

        return PaymentIntent(
            intent_ref=db_intent.ref,
            status="pending",
            amount_q=amount_q,
            currency=currency,
            client_secret=client_secret,
            expires_at=expires_at,
            gateway_id=txid,
            metadata={
                "qrcode": qr_response.get("qrcode", ""),
                "imagemQrcode": qr_response.get("imagemQrcode", ""),
                "txid": txid,
            },
        )
    except Exception:
        try:
            PaymentService.fail(
                db_intent.ref,
                error_code="gateway_error",
                message="Falha na criação da cobrança Efi",
            )
        except Exception:
            logger.warning("Efi create_intent: could not mark intent as failed for order %s", order_ref, exc_info=True)
        logger.exception("Efi create_intent error for order %s", order_ref)
        raise


def _intent_from_db(intent, *, currency: str = "BRL") -> PaymentIntent:
    client_secret = (intent.gateway_data or {}).get("client_secret")
    metadata = dict(intent.gateway_data or {})
    if client_secret:
        try:
            parsed = json.loads(client_secret)
        except (TypeError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            metadata.update(parsed)
    return PaymentIntent(
        intent_ref=intent.ref,
        status=intent.status,
        amount_q=intent.amount_q,
        currency=currency or intent.currency,
        client_secret=client_secret,
        expires_at=intent.expires_at,
        gateway_id=intent.gateway_id,
        metadata=metadata,
    )


def capture(
    intent_ref: str,
    *,
    amount_q: int | None = None,
    **config,
) -> PaymentResult:
    """Check PIX payment status and capture if paid.

    PIX is auto-captured when paid — this verifies status at the gateway.
    The `amount_q` argument is accepted for contract uniformity but ignored:
    PIX captures the full charge amount as defined at create_intent time.
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        txid = intent.gateway_id
    except PaymentError:
        return PaymentResult(
            success=False,
            error_code="intent_not_found",
            message=f"Intent {intent_ref} não encontrado",
        )

    try:
        response = _request("GET", f"/v2/cob/{txid}")
        status = response.get("status", "")

        if status == "CONCLUIDA":
            amount_q = int(float(response["valor"]["original"]) * 100)
            PaymentService.reconcile_gateway_status(
                intent_ref,
                gateway_status="captured",
                amount_q=amount_q,
                captured_q=amount_q,
                refunded_q=0,
                gateway_id=txid,
                capture_gateway_id=txid,
                gateway_data={"efi_status": status},
            )
            try:
                PaymentService.authorize(intent_ref, gateway_id=txid)
            except PaymentError:
                pass
            return PaymentResult(
                success=True,
                transaction_id=txid,
                amount_q=amount_q,
            )
        return PaymentResult(
            success=False,
            error_code=status.lower() if status else "pending",
            message=f"Status: {status}",
        )
    except Exception as e:
        logger.warning("capture check failed for intent %s: %s", intent_ref, e, exc_info=True)
        return PaymentResult(
            success=False,
            error_code="error",
            message=str(e),
        )


def refund(
    intent_ref: str,
    *,
    amount_q: int | None = None,
    reason: str = "",
    **config,
) -> PaymentResult:
    """Process PIX refund via Efi gateway + PaymentService."""
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        txid = intent.gateway_id
    except PaymentError:
        return PaymentResult(
            success=False,
            error_code="intent_not_found",
            message=f"Intent {intent_ref} não encontrado",
        )

    try:
        cob = _request("GET", f"/v2/cob/{txid}")

        if cob.get("status") != "CONCLUIDA":
            return PaymentResult(
                success=False,
                error_code="not_paid",
                message="Cobrança não foi paga",
            )

        pix_list = cob.get("pix", [])
        if not pix_list:
            return PaymentResult(
                success=False,
                error_code="no_payment",
                message="Pagamento não encontrado",
            )

        e2eid = pix_list[0].get("endToEndId", "")
        valor = f"{amount_q / 100:.2f}" if amount_q else cob["valor"]["original"]
        dev_id = uuid.uuid4().hex[:35]

        response = _request("PUT", f"/v2/pix/{e2eid}/devolucao/{dev_id}", {"valor": valor})

        refund_amount = int(float(valor) * 100)
        try:
            PaymentService.refund(
                intent_ref,
                amount_q=refund_amount,
                reason=reason,
                gateway_id=response.get("id", dev_id),
            )
        except PaymentError:
            pass

        return PaymentResult(
            success=True,
            transaction_id=response.get("id", dev_id),
            amount_q=refund_amount,
        )
    except Exception as e:
        logger.exception("Efi refund error for intent %s", intent_ref)
        return PaymentResult(
            success=False,
            error_code="error",
            message=str(e),
        )


def cancel(intent_ref: str, **config) -> PaymentResult:
    """Cancel a PIX charge via Efi gateway + PaymentService."""
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        txid = intent.gateway_id
    except PaymentError:
        return PaymentResult(
            success=False,
            error_code="intent_not_found",
            message="Intent não encontrado",
        )

    try:
        payload = {"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"}
        _request("PATCH", f"/v2/cob/{txid}", payload)

        try:
            PaymentService.cancel(intent_ref)
        except PaymentError:
            pass

        return PaymentResult(success=True)
    except Exception as e:
        logger.warning("cancel failed for intent %s: %s", intent_ref, e, exc_info=True)
        return PaymentResult(
            success=False,
            error_code="error",
            message=str(e),
        )


def get_status(intent_ref: str, **config) -> dict:
    """
    Get payment status from PaymentService (source of truth).

    Returns:
        {"intent_ref": str, "status": str, "amount_q": int,
         "captured_q": int, "refunded_q": int, "currency": str}
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        captured_q = PaymentService.captured_total(intent_ref)
        refunded_q = PaymentService.refunded_total(intent_ref)

        return {
            "intent_ref": intent_ref,
            "status": intent.status,
            "amount_q": intent.amount_q,
            "captured_q": captured_q,
            "refunded_q": refunded_q,
            "currency": intent.currency,
        }
    except PaymentError:
        return {
            "intent_ref": intent_ref,
            "status": "error",
            "amount_q": 0,
            "captured_q": 0,
            "refunded_q": 0,
            "currency": "BRL",
        }


def check_gateway_status(intent_ref: str) -> str:
    """
    Check status directly at the Efi gateway (bypasses DB).

    Used as safety check before cancelling expired intents.
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        txid = intent.gateway_id
    except PaymentError:
        return "error"

    try:
        cob = _request("GET", f"/v2/cob/{txid}")
        status_map = {
            "ATIVA": "pending",
            "CONCLUIDA": "captured",
            "REMOVIDA_PELO_USUARIO_RECEBEDOR": "cancelled",
            "REMOVIDA_PELO_PSP": "cancelled",
        }
        return status_map.get(cob["status"], cob["status"])
    except Exception as e:
        logger.warning("check_gateway_status failed for %s: %s", intent_ref, e)
        return "error"
