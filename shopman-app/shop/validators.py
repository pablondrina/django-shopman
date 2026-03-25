"""
Shop — Custom order validators.

Validators follow the Ordering Validator protocol:
- code: str — unique identifier
- stage: str — "draft", "commit", or "import"
- validate(*, channel, session, ctx) -> None — raises ValidationError if invalid
"""
from __future__ import annotations

from datetime import time
from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone

# ── Configurable defaults ──────────────────────────────────────────
BUSINESS_HOURS_START = time(6, 0)
BUSINESS_HOURS_END = time(20, 0)
MINIMUM_ORDER_Q = 1000  # R$ 10,00 em centavos


class BusinessHoursValidator:
    """
    Rejects orders outside business hours (06h-20h by default).

    Only applies at commit stage.
    """

    code = "shop.business_hours"
    stage = "commit"

    def __init__(
        self,
        *,
        start: time = BUSINESS_HOURS_START,
        end: time = BUSINESS_HOURS_END,
    ):
        self.start = start
        self.end = end

    def validate(self, *, channel: Any, session: Any, ctx: dict) -> None:
        now = timezone.localtime().time()
        if not (self.start <= now < self.end):
            raise ValidationError(
                f"Pedidos aceitos apenas entre "
                f"{self.start.strftime('%H:%M')} e {self.end.strftime('%H:%M')}."
            )


class MinimumOrderValidator:
    """
    Minimum order value for delivery channel (R$ 10,00 by default).

    Only applies to channels with ref containing 'delivery'.
    Only applies at commit stage.
    """

    code = "shop.minimum_order"
    stage = "commit"

    def __init__(self, *, minimum_q: int = MINIMUM_ORDER_Q):
        self.minimum_q = minimum_q

    def validate(self, *, channel: Any, session: Any, ctx: dict) -> None:
        channel_ref = getattr(channel, "ref", "") if channel is not None else ""

        if "delivery" not in channel_ref:
            return

        items = session.items or []
        total_q = sum(item.get("line_total_q", 0) for item in items)

        if total_q < self.minimum_q:
            minimum_display = f"R$ {self.minimum_q / 100:.2f}".replace(".", ",")
            raise ValidationError(
                f"Pedido minimo para delivery: {minimum_display}."
            )
