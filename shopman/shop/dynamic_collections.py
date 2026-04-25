"""Dynamic collections — coleções curadas pelo sistema, resolvidas em tempo real.

Complementam as Collections estáticas do Offerman (operador cria, produto é
associado). Dinâmicas não têm linhas no DB — são Python resolvers que retornam
produtos baseados em métricas (vendas, data de produção, novidade, etc.).

**Configuração**: quais dinâmicas aparecem no menu e em que ordem fica em
``Shop.defaults["menu"]["dynamic_collections"]`` (ou ``Channel.config``),
como lista de refs (``["featured", "fresh_from_oven"]``).

**Uso**:
    from shopman.shop import dynamic_collections as dyn
    section = dyn.resolve("featured", channel_ref="delivery")
    # Retorna DynamicSection(meta, products) ou None se ref desconhecido
    # ou produtos vazios.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Protocol

from django.utils import timezone

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from shopman.offerman.models import Product


@dataclass(frozen=True)
class DynamicCollectionMeta:
    """Metadata estática de uma dinâmica: ref, label, ícone, descrição."""

    ref: str            # "featured", "fresh_from_oven", ...
    label: str          # "Destaques"
    icon: str           # Material Symbols ligature
    description: str    # Subtítulo para a seção


@dataclass(frozen=True)
class DynamicSection:
    """Resultado de um resolver: metadados + produtos."""

    meta: DynamicCollectionMeta
    products: tuple["Product", ...]


class DynamicCollectionResolver(Protocol):
    meta: DynamicCollectionMeta

    def resolve(self, channel_ref: str, limit: int = 20) -> list["Product"]:
        ...


# ── Registry ──────────────────────────────────────────────────────────

_registry: dict[str, DynamicCollectionResolver] = {}


def register(resolver_instance: DynamicCollectionResolver) -> None:
    """Registra uma dinâmica no registry global."""
    _registry[resolver_instance.meta.ref] = resolver_instance


def get(ref: str) -> DynamicCollectionResolver | None:
    return _registry.get(ref)


def all_refs() -> list[str]:
    return list(_registry.keys())


def resolve(ref: str, *, channel_ref: str, limit: int = 20) -> DynamicSection | None:
    """Resolve uma dinâmica para um canal. Retorna None se vazio ou ausente."""
    resolver = _registry.get(ref)
    if resolver is None:
        return None
    try:
        products = resolver.resolve(channel_ref, limit=limit)
    except Exception:
        logger.exception(
            "dynamic_collections.resolve failed ref=%s channel=%s", ref, channel_ref,
        )
        return None
    if not products:
        return None
    return DynamicSection(meta=resolver.meta, products=tuple(products))


# ── Built-in resolvers ────────────────────────────────────────────────


class FeaturedResolver:
    """Destaques: mais vendidos nos últimos 30 dias; fallback: sort_order."""

    meta = DynamicCollectionMeta(
        ref="featured",
        label="Destaques",
        icon="local_fire_department",
        description="Os mais vendidos e curados pela casa.",
    )

    WINDOW_DAYS = 30

    def resolve(self, channel_ref: str, limit: int = 20) -> list["Product"]:
        from django.db.models import Count
        from shopman.offerman.models import Product
        from shopman.orderman.models import OrderItem

        since = timezone.now() - timedelta(days=self.WINDOW_DAYS)
        top_skus = (
            OrderItem.objects
            .filter(order__created_at__gte=since)
            .values("sku")
            .annotate(n=Count("id"))
            .order_by("-n")
            .values_list("sku", flat=True)[:limit]
        )
        top_skus = list(top_skus)
        if top_skus:
            # Manter ordem de mais vendidos
            preserved = {sku: idx for idx, sku in enumerate(top_skus)}
            products = list(
                Product.objects
                .filter(sku__in=top_skus, is_published=True, is_sellable=True)
            )
            products.sort(key=lambda p: preserved.get(p.sku, 9999))
            if products:
                return products

        # Fallback: produtos com is_featured no metadata ou menor sort_order
        qs = Product.objects.filter(is_published=True, is_sellable=True)
        featured_in_meta = [p for p in qs if (p.metadata or {}).get("is_featured")]
        if featured_in_meta:
            return featured_in_meta[:limit]
        return list(qs.order_by("sort_order", "name")[:limit])


class FreshFromOvenResolver:
    """Recém saídos do forno: WorkOrders completas nos últimos 60 minutos."""

    meta = DynamicCollectionMeta(
        ref="fresh_from_oven",
        label="Recém saídos do forno",
        icon="schedule",
        description="Saíram do forno nos últimos 60 minutos.",
    )

    WINDOW_MINUTES = 60

    def resolve(self, channel_ref: str, limit: int = 20) -> list["Product"]:
        try:
            from shopman.craftsman.models import WorkOrder
        except ImportError:
            return []
        from shopman.offerman.models import Product

        since = timezone.now() - timedelta(minutes=self.WINDOW_MINUTES)
        try:
            recent_skus = (
                WorkOrder.objects
                .filter(status="completed", completed_at__gte=since)
                .values_list("product_sku", flat=True)
                .distinct()
            )
            recent_skus = list(recent_skus)
        except Exception:
            logger.debug("fresh_from_oven: query failed, returning empty", exc_info=True)
            return []

        if not recent_skus:
            return []
        return list(
            Product.objects
            .filter(sku__in=recent_skus, is_published=True, is_sellable=True)
            .order_by("name")[:limit]
        )


class NewArrivalsResolver:
    """Novidades: produtos publicados nos últimos 14 dias."""

    meta = DynamicCollectionMeta(
        ref="new_arrivals",
        label="Novidades",
        icon="fiber_new",
        description="Chegaram recentemente ao cardápio.",
    )

    WINDOW_DAYS = 14

    def resolve(self, channel_ref: str, limit: int = 20) -> list["Product"]:
        from shopman.offerman.models import Product

        since = timezone.now() - timedelta(days=self.WINDOW_DAYS)
        return list(
            Product.objects
            .filter(is_published=True, is_sellable=True, created_at__gte=since)
            .order_by("-created_at")[:limit]
        )


# Registra built-ins
register(FeaturedResolver())
register(FreshFromOvenResolver())
register(NewArrivalsResolver())
