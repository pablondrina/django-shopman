"""
Orderman IDs — Geração de identificadores únicos.
"""

from __future__ import annotations

import secrets
import string
from datetime import date, datetime

from django.utils import timezone

# Caracteres seguros para IDs (sem ambíguos: 0/O, 1/l/I)
_SAFE_CHARS = string.ascii_uppercase.replace("O", "").replace("I", "") + string.digits.replace("0", "").replace("1", "")


def _generate_id(prefix: str, length: int = 8) -> str:
    """Gera um ID único com prefixo no formato PREFIX-XXXXXXXX."""
    random_part = "".join(secrets.choice(_SAFE_CHARS) for _ in range(length))
    return f"{prefix}-{random_part}"


# Sufixo curto (1 letra + 2 dígitos) é ALEATÓRIO num espaço de 24×100 = 2.400 por
# (canal, dia). Aleatório pode repetir (aniversário), então sorteamos de novo se o ref
# já existe. O índice único de Order.ref é a guarda final (corrida rara → o commit
# regenera; ver services/commit.py).
_ORDER_REF_MAX_TRIES = 30


def _order_ref_candidate(channel_ref: str, business_day: date) -> str:
    """Um candidato a ref (via refs lib; fallback local se indisponível)."""
    try:
        from shopman.refs.generators import generate_value

        return generate_value("ORDER_REF", {
            "channel_ref": channel_ref,
            "business_date": business_day.isoformat(),
        })
    except (ImportError, LookupError):
        date_part = business_day.strftime("%y%m%d")
        letter = secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")  # sem I/O
        return f"{channel_ref}-{date_part}-{letter}{secrets.randbelow(100):02d}"


def generate_order_ref(channel_ref: str = "ORD", business_date: date | datetime | str | None = None) -> str:
    """Gera um ref de pedido único: {CHANNEL_REF}-{YYMMDD}-{L##} (ex. WEB-260421-A17).

    Código ALEATÓRIO (curto, memorável, não revela volume). Sorteia de novo enquanto o
    ref colidir com um já existente; o índice único no INSERT é a guarda final.
    """
    channel_ref = channel_ref.upper()
    if business_date is None:
        business_day = timezone.localdate()
    elif isinstance(business_date, datetime):
        business_day = business_date.date()
    elif isinstance(business_date, str):
        business_day = date.fromisoformat(business_date)
    else:
        business_day = business_date

    from shopman.orderman.models import Order

    candidate = _order_ref_candidate(channel_ref, business_day)
    for _ in range(_ORDER_REF_MAX_TRIES):
        if not Order.objects.filter(ref=candidate).exists():
            return candidate
        candidate = _order_ref_candidate(channel_ref, business_day)
    return candidate  # esgotou as tentativas (dia lotadíssimo) → índice único decide


def generate_session_key() -> str:
    """Gera chave única para Session. Formato: SESS-XXXXXXXXXXXX"""
    return _generate_id("SESS", 12)


def generate_line_id() -> str:
    """Gera ID único para linha de item. Formato: L-XXXXXXXX"""
    return _generate_id("L", 8)


def generate_issue_id() -> str:
    """Gera ID único para Issue. Formato: ISS-XXXXXXXX"""
    return _generate_id("ISS", 8)


def generate_action_id() -> str:
    """Gera ID único para Action. Formato: ACT-XXXXXXXX"""
    return _generate_id("ACT", 8)


def generate_idempotency_key() -> str:
    """Gera chave de idempotência. Formato: IDEM-XXXXXXXXXXXXXXXX"""
    return _generate_id("IDEM", 16)
