"""Validation rules — registered as validators in the orderman registry.

These rules ARE registered by the engine (register_active_rules) at boot.
They wrap the existing validators from shop.validators, adding configurability
via RuleConfig params in the admin.
"""

from __future__ import annotations

from datetime import time
from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone

from shopman.shop.rules import BaseRule

_DAY_NAMES_PT = {
    "monday": "segunda",
    "tuesday": "terça",
    "wednesday": "quarta",
    "thursday": "quinta",
    "friday": "sexta",
    "saturday": "sábado",
    "sunday": "domingo",
}


class BusinessHoursRule(BaseRule):
    """Annotates orders placed outside business hours.

    Does NOT block checkout — sets session.data["outside_business_hours"] = True
    so the flow layer can decide how to handle it (e.g. auto_cancel confirmation,
    adjusted lead time, operator review).

    Comportamento (WP-S6): se ``Shop.opening_hours`` estiver vazio/ausente, não
    marca fora do horário — alinhado ao storefront (``_shop_status`` trata como
    sempre aberto). Com grade configurada, usa ``open``/``close`` por dia da semana.
    """

    code = "shop.business_hours"
    label = "Horário de Funcionamento"
    rule_type = "validator"
    stage = "commit"
    default_params = {"start": "08:00", "end": "18:00"}

    def __init__(self, *, start: str = "08:00", end: str = "18:00"):
        self.start = time.fromisoformat(start)
        self.end = time.fromisoformat(end)

    def validate(self, *, channel: Any, session: Any, ctx: dict) -> None:
        is_outside = self._check_outside_hours()

        if is_outside:
            if not hasattr(session, "data") or session.data is None:
                session.data = {}
            session.data["outside_business_hours"] = True

    def _check_outside_hours(self) -> bool:
        """Return True if current time is outside business hours."""
        now_dt = timezone.localtime()
        now_time = now_dt.time()
        weekday = now_dt.strftime("%A").lower()

        opening_hours = self._get_opening_hours()
        if opening_hours is not None:
            day_hours = opening_hours.get(weekday)
            if not day_hours:
                return True
            try:
                open_time = time.fromisoformat(day_hours["open"])
                close_time = time.fromisoformat(day_hours["close"])
            except (KeyError, ValueError):
                open_time = self.start
                close_time = self.end
            return not (open_time <= now_time < close_time)

        # Sem grade no Shop: não inferir janela pelos defaults da regra (evita
        # divergência com o vitrine, que assume "sempre aberto" sem horários).
        return False

    @staticmethod
    def _get_opening_hours() -> dict | None:
        try:
            from shopman.shop.models import Shop

            shop = Shop.load()
            if shop and shop.opening_hours:
                return shop.opening_hours
        except Exception:
            pass
        return None


class DeliveryZoneRule(BaseRule):
    """Bloqueia checkout quando o endereço de entrega está fora das zonas cobertas.

    Ativado apenas quando fulfillment_type == "delivery" e
    session.data["delivery_zone_error"] é True (setado pelo DeliveryFeeModifier).
    """

    code = "shop.delivery_zone"
    label = "Zona de Entrega"
    rule_type = "validator"
    stage = "commit"
    default_params = {}

    def validate(self, *, channel: Any, session: Any, ctx: dict) -> None:
        from shopman.orderman.exceptions import ValidationError as OrderValidationError

        session_data = getattr(session, "data", None) or {}
        fulfillment_type = session_data.get("fulfillment_type", "")
        if fulfillment_type != "delivery":
            return

        if session_data.get("delivery_zone_error"):
            raise OrderValidationError(
                code="delivery_zone_not_covered",
                message="Não entregamos neste endereço ainda.",
            )


class MinimumOrderRule(BaseRule):
    """Minimum order value for delivery orders.

    Applies when fulfillment_type is "delivery".
    """

    code = "shop.minimum_order"
    label = "Pedido Mínimo Delivery"
    rule_type = "validator"
    stage = "commit"
    default_params = {"minimum_q": 1000}

    def __init__(self, *, minimum_q: int = 1000):
        self.minimum_q = minimum_q

    def validate(self, *, channel: Any, session: Any, ctx: dict) -> None:
        session_data = getattr(session, "data", None) or {}
        fulfillment_type = session_data.get("fulfillment_type", "")

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
            raise ValidationError(f"Pedido minimo para delivery: {minimum_display}.")
