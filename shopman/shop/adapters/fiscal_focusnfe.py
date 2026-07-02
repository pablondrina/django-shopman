"""Focus NFe fiscal adapter.

Provider naming is Focus NFe. The fiscal document emitted here is NFC-e.
Official endpoints used by this adapter:
- homologacao: https://homologacao.focusnfe.com.br/v2/nfce?ref=...
- producao: https://api.focusnfe.com.br/v2/nfce?ref=...
"""

from __future__ import annotations

import json
import logging
from base64 import b64encode
from decimal import ROUND_HALF_UP, Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone
from shopman.fiscalman.contracts import FiscalCancellationResult, FiscalDocumentResult

logger = logging.getLogger(__name__)

HOMOLOGATION_URL = "https://homologacao.focusnfe.com.br"
PRODUCTION_URL = "https://api.focusnfe.com.br"

PAYMENT_METHOD_CODES = {
    "cash": "01",
    "money": "01",
    "dinheiro": "01",
    "card": "03",
    "credit_card": "03",
    "credit": "03",
    "debit_card": "04",
    "debit": "04",
    "store_credit": "05",
    "boleto": "15",
    "pix": "17",
    "external": "99",
}


class FocusNFePayloadError(ValueError):
    """Raised when an order cannot be converted to a Focus NFe NFC-e payload."""


class FocusNFeBackend:
    """FiscalBackend implementation for Focus NFe NFC-e emission."""

    def emit(
        self,
        *,
        reference: str,
        items: list[dict],
        customer: dict | None = None,
        payment: dict,
        additional_info: str | None = None,
    ) -> FiscalDocumentResult:
        config = _get_config()
        missing = _missing_config(config)
        if missing:
            return FiscalDocumentResult(
                success=False,
                status="denied",
                error_code="focus_nfe_config_missing",
                error_message=f"Focus NFe sem configuração obrigatória: {', '.join(missing)}",
            )

        try:
            payload = _build_nfce_payload(
                config=config,
                reference=reference,
                items=items,
                customer=customer or {},
                payment=payment,
                additional_info=additional_info,
            )
            response = _request("POST", _nfce_path(reference, config), payload, config)
        except FocusNFePayloadError as exc:
            return FiscalDocumentResult(
                success=False,
                status="denied",
                error_code="focus_nfe_invalid_payload",
                error_message=str(exc),
            )
        except (HTTPError, URLError, TimeoutError) as exc:
            return _document_error_result(exc)
        except Exception as exc:
            logger.exception("focus_nfe_emit_unexpected reference=%s", reference)
            return FiscalDocumentResult(
                success=False,
                status="denied",
                error_code="focus_nfe_unexpected_error",
                error_message=str(exc),
            )

        return _document_result(response, config)

    def query_status(self, *, reference: str) -> FiscalDocumentResult:
        config = _get_config()
        missing = _missing_config(config)
        if missing:
            return FiscalDocumentResult(
                success=False,
                status="denied",
                error_code="focus_nfe_config_missing",
                error_message=f"Focus NFe sem configuração obrigatória: {', '.join(missing)}",
            )
        try:
            response = _request("GET", _nfce_path(reference, config, consult=True), None, config)
        except (HTTPError, URLError, TimeoutError) as exc:
            return _document_error_result(exc)
        return _document_result(response, config)

    def cancel(self, *, reference: str, reason: str) -> FiscalCancellationResult:
        config = _get_config()
        missing = _missing_config(config)
        if missing:
            return FiscalCancellationResult(
                success=False,
                error_code="focus_nfe_config_missing",
                error_message=f"Focus NFe sem configuração obrigatória: {', '.join(missing)}",
            )

        reason = str(reason or "").strip()
        if len(reason) < 15:
            reason = f"Cancelamento solicitado pelo operador: {reason or reference}"

        try:
            response = _request(
                "DELETE",
                f"/v2/nfce/{quote(reference, safe='')}",
                {"justificativa": reason},
                config,
            )
        except (HTTPError, URLError, TimeoutError) as exc:
            return _cancellation_error_result(exc)

        status = _norm(response.get("status"))
        protocol = _first(response, "protocolo_cancelamento", "protocolo", "numero_protocolo")
        success = status in {"cancelado", "cancelled"} or bool(protocol)
        return FiscalCancellationResult(
            success=success,
            protocol_number=str(protocol) if protocol else None,
            cancellation_date=_first(response, "data_cancelamento", "cancelled_at"),
            error_code=None if success else str(_first(response, "codigo", "codigo_erro", default="focus_nfe_cancel_failed")),
            error_message=None if success else _response_error_message(response),
        )


