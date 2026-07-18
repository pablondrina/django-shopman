"""FOMO badges — urgência real derivada da operação da padaria.

Cada badge nasce de um fato verificável (estoque restante, fornada que acabou de
sair, lote de ontem, promoção com prazo). Urgência inventada destrói confiança:
se o dado não sustenta o badge, o badge não existe.

Puro e testável: recebe dicts já resolvidos pelo chamador (``api/fomo.py``),
não toca banco, não tem side effect. O relógio entra por ``now`` para o teste
não depender do horário da máquina.

Mecânicas cobertas (FOMO-BROADCAST-SPECS §1): F1 (últimas unidades), F3 (D-1),
F5 (saiu do forno), F13 (promoção expirando), F14 (happy hour).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.utils import timezone

# Quantos badges cabem num card sem virar poluição visual.
MAX_BADGES = 2

# "Saiu do forno" é efêmero por definição: passa de uma hora, não é mais notícia.
FRESH_WINDOW_MINUTES = 60

# Promoção só vira contagem regressiva quando o prazo aperta.
PROMO_COUNTDOWN_HOURS = 4

# Prioridade: 1 = mais urgente. Empate mantém a ordem de derivação.
PRIORITY_FRESH = 1
PRIORITY_LOW_STOCK = 1
PRIORITY_D1 = 2
PRIORITY_PROMO = 3
PRIORITY_HAPPY_HOUR = 3


@dataclass(frozen=True)
class FomoBadge:
    """Um badge de urgência pronto para exibição.

    ``expires_at`` é ISO-8601 (ou ``None`` quando o badge não caduca sozinho):
    o cliente pode sumir com o badge sem refetch quando o prazo passa.
    """

    type: str
    label: str
    priority: int
    expires_at: str | None = None
    meta: dict = field(default_factory=dict)


def badges_for_product(
    sku: str,
    *,
    availability: dict | None = None,
    production: dict | None = None,
    promotions: list | tuple = (),
    channel_config: dict | None = None,
    now: datetime | None = None,
) -> tuple[FomoBadge, ...]:
    """Derivar os badges FOMO de um produto.

    Args:
        sku: SKU do produto (entra no ``meta`` para o cliente correlacionar).
        availability: estado de estoque — ``available_qty``, ``d1_qty``,
            ``has_happy_hour``, ``happy_hour_end``.
        production: última fornada concluída — ``finished_at`` (datetime ou ISO)
            e, opcionalmente, ``quantity``. ``None`` quando não houve fornada.
        promotions: promoções ativas do SKU, cada uma com ``valid_until`` e ``name``.
        channel_config: aspecto ``stock`` do canal — ``low_stock_threshold``.
        now: relógio injetável (default: agora, timezone-aware).

    Returns:
        Até ``MAX_BADGES`` badges, do mais urgente para o menos.
    """
    now = now or timezone.now()
    availability = availability or {}
    channel_config = channel_config or {}

    badges: list[FomoBadge] = []
    badges.extend(_fresh(sku, production, now))
    badges.extend(_low_stock(sku, availability, channel_config))
    badges.extend(_d1(sku, availability))
    badges.extend(_promo_countdown(sku, promotions, now))
    badges.extend(_happy_hour(sku, availability))

    ordered = sorted(badges, key=lambda badge: badge.priority)
    return tuple(ordered[:MAX_BADGES])


# ── Mecânicas ────────────────────────────────────────────────────────


def _low_stock(sku: str, availability: dict, channel_config: dict) -> list[FomoBadge]:
    """F1 — "Últimas X unidades". Só entre 1 e o limiar do canal.

    Esgotado não gera badge: o card já vira "Esgotado" + "Me avise".
    """
    available = _int(availability.get("available_qty"))
    threshold = _int(channel_config.get("low_stock_threshold"), default=5)
    if not (0 < available <= threshold):
        return []
    label = "Última unidade" if available == 1 else f"Últimas {available} unidades"
    return [
        FomoBadge(
            type="low_stock",
            label=label,
            priority=PRIORITY_LOW_STOCK,
            meta={"sku": sku, "available": available, "threshold": threshold},
        )
    ]


def _d1(sku: str, availability: dict) -> list[FomoBadge]:
    """F3 — lote de ontem, com desconto automático, no último dia de venda.

    Sem travessão na copy (convenção de voz do storefront).
    """
    d1_qty = _int(availability.get("d1_qty"))
    if d1_qty <= 0:
        return []
    return [
        FomoBadge(
            type="d1",
            label="Último dia: amanhã não tem",
            priority=PRIORITY_D1,
            meta={"sku": sku, "qty": d1_qty},
        )
    ]


def _fresh(sku: str, production: dict | None, now: datetime) -> list[FomoBadge]:
    """F5 — "Saiu do forno há X min", válido por ``FRESH_WINDOW_MINUTES``."""
    if not production:
        return []
    finished_at = _parse_dt(production.get("finished_at"))
    if finished_at is None or finished_at > now:
        return []

    minutes_ago = int((now - finished_at).total_seconds() // 60)
    if minutes_ago > FRESH_WINDOW_MINUTES:
        return []

    label = "Saiu do forno agora" if minutes_ago < 1 else f"Saiu do forno há {minutes_ago} min"
    expires_at = finished_at + timedelta(minutes=FRESH_WINDOW_MINUTES)
    return [
        FomoBadge(
            type="fresh",
            label=label,
            priority=PRIORITY_FRESH,
            expires_at=expires_at.isoformat(),
            meta={
                "sku": sku,
                "minutes_ago": minutes_ago,
                "finished_at": finished_at.isoformat(),
            },
        )
    ]


def _promo_countdown(sku: str, promotions, now: datetime) -> list[FomoBadge]:
    """F13 — contagem regressiva quando faltam poucas horas para a promoção fechar."""
    badges: list[FomoBadge] = []
    for promo in promotions or ():
        valid_until = _parse_dt((promo or {}).get("valid_until"))
        if valid_until is None or valid_until <= now:
            continue
        hours_left = int((valid_until - now).total_seconds() // 3600)
        if hours_left > PROMO_COUNTDOWN_HOURS:
            continue
        label = (
            "Promoção acaba em menos de 1h"
            if hours_left < 1
            else f"Promoção acaba em {hours_left}h"
        )
        badges.append(
            FomoBadge(
                type="promo_countdown",
                label=label,
                priority=PRIORITY_PROMO,
                expires_at=valid_until.isoformat(),
                meta={"sku": sku, "hours_left": hours_left, "name": promo.get("name", "")},
            )
        )
    return badges


def _happy_hour(sku: str, availability: dict) -> list[FomoBadge]:
    """F14 — janela de desconto por horário, visível enquanto está valendo."""
    if not availability.get("has_happy_hour"):
        return []
    end = str(availability.get("happy_hour_end") or "").strip()
    label = f"Happy Hour até {end}" if end else "Happy Hour agora"
    return [
        FomoBadge(
            type="happy_hour",
            label=label,
            priority=PRIORITY_HAPPY_HOUR,
            meta={"sku": sku, "end": end},
        )
    ]


# ── Helpers ──────────────────────────────────────────────────────────


def _int(value, *, default: int = 0) -> int:
    """Coerção tolerante: Decimal, str e None chegam aqui vindos do estoque."""
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_dt(value) -> datetime | None:
    """Aceitar datetime ou ISO-8601 e devolver sempre timezone-aware."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed
