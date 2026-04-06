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


def create_intent(order_ref: str, amount_q: int, method: str = "pix", **config) -> dict:
    """
    Create a PIX charge via Efi gateway + persist via PaymentService.

    Returns:
        {"intent_ref": str, "status": str, "client_secret": str,
         "expires_at": datetime, "gateway_id": str}
    """
    from shopman.payments import PaymentService

    if method != "pix":
        raise ValueError("EFI adapter only supports PIX")

    efi_config = _get_config()
    pix_expiry_seconds = getattr(settings, "SHOPMAN_PIX_EXPIRY_SECONDS", 3600)
    expires_at = timezone.now() + timedelta(seconds=pix_expiry_seconds)

    db_intent = PaymentService.create_intent(
        order_ref=order_ref,
        amount_q=amount_q,
        method="pix",
        gateway="efi",
        gateway_data=config.get("metadata", {}),
        expires_at=expires_at,
    )

    txid = uuid.uuid4().hex[:35]
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
            "location": response.get("location", ""),
            "client_secret": client_secret,
        }
        db_intent.save(update_fields=["gateway_id", "gateway_data"])

        return {
            "intent_ref": db_intent.ref,
            "status": "pending",
            "client_secret": client_secret,
            "expires_at": expires_at,
            "gateway_id": txid,
        }
    except Exception:
        try:
            PaymentService.fail(
                db_intent.ref,
                error_code="gateway_error",
                message="Falha na criação da cobrança Efi",
            )
        except Exception:
            pass
        logger.exception("Efi create_intent error for order %s", order_ref)
        raise


def capture(intent_ref: str, **config) -> dict:
    """
    Check PIX payment status and capture if paid.

    PIX is auto-captured when paid — this verifies status at the gateway.

    Returns:
        {"success": bool, "transaction_id": str | None, "amount_q": int | None,
         "error_code": str | None, "message": str | None}
    """
    from shopman.payments import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        txid = intent.gateway_id
    except PaymentError:
        return {
            "success": False,
            "transaction_id": None,
            "amount_q": None,
            "error_code": "intent_not_found",
            "message": f"Intent {intent_ref} não encontrado",
        }

    try:
        response = _request("GET", f"/v2/cob/{txid}")
        status = response.get("status", "")

        if status == "CONCLUIDA":
            try:
                PaymentService.authorize(intent_ref, gateway_id=txid)
            except PaymentError:
                pass
            return {
                "success": True,
                "transaction_id": txid,
                "amount_q": int(float(response["valor"]["original"]) * 100),
                "error_code": None,
                "message": None,
            }
        return {
            "success": False,
            "transaction_id": None,
            "amount_q": None,
            "error_code": status.lower() if status else "pending",
            "message": f"Status: {status}",
        }
    except Exception as e:
        logger.warning("capture check failed for intent %s: %s", intent_ref, e, exc_info=True)
        return {
            "success": False,
            "transaction_id": None,
            "amount_q": None,
            "error_code": "error",
            "message": str(e),
        }


def refund(intent_ref: str, amount_q: int | None = None, **config) -> dict:
    """
    Process PIX refund via Efi gateway + PaymentService.

    Returns:
        {"success": bool, "refund_id": str | None, "amount_q": int | None,
         "error_code": str | None, "message": str | None}
    """
    from shopman.payments import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        txid = intent.gateway_id
    except PaymentError:
        return {
            "success": False,
            "refund_id": None,
            "amount_q": None,
            "error_code": "intent_not_found",
            "message": f"Intent {intent_ref} não encontrado",
        }

    try:
        cob = _request("GET", f"/v2/cob/{txid}")

        if cob.get("status") != "CONCLUIDA":
            return {
                "success": False,
                "refund_id": None,
                "amount_q": None,
                "error_code": "not_paid",
                "message": "Cobrança não foi paga",
            }

        pix_list = cob.get("pix", [])
        if not pix_list:
            return {
                "success": False,
                "refund_id": None,
                "amount_q": None,
                "error_code": "no_payment",
                "message": "Pagamento não encontrado",
            }

        e2eid = pix_list[0].get("endToEndId", "")
        valor = f"{amount_q / 100:.2f}" if amount_q else cob["valor"]["original"]
        dev_id = uuid.uuid4().hex[:35]

        response = _request("PUT", f"/v2/pix/{e2eid}/devolucao/{dev_id}", {"valor": valor})

        refund_amount = int(float(valor) * 100)
        try:
            PaymentService.refund(
                intent_ref,
                amount_q=refund_amount,
                reason=config.get("reason", ""),
                gateway_id=response.get("id", dev_id),
            )
        except PaymentError:
            pass

        return {
            "success": True,
            "refund_id": response.get("id", dev_id),
            "amount_q": refund_amount,
            "error_code": None,
            "message": None,
        }
    except Exception as e:
        logger.exception("Efi refund error for intent %s", intent_ref)
        return {
            "success": False,
            "refund_id": None,
            "amount_q": None,
            "error_code": "error",
            "message": str(e),
        }


def cancel(intent_ref: str, **config) -> dict:
    """
    Cancel a PIX charge via Efi gateway + PaymentService.

    Returns:
        {"success": bool, "error_code": str | None, "message": str | None}
    """
    from shopman.payments import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        txid = intent.gateway_id
    except PaymentError:
        return {"success": False, "error_code": "intent_not_found", "message": "Intent não encontrado"}

    try:
        payload = {"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"}
        _request("PATCH", f"/v2/cob/{txid}", payload)

        try:
            PaymentService.cancel(intent_ref)
        except PaymentError:
            pass

        return {"success": True, "error_code": None, "message": None}
    except Exception as e:
        logger.warning("cancel failed for intent %s: %s", intent_ref, e, exc_info=True)
        return {"success": False, "error_code": "error", "message": str(e)}


def get_status(intent_ref: str, **config) -> dict:
    """
    Get payment status from PaymentService (source of truth).

    Returns:
        {"intent_ref": str, "status": str, "amount_q": int,
         "captured_q": int, "refunded_q": int, "currency": str}
    """
    from shopman.payments import PaymentError, PaymentService

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
    from shopman.payments import PaymentError, PaymentService

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