def _get_config() -> dict:
    return dict(getattr(settings, "SHOPMAN_FOCUS_NFE", {}) or {})


def _missing_config(config: dict) -> list[str]:
    missing = []
    if not str(config.get("token") or "").strip():
        missing.append("FOCUS_NFE_TOKEN")
    if not _focus_cnpj_emitente(config):
        missing.append("FOCUS_NFE_CNPJ_EMITENTE_or_Shop.document")
    return missing


def _base_url(config: dict) -> str:
    configured = str(config.get("base_url") or "").strip().rstrip("/")
    if configured:
        return configured
    env = str(config.get("environment") or "homologacao").strip().lower()
    if env in {"producao", "produção", "production", "prod"}:
        return PRODUCTION_URL
    return HOMOLOGATION_URL


def _nfce_path(reference: str, config: dict, *, consult: bool = False) -> str:
    params = {"completa": _nfce_completa(config)}
    if consult:
        return f"/v2/nfce/{quote(reference, safe='')}?{urlencode(params)}"
    params = {"ref": reference, **params}
    return f"/v2/nfce?{urlencode(params)}"


def _nfce_completa(config: dict) -> str:
    value = config.get("completa_nfce", "1")
    return "0" if str(value).strip().lower() in {"0", "false", "no", "nao", "não"} else "1"


def _request(method: str, path: str, payload: dict | None, config: dict) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    token = str(config["token"]).strip()
    auth = b64encode(f"{token}:".encode()).decode("ascii")
    request = Request(
        f"{_base_url(config)}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "django-shopman/focus-nfe",
        },
    )
    with urlopen(request, timeout=int(config.get("timeout") or 30)) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}


def _build_nfce_payload(
    *,
    config: dict,
    reference: str,
    items: list[dict],
    customer: dict,
    payment: dict,
    additional_info: str | None,
) -> dict:
    # Taxa de entrega não é produto: sai dos itens e entra como frete da nota.
    fee_items = [item for item in items if _is_delivery_fee_item(item)]
    merchandise = [item for item in items if not _is_delivery_fee_item(item)]
    freight_q = sum(int(item.get("total_q") or 0) for item in fee_items)

    if not merchandise:
        raise FocusNFePayloadError("NFC-e exige ao menos um item.")

    mapped_items = [_map_item(idx, item, config) for idx, item in enumerate(merchandise, start=1)]
    product_total_q = _sum_focus_money_q(mapped_items, "valor_bruto")
    payment_total_q = _payment_total_q(payment)
    note_total_q = payment_total_q or (product_total_q + freight_q)

    payload = {
        "cnpj_emitente": _focus_cnpj_emitente(config),
        "natureza_operacao": config.get("natureza_operacao") or "VENDA AO CONSUMIDOR",
        "data_emissao": timezone.localtime().isoformat(),
        "tipo_documento": "1",
        "finalidade_emissao": "1",
        "consumidor_final": "1",
        "local_destino": str(config.get("local_destino_nfce") or "1"),
        "presenca_comprador": str(config.get("presenca_comprador_nfce") or "1"),
        "modalidade_frete": str(config.get("modalidade_frete_nfce") or "9"),
        "valor_produtos": _money_q(product_total_q),
        "valor_total": _money_q(note_total_q),
        "items": mapped_items,
        "formas_pagamento": _payment_forms(payment),
    }
    if freight_q > 0:
        payload["valor_frete"] = _money_q(freight_q)
        # Com frete, "sem ocorrência de transporte" (9) é inválido; o default
        # vira transporte próprio do emitente (0). Validar em homologação.
        if payload["modalidade_frete"] == "9":
            payload["modalidade_frete"] = str(config.get("modalidade_frete_com_taxa") or "0")
    if product_total_q + freight_q > note_total_q:
        payload["valor_desconto"] = _money_q(product_total_q + freight_q - note_total_q)
    if config.get("serie_nfce"):
        payload["serie"] = str(config["serie_nfce"])
    if additional_info:
        payload["informacoes_adicionais_contribuinte"] = str(additional_info)
    payload.update(_customer_fields(customer))
    payload["informacoes_adicionais_contribuinte"] = (
        payload.get("informacoes_adicionais_contribuinte") or f"Pedido {reference}"
    )
    return payload


def _is_delivery_fee_item(item: dict) -> bool:
    meta = item.get("meta") or {}
    return item.get("sku") == "__DELIVERY_FEE__" or meta.get("type") == "delivery_fee"


