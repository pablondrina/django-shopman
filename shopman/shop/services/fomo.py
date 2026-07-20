"""FOMO context — os fatos de domínio que sustentam os badges de urgência.

Divisão de trabalho em três camadas:

- **aqui (shop)** — LÊ o domínio: estoque, lote de ontem, última fornada,
  promoções, config do canal;
- ``storefront/presentation/fomo.py`` — DECIDE o que vira badge (puro);
- ``storefront/api/fomo.py`` — serve por HTTP.

As leituras vivem no shop porque atravessam Stockman e Craftsman, e superfície
não fala com kernel direto (regra de dependência do CLAUDE.md).

Toda leitura é defensiva: FOMO é enfeite. Se o estoque, a produção ou a
promoção falharem, o produto continua vendável e o card só perde o badge.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)

# Posição onde vive o lote de ontem (D-1). Canais que a excluem do escopo não
# vendem D-1 e portanto não anunciam D-1.
D1_POSITION_REF = "ontem"

# Espelha ``presentation.fomo.FRESH_WINDOW_MINUTES``: buscar fornada mais velha
# que a janela seria trabalho jogado fora, já que nunca viraria badge.
FRESH_WINDOW_MINUTES = 60


def context_for_sku(sku: str, *, channel_ref: str) -> dict:
    """Os insumos de ``badges_for_product``, resolvidos do estado atual."""
    config = _channel_config(channel_ref)
    return {
        "availability": _availability(sku, channel_ref=channel_ref, config=config),
        "production": last_finished_bake(sku),
        "promotions": _promotions_for_sku(sku),
        "social_proof": social_proof(sku),
        "channel_config": _stock_config(config),
    }


def cache_key(sku: str, channel_ref: str | None) -> str:
    """Chave canônica do cache de badges.

    Mora aqui porque tem dois donos: a API do storefront escreve e o emissor
    SSE invalida. Duas definições divergentes deixariam badge velho na tela.
    """
    return f"fomo:{sku}:{channel_ref or 'default'}"


# ── Estoque ──────────────────────────────────────────────────────────


def _availability(sku: str, *, channel_ref: str, config) -> dict:
    from shopman.shop.services import availability as avail_service

    data: dict = {"available_qty": 0, "d1_qty": 0}
    try:
        result = avail_service.check(sku, Decimal("1"), channel_ref=channel_ref)
        data["available_qty"] = result.get("available_qty", 0)
    except Exception:
        logger.debug("fomo.availability_failed sku=%s", sku, exc_info=True)

    data["d1_qty"] = d1_qty(sku, config=config)
    data.update(_happy_hour())
    return data


def d1_qty(sku: str, *, config) -> int:
    """Quanto há do lote de ontem — zero quando o canal não vende D-1.

    O gate por ``excluded_positions`` é o mesmo que o ``check`` usa para
    montar o escopo: badge e carrinho nunca divergem.
    """
    excluded = list(getattr(getattr(config, "stock", None), "excluded_positions", []) or [])
    if D1_POSITION_REF in excluded:
        return 0
    try:
        from shopman.stockman.models import Quant

        total = sum(
            quant.available
            for quant in Quant.objects.filter(sku=sku, position__ref=D1_POSITION_REF)
        )
        return max(int(total), 0)
    except Exception:
        logger.debug("fomo.d1_lookup_failed sku=%s", sku, exc_info=True)
        return 0


def _happy_hour() -> dict:
    from shopman.shop.projections.storefront_context import happy_hour_state

    try:
        state = happy_hour_state() or {}
    except Exception:
        logger.debug("fomo.happy_hour_failed", exc_info=True)
        return {}
    if not state.get("active"):
        return {}
    return {"has_happy_hour": True, "happy_hour_end": state.get("end", "")}


# ── Produção ─────────────────────────────────────────────────────────


def last_finished_bake(sku: str) -> dict | None:
    """A fornada mais recente deste SKU, se ainda estiver dentro da janela.

    Filtrar por ``finished_at`` no banco (e não em Python) mantém a query
    barata mesmo com histórico longo de work orders.
    """
    try:
        from shopman.craftsman.models import WorkOrder

        cutoff = timezone.now() - timedelta(minutes=FRESH_WINDOW_MINUTES)
        work_order = (
            WorkOrder.objects.filter(
                output_sku=sku,
                status=WorkOrder.Status.FINISHED,
                finished_at__gte=cutoff,
            )
            .order_by("-finished_at")
            .first()
        )
    except Exception:
        logger.debug("fomo.production_lookup_failed sku=%s", sku, exc_info=True)
        return None

    if work_order is None:
        return None
    return {
        "finished_at": work_order.finished_at,
        "work_order_ref": work_order.ref,
        "quality": (work_order.meta or {}).get("quality", ""),
    }


# ── Prova social ─────────────────────────────────────────────────────


def social_proof(sku: str) -> dict:
    """F16 + F17 — quanta gente está na fila e quanta gente já levou hoje.

    Janelas diferentes de propósito: "vendidos" é do dia corrente (venda de
    ontem não prova movimento hoje), enquanto a fila de "me avise" vale
    enquanto ninguém foi avisado — ela É a espera, e zerá-la à meia-noite
    apagaria gente que continua esperando.

    Cada contagem falha para zero por conta própria: uma consulta ruim da fila
    não pode apagar o "vendidos hoje" (e vice-versa).
    """
    return {"demand_count": demand_count(sku), "sold_today": sold_today(sku)}


def demand_count(sku: str) -> int:
    """F16 — quantas pessoas estão na fila de "me avise" deste SKU.

    Conta a fila de ``StockAlertSubscription`` pendente, não demand holds: o
    badge aparece ao lado do botão "Me avise", então o número precisa ser
    exatamente a fila em que aquele botão faz entrar. Contar outra população
    faria a copy prometer uma fila e exibir outra.

    Conta gente, não unidades — o badge fala de pessoas. Passa pelo adapter
    porque ``StockAlertSubscription`` é model do storefront e shop não importa
    superfície direto (ADR-001).
    """
    try:
        from shopman.shop.adapters import audience_sources

        return max(int(audience_sources.pending_alert_count(sku)), 0)
    except Exception:
        logger.debug("fomo.demand_count_failed sku=%s", sku, exc_info=True)
        return 0


def sold_today(sku: str) -> int:
    """F17 — unidades vendidas hoje, pedidos cancelados fora.

    Soma quantidade (não linhas): "12 vendidos" é sobre pães que saíram, e um
    pedido de 6 unidades pesa 6. Agrega no banco para não trazer as linhas.
    """
    try:
        from django.db.models import Sum
        from shopman.orderman.models import Order, OrderItem

        total = OrderItem.objects.filter(
            sku=sku,
            order__created_at__date=timezone.localdate(),
        ).exclude(order__status=Order.Status.CANCELLED).aggregate(total=Sum("qty"))["total"]
        return max(int(total or 0), 0)
    except Exception:
        logger.debug("fomo.sold_today_failed sku=%s", sku, exc_info=True)
        return 0


# ── Promoções ────────────────────────────────────────────────────────


def _promotions_for_sku(sku: str) -> list[dict]:
    """Promoções automáticas ativas que alcançam este SKU incondicionalmente.

    Badge de vitrine é promessa: só anuncia o que vale para qualquer visitante,
    agora, sem depender de quem ele é (segmento, aniversário), de quanto vai
    gastar (``min_order_q``) ou de como vai receber (``fulfillment_types``).
    Promo condicional continua valendo no carrinho, só não vira contagem
    regressiva no card.
    """
    from shopman.shop.adapters import promotion as promotion_adapter

    try:
        promos = promotion_adapter.get_active_promotions(timezone.now())
    except Exception:
        logger.debug("fomo.promotions_failed sku=%s", sku, exc_info=True)
        return []

    collections = _collections_for_sku(sku)
    matched = []
    for promo in promos:
        if promo.birthday_only or promo.customer_segments or promo.fulfillment_types:
            continue
        if promo.min_order_q:
            continue
        if promo.skus and sku not in promo.skus:
            continue
        if promo.collections and not any(ref in promo.collections for ref in collections):
            continue
        matched.append({"name": promo.name, "valid_until": promo.valid_until})
    return matched


def _collections_for_sku(sku: str) -> list[str]:
    from shopman.shop.projections import catalog_context

    try:
        return list(catalog_context.collection_refs_by_sku([sku]).get(sku, []))
    except Exception:
        logger.debug("fomo.collections_failed sku=%s", sku, exc_info=True)
        return []


# ── Config ───────────────────────────────────────────────────────────


def _channel_config(channel_ref: str):
    from shopman.shop.config import ChannelConfig

    try:
        return ChannelConfig.for_channel(channel_ref)
    except Exception:
        logger.debug("fomo.channel_config_failed channel=%s", channel_ref, exc_info=True)
        return ChannelConfig()


def _stock_config(config) -> dict:
    stock = getattr(config, "stock", None)
    return {"low_stock_threshold": getattr(stock, "low_stock_threshold", 5)}
