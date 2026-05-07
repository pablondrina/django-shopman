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


def generate_order_ref(channel_ref: str = "ORD", business_date: date | datetime | str | None = None) -> str:
    """Generate order ref via shopman.refs library.

    Format: {CHANNEL_REF}-{YYMMDD}-{CODE} e.g. WEB-260421-AB09.
    Falls back to {CHANNEL_REF}-{YYMMDD}-XXXX if the refs library is unavailable
    (standalone orderman tests, fresh installs before ORDER_REF is registered).
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
    try:
        from shopman.refs.generators import generate_value
        scope = {
            "channel_ref": channel_ref,
            "business_date": business_day.isoformat(),
        }
        return generate_value("ORDER_REF", scope)
    except (ImportError, LookupError):
        date_part = business_day.strftime("%y%m%d")
        random_part = "".join(secrets.choice(_SAFE_CHARS) for _ in range(4))
        return f"{channel_ref}-{date_part}-{random_part}"


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
