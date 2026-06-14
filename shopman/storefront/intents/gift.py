"""Gift (entrega para terceiro) — integrity gate for checkout.

Spec canônica: ``docs/plans/GIFT-UX-PLAN.md``. Presente desacopla o
destinatário e o endereço do comprador, **sem** tocar identidade nem cobrança
(que continuam do comprador autenticado).

Este módulo é a guarda de integridade que o Pablo frisou: quando
``is_gift=True``, ``recipient.name`` e ``recipient.phone`` são obrigatórios e
validados; ``gift_message`` é opcional mas persistido íntegro; **nunca** grava
``recipient`` parcial. Quando ``is_gift=False``, devolve ``None`` — as chaves
não existem no pedido (não gravar vazias).

A função é pura (sem request) para ser testável isoladamente.
"""

from __future__ import annotations

from ._phone import normalize_phone_input


def build_gift_data(
    *,
    is_gift: bool,
    recipient_name: str | None,
    recipient_phone: str | None,
    gift_message: str | None = "",
) -> tuple[dict | None, dict[str, str]]:
    """Build the gift contribution to ``checkout_data``, or field errors.

    Returns ``(gift_data, {})`` quando é um presente válido — onde ``gift_data``
    é ``{"is_gift": True, "recipient": {"name", "phone"}, "gift_message"?}`` —,
    ``(None, {})`` quando não é presente, e ``(None, errors)`` quando é presente
    mas faltam/são inválidos os dados do destinatário.
    """
    errors: dict[str, str] = {}
    if not is_gift:
        return None, errors

    name = (recipient_name or "").strip()
    phone_raw = (recipient_phone or "").strip()
    message = (gift_message or "").strip()

    if not name:
        errors["recipient_name"] = "Informe o nome de quem vai receber o presente."

    phone = normalize_phone_input(phone_raw) if phone_raw else ""
    if not phone_raw:
        errors["recipient_phone"] = "Informe o telefone de quem vai receber o presente."
    elif not phone:
        errors["recipient_phone"] = (
            "Telefone do destinatário inválido. Informe com DDD, ex: (43) 99999-9999"
        )

    if errors:
        return None, errors

    gift_data: dict = {
        "is_gift": True,
        "recipient": {"name": name, "phone": phone},
    }
    if message:
        gift_data["gift_message"] = message
    return gift_data, errors
