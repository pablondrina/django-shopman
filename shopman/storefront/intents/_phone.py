"""Shared phone normalization for intent extraction."""
from __future__ import annotations

import logging

from shopman.utils.phone import normalize_phone

from ..constants import get_default_ddd

logger = logging.getLogger(__name__)


def normalize_phone_input(phone_raw: str) -> str:
    """Normalize phone to E.164, with default DDD fallback for 8–9 digit inputs."""
    if not phone_raw:
        return ""
    try:
        phone = normalize_phone(phone_raw)
        if not phone:
            digits = "".join(c for c in phone_raw if c.isdigit())
            if 8 <= len(digits) <= 9:
                phone = normalize_phone(f"{get_default_ddd()}{digits}")
        return phone or ""
    except (ValueError, TypeError):
        logger.exception("phone_normalization_failed")
        return ""
