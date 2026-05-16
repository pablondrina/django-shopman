"""Versioned POS sale intent contract.

The POS UI sends an operator intent. This module validates and normalizes that
intent before the Orderman/CashShift services expand it into domain writes.
"""

from __future__ import annotations

from dataclasses import dataclass


POS_SALE_INTENT_VERSION = "pos.sale-intent.v1"

_ALLOWED_TOP_LEVEL_KEYS = {
    "intent_version",
    "schema_version",
    "items",
    "customer_name",
    "customer_ref",
    "customer_phone",
    "customer_tax_id",
    "customer_email",
    "customer_memory_action",
    "fulfillment_type",
    "delivery_address",
    "delivery_address_structured",
    "delivery_date",
    "delivery_time_slot",
    "delivery_fee_q",
    "order_notes",
    "payment_method",
    "payment_collection",
    "payment_tenders",
    "tendered_amount_q",
    "issue_fiscal_document",
    "receipt_mode",
    "receipt_email",
    "client_request_id",
    "tab_code",
    "tab_session_key",
    "manual_discount",
    "manager_approval",
    "cash_shift_id",
    "pos_terminal_ref",
}
_ALLOWED_PAYMENT_METHODS = {"cash", "pix", "card", "external", "mixed"}
_ALLOWED_PAYMENT_COLLECTIONS = {"terminal", "on_delivery"}
_ALLOWED_RECEIPT_MODES = {"none", "print", "email"}

POS_SALE_INTENT_PAYLOAD_KEYS = tuple(sorted(_ALLOWED_TOP_LEVEL_KEYS))
POS_SALE_INTENT_PAYMENT_METHODS = tuple(sorted(_ALLOWED_PAYMENT_METHODS))
POS_SALE_INTENT_PAYMENT_COLLECTIONS = tuple(sorted(_ALLOWED_PAYMENT_COLLECTIONS))
POS_SALE_INTENT_RECEIPT_MODES = tuple(sorted(_ALLOWED_RECEIPT_MODES))


@dataclass(frozen=True)
class PosIntentError(ValueError):
    """Validation error with stable recovery metadata for POS surfaces."""

    code: str
    message: str
    field: str = ""
    focus: str = ""
    status: int = 422
    recovery: str = ""

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "focus": self.focus,
            "recovery": self.recovery,
        }


@dataclass(frozen=True)
class PosSaleIntent:
    """Normalized POS sale intent ready for the POS application service."""

    version: str
    payload: dict
    warnings: tuple[str, ...] = ()