def _map_item(number: int, item: dict, config: dict) -> dict:
    fiscal = dict(item.get("fiscal") or {})
    ncm = _digits(_first(fiscal, "codigo_ncm", "ncm", default=""))
    if not ncm:
        raise FocusNFePayloadError(
            f"Produto {item.get('sku') or number} sem NCM em metadata.fiscal.ncm."
        )

    raw_qty = Decimal(str(item.get("qty") or 1))
    qty = _decimal(raw_qty, places="0.001")
    unit_price_q = int(item.get("unit_price_q") or 0)
    total_q = item.get("total_q")
    if total_q in (None, ""):
        total_q = int((Decimal(unit_price_q) * raw_qty).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    unit_price = _money_q(unit_price_q)
    total = _money_q(total_q)
    unit = str(_first(fiscal, "unidade_comercial", "unit", default=item.get("unit") or "UN")).upper()

    mapped = {
        "numero_item": str(number),
        "codigo_produto": str(item.get("sku") or number),
        "descricao": str(item.get("name") or item.get("description") or item.get("sku") or number)[:120],
        "codigo_ncm": ncm,
        "cfop": str(_first(fiscal, "cfop", default=config.get("default_cfop_nfce") or "5102")),
        "unidade_comercial": unit,
        "quantidade_comercial": qty,
        "valor_unitario_comercial": unit_price,
        "valor_bruto": total,
        "unidade_tributavel": unit,
        "quantidade_tributavel": qty,
        "valor_unitario_tributavel": unit_price,
        "icms_origem": str(_first(fiscal, "icms_origem", "origem", default="0")),
        "icms_situacao_tributaria": str(_first(fiscal, "icms_situacao_tributaria", "csosn", default="102")),
        "pis_situacao_tributaria": str(_first(fiscal, "pis_situacao_tributaria", default="07")),
        "cofins_situacao_tributaria": str(_first(fiscal, "cofins_situacao_tributaria", default="07")),
    }

    optional_map = {
        "cest": "cest",
        "codigo_beneficio_fiscal": "codigo_beneficio_fiscal",
        "ean": "ean",
        "codigo_barras_comercial": "codigo_barras_comercial",
    }
    for source, target in optional_map.items():
        value = fiscal.get(source)
        if value:
            mapped[target] = str(value)
    return mapped


def _payment_forms(payment: dict) -> list[dict]:
    payment = dict(payment or {})
    amount_q = int(payment.get("amount_q") or 0)
    tenders = payment.get("tenders") or []
    if tenders:
        forms = []
        for tender in tenders:
            tender_amount_q = int(tender.get("amount_q") or 0)
            if tender_amount_q <= 0:
                continue
            forms.append({
                "forma_pagamento": _payment_code(tender.get("method") or payment.get("method")),
                "valor_pagamento": _money_q(tender_amount_q),
            })
        if forms:
            return forms

    if amount_q <= 0:
        raise FocusNFePayloadError("Pagamento fiscal exige payment.amount_q > 0.")
    return [{
        "forma_pagamento": _payment_code(payment.get("method")),
        "valor_pagamento": _money_q(amount_q),
    }]


def _payment_total_q(payment: dict) -> int:
    payment = dict(payment or {})
    tenders = payment.get("tenders") or []
    if tenders:
        return sum(max(0, int(tender.get("amount_q") or 0)) for tender in tenders if isinstance(tender, dict))
    return max(0, int(payment.get("amount_q") or 0))


def _payment_code(method: object) -> str:
    value = str(method or "cash").strip().lower()
    return PAYMENT_METHOD_CODES.get(value, "99")


def _customer_fields(customer: dict) -> dict:
    from shopman.utils.documents import is_valid_tax_id

    customer = dict(customer or {})
    tax_id = _digits(customer.get("tax_id") or customer.get("cpf") or customer.get("cnpj"))
    if tax_id and not is_valid_tax_id(tax_id):
        # Melhor falhar aqui (claro, acionável) que rejeição assíncrona da SEFAZ.
        raise FocusNFePayloadError(
            f"CPF/CNPJ do cliente inválido ({tax_id[:4]}…): confira os dígitos."
        )
    fields = {}
    if len(tax_id) == 11:
        fields["cpf_destinatario"] = tax_id
    elif len(tax_id) == 14:
        fields["cnpj_destinatario"] = tax_id
    if tax_id:
        fields["indicador_inscricao_estadual_destinatario"] = "9"
    if tax_id and customer.get("name"):
        fields["nome_destinatario"] = str(customer["name"])[:60]
    if customer.get("email"):
        fields["email_destinatario"] = str(customer["email"])
    phone = _digits(customer.get("phone"))
    if phone:
        fields["telefone_destinatario"] = phone
    return fields


def _focus_cnpj_emitente(config: dict) -> str:
    configured = _digits(config.get("cnpj_emitente"))
    if configured:
        return configured
    return _digits(_shop_document())


def _shop_document() -> str:
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        return str(getattr(shop, "document", "") or "")
    except Exception:
        logger.debug("focus_nfe_shop_document_lookup_failed", exc_info=True)
        return ""


def _document_result(response: dict, config: dict | None = None) -> FiscalDocumentResult:
    status = _norm(response.get("status"))
    access_key = _first(response, "chave_nfe", "chave_nfce", "chave_acesso", "chave")
    # Chave presente NÃO significa autorizada: o Focus devolve chave também em
    # "processando_autorizacao" e em consultas de notas rejeitadas. Sucesso
    # exige status autorizado; chave sozinha só vale em resposta sem status.
    success = status in {"autorizado", "authorized", "emitido", "emitida"} or (
        not status and bool(access_key)
    )
    if not success and status in {"processando_autorizacao", "processando", "processing"}:
        return FiscalDocumentResult(
            success=False,
            document_id=_first(response, "ref", "id"),
            access_key=str(access_key) if access_key else None,
            status="processing",
            error_code="focus_nfe_processing",
            error_message="NFC-e em processamento na SEFAZ — consultar novamente.",
        )
    return FiscalDocumentResult(
        success=success,
        document_id=_first(response, "ref", "id"),
        document_number=_int_or_none(_first(response, "numero", "numero_nfce", "numero_nfe")),
        document_series=_int_or_none(_first(response, "serie")),
        access_key=str(access_key) if access_key else None,
        authorization_date=_first(response, "data_autorizacao", "data_emissao"),
        protocol_number=_first(response, "protocolo", "protocolo_autorizacao", "numero_protocolo"),
        xml_url=_focus_url(_first(response, "caminho_xml_nota_fiscal", "xml_url"), config),
        danfe_url=_focus_url(_first(response, "caminho_danfe", "danfe_url"), config),
        qrcode_url=_first(response, "qrcode_url", "url_qrcode", "qrcode"),
        status="authorized" if success else "denied",
        error_code=None if success else str(_first(response, "codigo", "codigo_erro", default="focus_nfe_not_authorized")),
        error_message=None if success else _response_error_message(response),
    )


def _document_error_result(exc: Exception) -> FiscalDocumentResult:
    body = _error_body(exc)
    return FiscalDocumentResult(
        success=False,
        status="denied",
        error_code=f"focus_nfe_http_{getattr(exc, 'code', 'error')}",
        error_message=body or str(exc),
    )


def _cancellation_error_result(exc: Exception) -> FiscalCancellationResult:
    body = _error_body(exc)
    return FiscalCancellationResult(
        success=False,
        error_code=f"focus_nfe_http_{getattr(exc, 'code', 'error')}",
        error_message=body or str(exc),
    )


def _response_error_message(response: dict) -> str:
    errors = response.get("erros") or response.get("errors")
    if isinstance(errors, list) and errors:
        return "; ".join(str(item.get("mensagem") or item.get("message") or item) for item in errors)
    return str(
        response.get("mensagem_sefaz")
        or response.get("mensagem")
        or response.get("message")
        or "Focus NFe não autorizou a NFC-e."
    )


def _error_body(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        raw = exc.read().decode("utf-8") if exc.fp else ""
        if not raw:
            return f"HTTP {exc.code}"
        try:
            parsed = json.loads(raw)
            return _response_error_message(parsed)
        except json.JSONDecodeError:
            return raw[:500]
    if isinstance(exc, URLError):
        return str(exc.reason)
    return str(exc)


def _focus_url(value: object, config: dict | None = None) -> str | None:
    if not value:
        return None
    text = str(value)
    if text.startswith(("http://", "https://")):
        return text
    base = _base_url(config or {})
    return f"{base}{text if text.startswith('/') else '/' + text}"


def _first(data: dict, *keys: str, default=None):
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def _digits(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _decimal(value: object, *, places: str) -> str:
    quant = Decimal(places)
    return str(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def _money_q(value: object) -> str:
    return _decimal(Decimal(int(value or 0)) / Decimal("100"), places="0.01")


def _sum_focus_money_q(rows: list[dict], field: str) -> int:
    total = Decimal("0")
    for row in rows:
        total += Decimal(str(row.get(field) or "0"))
    return int((total * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _norm(value: object) -> str:
    return str(value or "").strip().lower()


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["FocusNFeBackend"]
