"""
Lead time de encomenda — antecedência mínima entre o pedido e a data prometida.

Política da padaria (fermentação natural): encomenda é CONTRATO com o cliente.
Um pão de fermentação longa não nasce da noite para o dia — registrar demanda
para uma data que a produção não alcança seria prometer o que não se pode
cumprir. Por isso o registro de DEMANDA (encomenda para data sem fornada
planejada) só pode ocorrer dentro do prazo do lead time.

Fontes (nesta ordem):
1. ``Product.metadata["lead_time_hours"]`` (Offerman; int, opcional) — o
   produto declara a própria antecedência.
2. ``ChannelConfig.stock.default_lead_time_hours`` — default do canal.
   0 = sem exigência.

O que o gate NÃO bloqueia:
- Encomenda para data COM Quant planejado (a fornada já está planejada — o
  compromisso existe). Quem decide isso são os pontos de enforcement
  (checkout / ``services.stock.hold``), que só consultam este módulo no
  caminho de demanda.
- Venda imediata de estoque físico de hoje (data de hoje nunca passa por
  lead time — o gate vale só para data futura/encomenda).

Regra de arredondamento de ``earliest_allowed_date``: a fornada da data D
começa no início do dia D — o lead time precisa estar COMPLETO antes disso.
``now + lead`` caindo no meio do dia D empurra a primeira data possível para
D+1 (ex.: pedido 24/07 15h com lead de 24h → pronto 25/07 15h → a fornada de
25/07 já começou → primeira data possível: 26/07).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def effective_lead_time_hours(sku: str, channel_ref: str | None) -> int:
    """Lead time efetivo (horas) para o SKU neste canal.

    ``Product.metadata["lead_time_hours"]`` vence quando declarado (mesmo 0);
    ausente/ilegível cai no ``ChannelConfig.stock.default_lead_time_hours``.
    Nunca negativo; degradação de leitura vira 0 (sem exigência) — lead time é
    política comercial, não gate de integridade: config ilegível não pode
    recusar venda.
    """
    declared = _product_lead_time_hours(sku)
    if declared is not None:
        return max(declared, 0)
    return max(_channel_default_lead_time_hours(channel_ref), 0)


def earliest_allowed_date(sku: str, channel_ref: str | None, now: datetime | None = None) -> date:
    """Primeira data em que a demanda do SKU pode ser registrada neste canal.

    Sem lead time → hoje. Com lead time, a primeira data cuja fornada começa
    (início do dia, timezone local) DEPOIS de ``now + lead_time`` completo.
    """
    hours = effective_lead_time_hours(sku, channel_ref)
    if now is None:
        now = timezone.now()
    if hours <= 0:
        return timezone.localdate(now)

    ready_local = timezone.localtime(now + timedelta(hours=hours))
    earliest = ready_local.date()
    if ready_local.time() != time.min:
        earliest += timedelta(days=1)
    return earliest


# ── helpers ──


def _product_lead_time_hours(sku: str) -> int | None:
    """``Product.metadata["lead_time_hours"]`` como int, ou None se ausente/ilegível."""
    if not sku:
        return None
    try:
        from shopman.offerman.models import Product

        metadata = (
            Product.objects.filter(sku=sku).values_list("metadata", flat=True).first()
        )
    except Exception:
        logger.debug("lead_time: product metadata lookup degraded sku=%s", sku, exc_info=True)
        return None
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get("lead_time_hours")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("lead_time: metadata.lead_time_hours ilegível sku=%s valor=%r", sku, raw)
        return None


def _channel_default_lead_time_hours(channel_ref: str | None) -> int:
    try:
        from shopman.shop.config import ChannelConfig

        return int(ChannelConfig.for_channel(channel_ref).stock.default_lead_time_hours)
    except Exception:
        logger.debug(
            "lead_time: channel config lookup degraded channel=%s", channel_ref, exc_info=True
        )
        return 0
