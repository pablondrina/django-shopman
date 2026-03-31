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

# English weekday name → Portuguese for error messages
_DAY_NAMES_PT = {
    "monday": "segunda",
    "tuesday": "terça",
    "wednesday": "quarta",
    "thursday": "quinta",
    "friday": "sexta",
    "saturday": "sábado",
    "sunday": "domingo",
}


class BusinessHoursValidator:
    """
    Rejects orders outside business hours based on Shop.opening_hours.

    Reads the shop's actual opening_hours (day-of-week + open/close times).
    Falls back to start/end constructor params if Shop is not available.
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
        now_dt = timezone.localtime()
        now_time = now_dt.time()
        weekday = now_dt.strftime("%A").lower()  # "monday", "tuesday", etc.

        # Try to read Shop.opening_hours for day-aware validation
        opening_hours = self._get_opening_hours()
        if opening_hours is not None:
            day_hours = opening_hours.get(weekday)
            if not day_hours:
                day_pt = _DAY_NAMES_PT.get(weekday, weekday)
                raise ValidationError(
                    f"Não aceitamos pedidos {day_pt}."
                )
            try:
                open_time = time.fromisoformat(day_hours["open"])
                close_time = time.fromisoformat(day_hours["close"])
            except (KeyError, ValueError):
                open_time = self.start
                close_time = self.end

            if not (open_time <= now_time < close_time):
                raise ValidationError(
                    f"Pedidos aceitos apenas entre "
                    f"{open_time.strftime('%H:%M')} e {close_time.strftime('%H:%M')}."
                )
            return

        # Fallback: use constructor defaults (no day-of-week check)
        if not (self.start <= now_time < self.end):
            raise ValidationError(
                f"Pedidos aceitos apenas entre "
                f"{self.start.strftime('%H:%M')} e {self.end.strftime('%H:%M')}."
            )

    @staticmethod
    def _get_opening_hours() -> dict | None:
        """Load opening_hours from Shop singleton, or None if unavailable."""
        try:
            from shop.models import Shop

            shop = Shop.load()
            if shop and shop.opening_hours:
                return shop.opening_hours
        except Exception:
            pass
        return None


class MinimumOrderValidator:
    """
    Minimum order value for delivery orders (R$ 10,00 by default).

    Applies when the session's fulfillment_type is "delivery", regardless of
    which channel the order comes from (WhatsApp, Web, etc.).
    Only applies at commit stage.
    """

    code = "shop.minimum_order"
    stage = "commit"

    def __init__(self, *, minimum_q: int = MINIMUM_ORDER_Q):
        self.minimum_q = minimum_q

    def validate(self, *, channel: Any, session: Any, ctx: dict) -> None:
        # Check fulfillment_type from session data (set by customer at checkout)
        session_data = getattr(session, "data", None) or {}
        fulfillment_type = session_data.get("fulfillment_type", "")

        # Fallback: also check channel ref for channels that are inherently delivery
        if not fulfillment_type:
            channel_ref = getattr(channel, "ref", "") if channel is not None else ""
            if "delivery" in channel_ref:
                fulfillment_type = "delivery"

        if fulfillment_type != "delivery":
            return

        items = session.items or []
        total_q = sum(item.get("line_total_q", 0) for item in items)

        if total_q < self.minimum_q:
            minimum_display = f"R$ {self.minimum_q / 100:.2f}".replace(".", ",")
            raise ValidationError(
                f"Pedido minimo para delivery: {minimum_display}."
            )
