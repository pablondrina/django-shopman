"""
Resolvers de emissão de NFC-e — exemplos prontos para ``SHOPMAN_FISCAL_EMISSION_RESOLVER``.

Um resolver é só ``callable(order) -> bool``: devolve True para emitir a nota, False para
não emitir. O motor (``shopman.shop.services.fiscal.emission_resolver``) chama o resolver
apontado no settings; se AUSENTE ou com erro, cai no fallback padrão (opt-in do operador).

Aponte no ambiente/settings, ex.:
    SHOPMAN_FISCAL_EMISSION_RESOLVER = "shopman.shop.fiscal_resolvers.on_request_or_tax_id"
"""

from __future__ import annotations


def always(order) -> bool:
    """Emite SEMPRE (toda venda vira NFC-e). Postura mais conservadora/fiscal."""
    return True


def on_request_or_tax_id(order) -> bool:
    """Emite quando o operador pediu OU o cliente informou CPF/CNPJ ("CPF na nota").

    É a regra prática de balcão: a maioria não pede nota; quem informa o documento
    quer a nota — então emite. Exemplo real recomendado para começar.
    """
    data = order.data or {}
    fiscal = data.get("fiscal") or {}
    customer = data.get("customer") or {}
    return bool(fiscal.get("issue_document") or (customer.get("tax_id") or "").strip())


def channels(*refs: str):
    """Fábrica: emite sempre nos canais dados (ex.: só no PDV presencial).

    Uso (resolver por canal exige um wrapper importável):
        emit_pdv = channels("pdv")
        SHOPMAN_FISCAL_EMISSION_RESOLVER = "meuapp.fiscais.emit_pdv"
    """
    allowed = {r.strip().lower() for r in refs if r.strip()}

    def _resolver(order) -> bool:
        return (getattr(order, "channel_ref", "") or "").lower() in allowed

    return _resolver


def above_amount_q(threshold_q: int):
    """Fábrica: emite quando o total é ≥ ``threshold_q`` centavos.

        emit_big = above_amount_q(10000)  # ≥ R$ 100,00
        SHOPMAN_FISCAL_EMISSION_RESOLVER = "meuapp.fiscais.emit_big"
    """

    def _resolver(order) -> bool:
        return int(getattr(order, "total_q", 0) or 0) >= int(threshold_q)

    return _resolver