def parse_pos_sale_intent(raw: dict, *, for_commit: bool = True) -> PosSaleIntent:
    """Validate and normalize a raw POS sale intent.

    Missing ``intent_version`` is accepted for Python-level callers that still
    build payloads directly in tests/services. Any explicit unknown version is
    rejected so browser/API contracts fail loudly on drift.
    """
    if not isinstance(raw, dict):
        raise PosIntentError(
            code="invalid_payload",
            message="Payload do PDV precisa ser um objeto JSON.",
            focus="search",
            status=400,
        )

    version = str(raw.get("intent_version") or raw.get("schema_version") or POS_SALE_INTENT_VERSION).strip()
    if version != POS_SALE_INTENT_VERSION:
        raise PosIntentError(
            code="unknown_intent_version",
            message="Versão do contrato POS não reconhecida. Atualize a tela e tente novamente.",
            field="intent_version",
            focus="search",
            status=400,
            recovery="Atualize o PDV antes de reenviar a venda.",
        )

    unknown = sorted(str(key) for key in raw.keys() if key not in _ALLOWED_TOP_LEVEL_KEYS)
    if unknown:
        raise PosIntentError(
            code="unexpected_intent_field",
            message=f"Payload do PDV contém campo não permitido: {unknown[0]}.",
            field=unknown[0],
            focus="search",
            status=400,
            recovery="Atualize o PDV antes de reenviar a venda.",
        )

    payload = dict(raw)
    payload["intent_version"] = POS_SALE_INTENT_VERSION
    payload["items"] = _items(payload.get("items"), for_commit=for_commit)

    fulfillment_type = _fulfillment_type(payload.get("fulfillment_type"))
    payload["fulfillment_type"] = fulfillment_type

    payload["customer_name"] = _text(payload.get("customer_name"), limit=160)
    payload["customer_ref"] = _text(payload.get("customer_ref"), limit=80)
    payload["customer_phone"] = _text(payload.get("customer_phone"), limit=80)
    payload["customer_tax_id"] = _text(payload.get("customer_tax_id"), limit=32)
    payload["customer_email"] = _emailish(payload.get("customer_email"), field="customer_email")
    payload["customer_memory_action"] = _text(payload.get("customer_memory_action"), limit=80)

    payload["delivery_address"] = _text(payload.get("delivery_address"), limit=400)
    payload["delivery_time_slot"] = _text(payload.get("delivery_time_slot"), limit=80)
    payload["delivery_date"] = _text(payload.get("delivery_date"), limit=32)
    payload["order_notes"] = _text(payload.get("order_notes"), limit=500)
    payload["delivery_fee_q"] = _nonnegative_int(payload.get("delivery_fee_q"), "delivery_fee_q")
    payload["delivery_address_structured"] = _structured_address(payload.get("delivery_address_structured"))
    if for_commit and fulfillment_type == "delivery" and not payload["delivery_address"]:
        raise PosIntentError(
            code="delivery_address_required",
            message="Informe o endereço de entrega antes de finalizar.",
            field="delivery_address",
            focus="delivery_address",
            recovery="Preencha endereço, referência e horário prometido.",
        )

    payment_method = _payment_method(payload.get("payment_method") or "cash")
    payment_collection = _payment_collection(payload.get("payment_collection") or "terminal")
    if fulfillment_type != "delivery":
        payment_collection = "terminal"
    if payment_collection == "on_delivery" and payment_method not in {"cash", "mixed"}:
        raise PosIntentError(
            code="invalid_on_delivery_payment",
            message="Pagamento na entrega só é permitido para dinheiro.",
            field="payment_collection",
            focus="payment",
            recovery="Receba no caixa ou altere a forma para dinheiro.",
        )
    payload["payment_method"] = payment_method
    payload["payment_collection"] = payment_collection
    payload["payment_tenders"] = _tenders(payload.get("payment_tenders"))
    payload["tendered_amount_q"] = _optional_nonnegative_int(payload.get("tendered_amount_q"), "tendered_amount_q")

    payload["issue_fiscal_document"] = bool(payload.get("issue_fiscal_document"))
    if for_commit and payload["issue_fiscal_document"] and payload["delivery_fee_q"] > 0:
        raise PosIntentError(
            code="fiscal_delivery_fee_pending",
            message="Fiscal com taxa de entrega ainda exige revisão no gestor.",
            field="delivery_fee_q",
            focus="delivery_address",
            recovery="Finalize sem taxa, ou finalize sem fiscal e reprocesse no gestor após conferência.",
        )
    payload["receipt_mode"] = _receipt_mode(payload.get("receipt_mode") or "none")
    payload["receipt_email"] = _emailish(payload.get("receipt_email"), field="receipt_email")
    if for_commit and payload["receipt_mode"] == "email" and not payload["receipt_email"]:
        raise PosIntentError(
            code="receipt_email_required",
            message="Informe o e-mail para enviar o comprovante.",
            field="receipt_email",
            focus="receipt_email",
            recovery="Preencha o e-mail ou altere o comprovante para não emitir.",
        )

    payload["client_request_id"] = _client_request_id(payload.get("client_request_id"))
    payload["tab_code"] = _text(payload.get("tab_code"), limit=16)
    payload["tab_session_key"] = _text(payload.get("tab_session_key"), limit=120)

    payload["manual_discount"] = _manual_discount(payload.get("manual_discount"))
    payload["manager_approval"] = _manager_approval(payload.get("manager_approval"))
    if payload.get("cash_shift_id") not in (None, ""):
        payload["cash_shift_id"] = _nonnegative_int(payload.get("cash_shift_id"), "cash_shift_id")
    payload["pos_terminal_ref"] = _text(payload.get("pos_terminal_ref"), limit=120)

    return PosSaleIntent(version=POS_SALE_INTENT_VERSION, payload=payload)


def _items(raw, *, for_commit: bool) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        if for_commit:
            raise PosIntentError(
                code="cart_empty",
                message="Carrinho vazio — adicione produtos antes de fechar.",
                field="items",
                focus="search",
            )
        return []
    items = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise PosIntentError("invalid_item", "Item inválido no carrinho.", field=f"items.{idx}", focus="search")
        sku = _text(item.get("sku"), limit=120)
        if not sku:
            raise PosIntentError("item_sku_required", "Item sem SKU no carrinho.", field=f"items.{idx}.sku", focus="search")
        qty = _positive_int(item.get("qty", 1), f"items.{idx}.qty")
        unit_price_q = _nonnegative_int(item.get("unit_price_q", item.get("price_q", 0)), f"items.{idx}.unit_price_q")
        items.append({
            "sku": sku,
            "name": _text(item.get("name"), limit=180),
            "qty": qty,
            "unit_price_q": unit_price_q,
            "notes": _text(item.get("notes"), limit=280),
        })
    return items


