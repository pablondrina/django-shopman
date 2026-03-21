"""
Pix Payment Backend — Integração com Pix via Efi (Gerencianet).

Para usar outro provider (Mercado Pago, PagSeguro, etc),
use este arquivo como template e adapte.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from django.utils import timezone

from shopman.payment.protocols import (
    CaptureResult,
    PaymentIntent,
    PaymentStatus,
    RefundResult,
)

logger = logging.getLogger(__name__)


class EfiPixBackend:
    """
    Backend para Pix via Efi (antigo Gerencianet).

    Args:
        client_id: Client ID da API Efi
        client_secret: Client Secret da API Efi
        certificate_path: Caminho para o certificado .pem
        sandbox: Se True, usa ambiente de homologação

    Example:
        backend = EfiPixBackend(
            client_id="Client_Id_xxx",
            client_secret="Client_Secret_xxx",
            certificate_path="/path/to/certificate.pem",
            sandbox=True,
        )

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

    Documentação Efi:
        https://dev.efipay.com.br/docs/api-pix
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
    ) -> PaymentIntent:
        """
        Cria cobrança Pix imediata.

        O 'intent_id' retornado é o txid da cobrança.
        O 'client_secret' contém o QR Code e dados para pagamento.
        """
        if currency.upper() != "BRL":
            raise ValueError("Pix só suporta BRL")

        # Valor em reais (API Efi usa string com 2 decimais)
        valor = f"{amount_q / 100:.2f}"

        # Gera txid único
        import uuid
        txid = uuid.uuid4().hex[:35]  # Max 35 chars

        payload = {
            "calendario": {
                "expiracao": 3600,  # 1 hora
            },
            "valor": {
                "original": valor,
            },
            "chave": self.pix_key,
            "infoAdicionais": [
                {"nome": "Referência", "valor": reference or ""},
            ],
        }

        try:
            response = self._request("PUT", f"/v2/cob/{txid}", payload)

            # Busca QR Code
            qr_response = self._request("GET", f"/v2/loc/{response['loc']['id']}/qrcode")

            return PaymentIntent(
                intent_id=txid,
                status="pending",
                amount_q=amount_q,
                currency="BRL",
                client_secret=json.dumps({
                    "qrcode": qr_response.get("qrcode", ""),
                    "imagemQrcode": qr_response.get("imagemQrcode", ""),
                    "txid": txid,
                }),
                expires_at=timezone.now() + timedelta(hours=1),
                metadata={"location": response.get("location", "")},
            )

        except Exception as e:
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
        Retorna sucesso se a cobrança existe.
        """
        try:
            response = self._request("GET", f"/v2/cob/{intent_id}")
            status = response.get("status", "")

            if status == "CONCLUIDA":
                return CaptureResult(
                    success=True,
                    transaction_id=intent_id,
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
        """
        Pix é capturado automaticamente quando pago.
        Este método apenas verifica o status.
        """
        return self.authorize(intent_id)

    def refund(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reason: str | None = None,
    ) -> RefundResult:
        """
        Processa devolução Pix.

        Nota: Requer que a cobrança tenha sido paga.
        """
        try:
            # Busca cobrança para pegar o e2eId
            cob = self._request("GET", f"/v2/cob/{intent_id}")

            if cob.get("status") != "CONCLUIDA":
                return RefundResult(
                    success=False,
                    error_code="not_paid",
                    message="Cobrança não foi paga",
                )

            # Pega e2eId do pagamento
            pix_list = cob.get("pix", [])
            if not pix_list:
                return RefundResult(
                    success=False,
                    error_code="no_payment",
                    message="Pagamento não encontrado",
                )

            e2eid = pix_list[0].get("endToEndId", "")

            # Valor da devolução
            if amount_q:
                valor = f"{amount_q / 100:.2f}"
            else:
                valor = cob["valor"]["original"]

            # Gera ID da devolução
            import uuid
            dev_id = uuid.uuid4().hex[:35]

            payload = {
                "valor": valor,
            }

            response = self._request("PUT", f"/v2/pix/{e2eid}/devolucao/{dev_id}", payload)

            return RefundResult(
                success=True,
                refund_id=response.get("id", dev_id),
                amount_q=int(float(valor) * 100),
            )

        except Exception as e:
            logger.exception("Efi refund error")
            return RefundResult(
                success=False,
                error_code="error",
                message=str(e),
            )

    def cancel(self, intent_id: str) -> bool:
        """
        Cancela cobrança Pix.

        Só é possível cancelar cobranças não pagas.
        """
        try:
            payload = {"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"}
            self._request("PATCH", f"/v2/cob/{intent_id}", payload)
            return True
        except Exception:
            logger.warning("cancel failed for intent %s", intent_id, exc_info=True)
            return False

    def get_status(self, intent_id: str) -> PaymentStatus:
        """Consulta status da cobrança."""
        try:
            cob = self._request("GET", f"/v2/cob/{intent_id}")

            status_map = {
                "ATIVA": "pending",
                "CONCLUIDA": "captured",
                "REMOVIDA_PELO_USUARIO_RECEBEDOR": "cancelled",
                "REMOVIDA_PELO_PSP": "cancelled",
            }

            amount = int(float(cob["valor"]["original"]) * 100)
            captured = amount if cob["status"] == "CONCLUIDA" else 0

            # Soma devoluções
            refunded = 0
            for pix in cob.get("pix", []):
                for dev in pix.get("devolucoes", []):
                    if dev.get("status") == "DEVOLVIDO":
                        refunded += int(float(dev["valor"]) * 100)

            return PaymentStatus(
                intent_id=intent_id,
                status=status_map.get(cob["status"], cob["status"]),
                amount_q=amount,
                captured_q=captured,
                refunded_q=refunded,
                currency="BRL",
            )

        except Exception as e:
            logger.warning("get_status failed for intent %s: %s", intent_id, e, exc_info=True)
            return PaymentStatus(
                intent_id=intent_id,
                status="error",
                amount_q=0,
                captured_q=0,
                refunded_q=0,
                currency="BRL",
                metadata={"error": str(e)},
            )

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
            logger.error(f"Efi API error: {e.code} - {error_body}")
            raise
