"""
Pix Payment Backend — Integração com Pix via Efi (Gerencianet).

Persiste via PaymentService (DB) + comunica com API Efi.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.utils import timezone
from shopman.payments.protocols import (
    CaptureResult,
    GatewayIntent,
    PaymentStatus,
    RefundResult,
)

logger = logging.getLogger(__name__)


class EfiPixBackend:
    """
    Backend para Pix via Efi (antigo Gerencianet).

    Configuração via settings:
        SHOPMAN_PAYMENT = {
            "backend": "pix",
            "pix": {
                "client_id": os.environ["EFI_CLIENT_ID"],
                "client_secret": os.environ["EFI_CLIENT_SECRET"],
                "certificate_path": BASE_DIR / "certs" / "efi.pem",
                "sandbox": DEBUG,
            },
        }

    Documentação Efi: https://dev.efipay.com.br/docs/api-pix
    """

    SANDBOX_URL = "https://pix-h.api.efipay.com.br"
    PRODUCTION_URL = "https://pix.api.efipay.com.br"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        certificate_path: str,
        sandbox: bool = True,
        pix_key: str | None = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.certificate_path = certificate_path
        self.sandbox = sandbox
        self.pix_key = pix_key
        self.base_url = self.SANDBOX_URL if sandbox else self.PRODUCTION_URL
        self._access_token: str | None = None
        self._token_expires: datetime | None = None

    def create_intent(
        self,
        amount_q: int,
        currency: str,
        *,
        reference: str | None = None,
        metadata: dict | None = None,
    ) -> GatewayIntent:
        """Cria cobrança Pix imediata com persistência via PaymentService."""
        from shopman.payments import PaymentService

        if currency.upper() != "BRL":
            raise ValueError("Pix só suporta BRL")

        # 1. Persist via PaymentService
        db_intent = PaymentService.create_intent(
            order_ref=reference or "",
            amount_q=amount_q,
            method="pix",
            gateway="efi",
            gateway_data=metadata or {},
            expires_at=timezone.now() + timedelta(hours=1),
        )

        # 2. Call Efi API
        import uuid
        txid = uuid.uuid4().hex[:35]
        valor = f"{amount_q / 100:.2f}"

        payload = {
            "calendario": {"expiracao": 3600},
            "valor": {"original": valor},
            "chave": self.pix_key,
            "infoAdicionais": [
                {"nome": "Referência", "valor": reference or ""},
            ],
        }

        try:
            response = self._request("PUT", f"/v2/cob/{txid}", payload)
            qr_response = self._request("GET", f"/v2/loc/{response['loc']['id']}/qrcode")

            client_secret = json.dumps({
                "qrcode": qr_response.get("qrcode", ""),
                "imagemQrcode": qr_response.get("imagemQrcode", ""),
                "txid": txid,
            })

            # 3. Store gateway_id and data
            db_intent.gateway_id = txid
            db_intent.gateway_data = {
                **(metadata or {}),
                "location": response.get("location", ""),
                "client_secret": client_secret,
            }
            db_intent.save(update_fields=["gateway_id", "gateway_data"])

            return GatewayIntent(
                intent_id=db_intent.ref,
                status="pending",
                amount_q=amount_q,
                currency="BRL",
                client_secret=client_secret,
                expires_at=timezone.now() + timedelta(hours=1),
                metadata={"location": response.get("location", "")},
            )

        except Exception:
            # Mark as failed if gateway call fails
            try:
                PaymentService.fail(
                    db_intent.ref,
                    error_code="gateway_error",
                    message="Falha na criação da cobrança Efi",
                )
            except Exception:
                pass
            logger.exception("Efi create_intent error")
            raise

    def authorize(
        self,
        intent_id: str,
        *,
        payment_method: str | None = None,
    ) -> CaptureResult:
        """
        Pix não tem fase de autorização separada.
        Verifica status no gateway via txid armazenado.
        """
        from shopman.payments import PaymentError, PaymentService

        try:
            intent = PaymentService.get(intent_id)
            txid = intent.gateway_id
        except PaymentError:
            return CaptureResult(
                success=False,
                error_code="intent_not_found",
                message=f"Intent {intent_id} não encontrado",
            )

        try:
            response = self._request("GET", f"/v2/cob/{txid}")
            status = response.get("status", "")

            if status == "CONCLUIDA":
                # Authorize + capture via PaymentService
                try:
                    PaymentService.authorize(intent_id, gateway_id=txid)
                except PaymentError:
                    pass  # May already be authorized
                return CaptureResult(
                    success=True,
                    transaction_id=txid,
                    amount_q=int(float(response["valor"]["original"]) * 100),
                )
            elif status == "ATIVA":
                return CaptureResult(
                    success=False,
                    error_code="pending",
                    message="Aguardando pagamento",
                )
            else:
                return CaptureResult(
                    success=False,
                    error_code=status,
                    message=f"Status: {status}",
                )

        except Exception as e:
            logger.warning("authorize check failed for intent %s: %s", intent_id, e, exc_info=True)
            return CaptureResult(
                success=False,
                error_code="error",
                message=str(e),
            )

    def capture(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reference: str | None = None,
    ) -> CaptureResult:
        """Pix é capturado automaticamente quando pago. Verifica status."""
        return self.authorize(intent_id)

    def refund(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reason: str | None = None,
    ) -> RefundResult:
        """Processa devolução Pix via gateway + PaymentService."""
        from shopman.payments import PaymentError, PaymentService

        try:
            intent = PaymentService.get(intent_id)
            txid = intent.gateway_id
        except PaymentError:
            return RefundResult(
                success=False,
                error_code="intent_not_found",
                message=f"Intent {intent_id} não encontrado",
            )

        try:
            cob = self._request("GET", f"/v2/cob/{txid}")

            if cob.get("status") != "CONCLUIDA":
                return RefundResult(
                    success=False,
                    error_code="not_paid",
                    message="Cobrança não foi paga",
                )

            pix_list = cob.get("pix", [])
            if not pix_list:
                return RefundResult(
                    success=False,
                    error_code="no_payment",
                    message="Pagamento não encontrado",
                )

            e2eid = pix_list[0].get("endToEndId", "")

            if amount_q:
                valor = f"{amount_q / 100:.2f}"
            else:
                valor = cob["valor"]["original"]

            import uuid
            dev_id = uuid.uuid4().hex[:35]

            response = self._request("PUT", f"/v2/pix/{e2eid}/devolucao/{dev_id}", {"valor": valor})

            # Persist refund via PaymentService
            refund_amount = int(float(valor) * 100)
            try:
                PaymentService.refund(
                    intent_id,
                    amount_q=refund_amount,
                    reason=reason or "",
                    gateway_id=response.get("id", dev_id),
                )
            except PaymentError:
                pass  # Log but don't fail the gateway-confirmed refund

            return RefundResult(
                success=True,
                refund_id=response.get("id", dev_id),
                amount_q=refund_amount,
            )

        except Exception as e:
            logger.exception("Efi refund error")
            return RefundResult(
                success=False,
                error_code="error",
                message=str(e),
            )

    def cancel(self, intent_id: str) -> bool:
        """Cancela cobrança Pix via gateway + PaymentService."""
        from shopman.payments import PaymentError, PaymentService

        try:
            intent = PaymentService.get(intent_id)
            txid = intent.gateway_id
        except PaymentError:
            return False

        try:
            payload = {"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"}
            self._request("PATCH", f"/v2/cob/{txid}", payload)

            # Persist cancellation via PaymentService
            try:
                PaymentService.cancel(intent_id)
            except PaymentError:
                pass

            return True
        except Exception:
            logger.warning("cancel failed for intent %s", intent_id, exc_info=True)
            return False

    def get_status(self, intent_id: str) -> PaymentStatus:
        """Consulta status via PaymentService (fonte de verdade local)."""
        from shopman.payments import PaymentError, PaymentService

        try:
            intent = PaymentService.get(intent_id)
            captured_q = PaymentService.captured_total(intent_id)
            refunded_q = PaymentService.refunded_total(intent_id)

            return PaymentStatus(
                intent_id=intent_id,
                status=intent.status,
                amount_q=intent.amount_q,
                captured_q=captured_q,
                refunded_q=refunded_q,
                currency=intent.currency,
            )
        except PaymentError:
            return PaymentStatus(
                intent_id=intent_id,
                status="error",
                amount_q=0,
                captured_q=0,
                refunded_q=0,
                currency="BRL",
            )

    def check_gateway_status(self, intent_id: str) -> str:
        """
        Consulta status diretamente no gateway Efi (bypass do DB).

        Usado pelo PixTimeoutHandler como safety check antes de cancelar.
        """
        from shopman.payments import PaymentError, PaymentService

        try:
            intent = PaymentService.get(intent_id)
            txid = intent.gateway_id
        except PaymentError:
            return "error"

        try:
            cob = self._request("GET", f"/v2/cob/{txid}")
            status_map = {
                "ATIVA": "pending",
                "CONCLUIDA": "captured",
                "REMOVIDA_PELO_USUARIO_RECEBEDOR": "cancelled",
                "REMOVIDA_PELO_PSP": "cancelled",
            }
            return status_map.get(cob["status"], cob["status"])
        except Exception as e:
            logger.warning("check_gateway_status failed for %s: %s", intent_id, e)
            return "error"

    # ── HTTP helpers ──

    def _get_access_token(self) -> str:
        """Obtém ou renova access token."""
        if self._access_token and self._token_expires:
            if timezone.now() < self._token_expires:
                return self._access_token

        import ssl
        from base64 import b64encode
        from urllib.parse import urlencode

        auth = b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()

        context = ssl.create_default_context()
        context.load_cert_chain(self.certificate_path)

        data = urlencode({"grant_type": "client_credentials"}).encode()

        request = Request(
            f"{self.base_url}/oauth/token",
            data=data,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        with urlopen(request, context=context, timeout=30) as response:
            result = json.loads(response.read().decode())
            self._access_token = result["access_token"]
            self._token_expires = timezone.now() + timedelta(seconds=result["expires_in"] - 60)
            return self._access_token

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        """Faz request autenticado para API Efi."""
        import ssl

        token = self._get_access_token()

        context = ssl.create_default_context()
        context.load_cert_chain(self.certificate_path)

        data = json.dumps(payload).encode() if payload else None

        request = Request(
            f"{self.base_url}{path}",
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


# Backwards-compatible alias
EfiPaymentBackend = EfiPixBackend
