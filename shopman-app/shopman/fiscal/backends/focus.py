"""
Focus NFC-e Backend — Emissão de NFC-e via Focus API.
"""

from __future__ import annotations

import json
import logging
from base64 import b64encode
from urllib.request import Request, urlopen

from shopman.ordering.protocols import (
    FiscalCancellationResult,
    FiscalDocumentResult,
)

logger = logging.getLogger(__name__)


class FocusNFCeBackend:
    """
    FiscalBackend para NFC-e via Focus NFC-e API.

    Configuração:
        SHOPMAN_FISCAL = {
            "backend": "focus_nfce",
            "api_token": "xxx",
            "environment": "production",  # ou "homologation"
            "cnpj": "00000000000100",
            "state_code": "41",  # PR
            "default_cfop": "5102",
            "default_ncm": "19059090",  # Produtos de padaria
        }
    """

    PRODUCTION_URL = "https://api.focusnfe.com.br"
    HOMOLOGATION_URL = "https://homologacao.focusnfe.com.br"

    def __init__(
        self,
        api_token: str,
        environment: str = "production",
        cnpj: str = "",
        state_code: str = "41",
        default_cfop: str = "5102",
        default_ncm: str = "19059090",
    ):
        self.api_token = api_token
        self.base_url = (
            self.PRODUCTION_URL if environment == "production"
            else self.HOMOLOGATION_URL
        )
        self.cnpj = cnpj
        self.state_code = state_code
        self.default_cfop = default_cfop
        self.default_ncm = default_ncm

    def emit(
        self,
        *,
        reference: str,
        items: list[dict],
        customer: dict | None = None,
        payment: dict,
        additional_info: str | None = None,
    ) -> FiscalDocumentResult:
        """Emite NFC-e via Focus API."""
        payload = self._build_nfce_payload(
            items=items,
            customer=customer,
            payment=payment,
            additional_info=additional_info,
        )

        try:
            response = self._api_call(
                "POST", f"/v2/nfce?ref={reference}", payload
            )

            if response.get("status") in ("processando_autorizacao", "autorizado"):
                return self.query_status(reference=reference)

            return FiscalDocumentResult(
                success=False,
                status="denied",
                error_code=response.get("codigo"),
                error_message=response.get("mensagem"),
            )

        except Exception as e:
            logger.exception("Focus NFC-e emit error: %s", reference)
            return FiscalDocumentResult(
                success=False,
                status="error",
                error_message=str(e),
            )

    def query_status(self, *, reference: str) -> FiscalDocumentResult:
        """Consulta status da NFC-e."""
        try:
            response = self._api_call("GET", f"/v2/nfce/{reference}")
            status = response.get("status", "")

            if status == "autorizado":
                return FiscalDocumentResult(
                    success=True,
                    document_id=reference,
                    document_number=response.get("numero"),
                    document_series=response.get("serie"),
                    access_key=response.get("chave_nfe"),
                    authorization_date=response.get("data_emissao"),
                    protocol_number=response.get("protocolo"),
                    xml_url=response.get("caminho_xml_nota_fiscal"),
                    danfe_url=response.get("caminho_danfe"),
                    qrcode_url=response.get("url_qrcode"),
                    status="authorized",
                )

            if status == "cancelado":
                return FiscalDocumentResult(
                    success=False,
                    document_id=reference,
                    status="cancelled",
                )

            if status in ("erro_autorizacao", "rejeitado"):
                return FiscalDocumentResult(
                    success=False,
                    document_id=reference,
                    status="denied",
                    error_message=response.get("mensagem_sefaz"),
                )

            return FiscalDocumentResult(
                success=False,
                document_id=reference,
                status="pending",
            )

        except Exception as e:
            logger.exception("Focus NFC-e query error: %s", reference)
            return FiscalDocumentResult(
                success=False,
                error_message=str(e),
            )

    def cancel(
        self,
        *,
        reference: str,
        reason: str,
    ) -> FiscalCancellationResult:
        """Cancela NFC-e (dentro de 30min da autorização)."""
        if len(reason) < 15:
            return FiscalCancellationResult(
                success=False,
                error_message="Justificativa deve ter no mínimo 15 caracteres.",
            )

        try:
            response = self._api_call(
                "DELETE",
                f"/v2/nfce/{reference}",
                {"justificativa": reason},
            )

            if response.get("status") == "cancelado":
                return FiscalCancellationResult(
                    success=True,
                    protocol_number=response.get("protocolo"),
                    cancellation_date=response.get("data_evento"),
                )

            return FiscalCancellationResult(
                success=False,
                error_code=response.get("codigo"),
                error_message=response.get("mensagem"),
            )

        except Exception as e:
            logger.exception("Focus NFC-e cancel error: %s", reference)
            return FiscalCancellationResult(
                success=False,
                error_message=str(e),
            )

    def _build_nfce_payload(
        self,
        items: list[dict],
        customer: dict | None,
        payment: dict,
        additional_info: str | None,
    ) -> dict:
        """Monta payload NFC-e no formato Focus."""
        payload: dict = {
            "natureza_operacao": "Venda ao consumidor final",
            "tipo_documento": 1,
            "finalidade_emissao": 1,
            "consumidor_final": 1,
            "presenca_comprador": 1,
            "items": [],
            "formas_pagamento": [{
                "forma_pagamento": payment.get("method", "01"),
                "valor_pagamento": payment["amount_q"] / 100,
            }],
        }

        if customer and customer.get("cpf"):
            payload["cpf"] = customer["cpf"].replace(".", "").replace("-", "")
            if customer.get("name"):
                payload["nome"] = customer["name"]

        for i, item in enumerate(items, 1):
            unit = item.get("unit", "UN")
            qty = float(item["quantity"])
            unit_price = item["unit_price_q"] / 100

            payload["items"].append({
                "numero_item": i,
                "codigo_produto": item.get("sku", f"ITEM-{i}"),
                "descricao": item["description"],
                "codigo_ncm": item.get("ncm", self.default_ncm),
                "cfop": item.get("cfop", self.default_cfop),
                "unidade_comercial": unit,
                "quantidade_comercial": qty,
                "valor_unitario_comercial": unit_price,
                "valor_bruto": item["total_q"] / 100,
                "unidade_tributavel": unit,
                "quantidade_tributavel": qty,
                "valor_unitario_tributavel": unit_price,
                "icms_origem": 0,
                "icms_situacao_tributaria": item.get("icms_cst", "102"),
                "pis_situacao_tributaria": item.get("pis_cst", "49"),
                "cofins_situacao_tributaria": item.get("cofins_cst", "49"),
            })

        if additional_info:
            payload["informacoes_adicionais_contribuinte"] = additional_info

        return payload

    def _api_call(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
    ) -> dict:
        """Chamada HTTP autenticada para Focus API."""
        url = f"{self.base_url}{path}"
        credentials = b64encode(
            f"{self.api_token}:".encode()
        ).decode("ascii")

        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }

        data = json.dumps(payload).encode("utf-8") if payload else None

        request = Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )

        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