def _tenders(raw) -> list[dict] | None:
    if raw in (None, "", []):
        return None
    if not isinstance(raw, list):
        raise PosIntentError("invalid_tenders", "Pagamentos informados são inválidos.", field="payment_tenders", focus="payment")
    tenders = []
    for idx, tender in enumerate(raw):
        if not isinstance(tender, dict):
            raise PosIntentError("invalid_tender", "Pagamento informado é inválido.", field=f"payment_tenders.{idx}", focus="payment")
        amount_q = _nonnegative_int(tender.get("amount_q"), f"payment_tenders.{idx}.amount_q")
        if amount_q <= 0:
            continue
        tenders.append({
            "method": _payment_method(tender.get("method") or "external"),
            "amount_q": amount_q,
            "collection": _payment_collection(tender.get("collection") or "terminal"),
            "reference": _text(tender.get("reference"), limit=120),
        })
    return tenders


def _structured_address(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    text_limits = {
        "formatted_address": 500,
        "route": 200,
        "street_number": 40,
        "neighborhood": 120,
        "city": 120,
        "state": 80,
        "state_code": 10,
        "postal_code": 40,
        "country": 120,
        "country_code": 10,
        "place_id": 255,
        "complement": 160,
        "delivery_instructions": 500,
        "reference": 160,
    }
    cleaned: dict = {}
    for key, value in raw.items():
        if key in text_limits:
            text = _text(value, limit=text_limits[key])
            if text:
                cleaned[key] = text
        elif key in {"latitude", "longitude"}:
            number = _optional_float(value)
            if number is not None:
                cleaned[key] = number
        elif key == "is_verified":
            cleaned[key] = bool(value)
    return cleaned


def _manual_discount(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    discount_q = _optional_nonnegative_int(raw.get("discount_q"), "manual_discount.discount_q") or 0
    if discount_q <= 0:
        return None
    discount_type = str(raw.get("type") or "percent").strip().lower()
    if discount_type not in {"percent", "fixed"}:
        discount_type = "fixed"
    return {
        "type": discount_type,
        "value": raw.get("value", 0),
        "discount_q": discount_q,
        "reason": _text(raw.get("reason") or "outro", limit=120),
    }


def _manager_approval(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    username = _text(raw.get("username"), limit=150)
    password = str(raw.get("password") or "")
    if not username and not password:
        return None
    return {"username": username, "password": password}


def _fulfillment_type(value) -> str:
    return "delivery" if str(value or "pickup").strip().lower() == "delivery" else "pickup"


def _payment_method(value) -> str:
    method = str(value or "cash").strip().lower()
    if method not in _ALLOWED_PAYMENT_METHODS:
        raise PosIntentError("invalid_payment_method", "Forma de pagamento inválida.", field="payment_method", focus="payment")
    return method


def _payment_collection(value) -> str:
    collection = str(value or "terminal").strip().lower()
    if collection not in _ALLOWED_PAYMENT_COLLECTIONS:
        raise PosIntentError("invalid_payment_collection", "Recebimento inválido.", field="payment_collection", focus="payment")
    return collection


def _receipt_mode(value) -> str:
    mode = str(value or "none").strip().lower()
    if mode not in _ALLOWED_RECEIPT_MODES:
        raise PosIntentError("invalid_receipt_mode", "Modo de comprovante inválido.", field="receipt_mode", focus="receipt")
    return mode


def _client_request_id(value) -> str:
    raw = _text(value, limit=128)
    if not raw:
        return ""
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in "-_:")
    if safe != raw:
        raise PosIntentError("invalid_client_request_id", "Identificador local da venda inválido.", field="client_request_id", focus="search")
    return raw


def _emailish(value, *, field: str) -> str:
    text = _text(value, limit=180).lower()
    if not text:
        return ""
    if "@" not in text or text.startswith("@") or text.endswith("@"):
        raise PosIntentError("invalid_email", "E-mail inválido.", field=field, focus="receipt_email")
    return text


def _text(value, *, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        text = text[:limit]
    return text


def _optional_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive_int(value, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PosIntentError("invalid_number", "Número inválido no POS.", field=field, focus="search") from exc
    if parsed <= 0:
        raise PosIntentError("invalid_quantity", "Quantidade precisa ser maior que zero.", field=field, focus="search")
    return parsed


def _nonnegative_int(value, field: str) -> int:
    parsed = _optional_nonnegative_int(value, field)
    return int(parsed or 0)


def _optional_nonnegative_int(value, field: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PosIntentError("invalid_number", "Número inválido no POS.", field=field, focus="payment") from exc
    if parsed < 0:
        raise PosIntentError("invalid_negative_amount", "Valor não pode ser negativo.", field=field, focus="payment")
    return parsed


__all__ = [
    "POS_SALE_INTENT_PAYLOAD_KEYS",
    "POS_SALE_INTENT_PAYMENT_COLLECTIONS",
    "POS_SALE_INTENT_PAYMENT_METHODS",
    "POS_SALE_INTENT_RECEIPT_MODES",
    "POS_SALE_INTENT_VERSION",
    "PosIntentError",
    "PosSaleIntent",
    "parse_pos_sale_intent",
]
