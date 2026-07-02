"""Validation rules — registered as validators in the orderman registry.

These rules ARE registered by the engine (register_active_rules) at boot.
They wrap the existing validators from shop.validators, adding configurability
via RuleConfig params in the admin.
"""

from __future__ import annotations

import logging
from datetime import time
from typing import Any

from django.utils import timezone

from shopman.shop.rules import BaseRule

logger = logging.getLogger(__name__)

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

        closed_dates = self._get_closed_dates()
        if closed_dates:
            from shopman.shop.services.business_calendar import closed_date_for

            closed, _, _ = closed_date_for(now_dt.date(), closed_dates)
            if closed:
                return True

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
            logger.debug("business_hours_rule: could not load shop opening hours", exc_info=True)
        return None

    @staticmethod
    def _get_closed_dates() -> list:
        try:
            from shopman.shop.models import Shop

            shop = Shop.load()
            defaults = (shop.defaults or {}) if shop else {}
            if not isinstance(defaults, dict):
                return []
            calendar = defaults.get("calendar") if isinstance(defaults.get("calendar"), dict) else {}
            dates = []
            for key in ("closed_dates", "closures", "holidays"):
                value = defaults.get(key)
                if isinstance(value, list):
                    dates.extend(value)
            for key in ("closed_dates", "closures", "holidays"):
                value = calendar.get(key)
                if isinstance(value, list):
                    dates.extend(value)
            return dates
        except Exception:
            logger.debug("business_hours_rule: could not load shop closed dates", exc_info=True)
        return []


class DeliveryZoneRule(BaseRule):
    """Gate de entrega no commit — cobertura de zona + pedido mínimo de entrega.

    Roda apenas quando ``fulfillment_type == "delivery"``. Bloqueia quando:

    - o endereço está fora das zonas cobertas
      (``session.data["delivery_zone_error"]``, setado pelo DeliveryFeeModifier); ou
    - o subtotal está abaixo do mínimo de entrega
      (``shop.defaults.rules.delivery_minimum_q``; ``0`` = sem mínimo).

    O mesmo ``delivery_minimum_q`` alimenta o aviso ao vivo no checkout
    (``build_delivery_minimum_progress``) — fonte única. Retirada nunca tem
    mínimo.
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

        # Sem taxa resolvida = zona nunca foi verificada (endereço só-texto,
        # sem CEP/bairro/coordenada). Delivery não commita sem cobertura
        # comprovada — senão a taxa sai zero e a zona vira opcional via API.
        if "delivery_fee_q" not in session_data:
            raise OrderValidationError(
                code="delivery_zone_unverified",
                message="Confirme o endereço com CEP para calcularmos a entrega.",
            )

        minimum_q = _delivery_minimum_q()
        if minimum_q:
            items = [
                item for item in (session.items or [])
                if item.get("sku") != "__DELIVERY_FEE__"
                and (item.get("meta") or {}).get("type") != "delivery_fee"
            ]
            # Cupom não conta pro mínimo (cortesia não tira elegibilidade de entrega) —
            # mesmo critério do aviso ao vivo (build_delivery_minimum_progress).
            coupon_discount_q = int(
                ((getattr(session, "pricing", None) or {}).get("coupon") or {}).get("discount_q", 0) or 0
            )
            total_q = sum(item.get("line_total_q", 0) for item in items) + coupon_discount_q
            if total_q < minimum_q:
                minimum_display = f"R$ {minimum_q / 100:.2f}".replace(".", ",")
                raise OrderValidationError(
                    code="below_delivery_minimum",
                    message=f"Pedido mínimo para entrega: {minimum_display}.",
                )


def _delivery_minimum_q() -> int:
    """Read the delivery minimum (cents) from ``shop.defaults.rules.delivery_minimum_q``."""
    from shopman.shop.projections.cart import shop_rule_q

    return shop_rule_q("delivery_minimum_q")
