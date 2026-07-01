"""
iFood Catalog Projection adapter — catalog v2.0 (verified live 2026-06-30).

Implements ``CatalogProjectionBackend`` (Offerman) by pushing the internal
catalog (``ProjectedItem`` snapshots) to the iFood Merchant Catalog API.

Live contract (test store ``f36a17d0-…``)
----------------------------------------

Structure: **Merchant → Catálogos → Categorias → Itens**.

- **Upsert an item** — ``PUT /catalog/v2.0/merchants/{mid}/items`` → ``200``.
  Body is a *FullItemDto*::

        {
          "item":     {"id", "productId", "status", "price", "categoryId",
                       "externalCode", "index", "shifts"},
          "products": [{"id", "name", "description", "externalCode"}]
        }

  ``item.id``, ``item.productId`` and ``products[0].id`` **must be UUIDs**, and
  ``item.productId`` must equal ``products[0].id``. We derive both UUIDs
  deterministically from ``(merchant_id, sku)`` (uuid5), so re-syncing the same
  SKU upserts the same item instead of duplicating it.

- **Toggle availability / retract** — ``PATCH /catalog/v2.0/merchants/{mid}/items/status``
  → ``200``. Body is a single object ``{"itemId": <item uuid>, "status":
  "AVAILABLE"|"UNAVAILABLE"}``.

Authentication is OAuth 2.0 ``client_credentials`` via
:mod:`shopman.shop.services.ifood_auth` (Bearer + the mandatory own User-Agent —
iFood's WAF answers ``403`` to a generic UA). Config lives in the
``SHOPMAN_IFOOD`` Django setting:

    merchant_id:         iFood merchant UUID.
    api_base:            Base URL (default ``https://merchant-api.ifood.com.br``).
    catalog_category_map: ``{internal_collection_ref: ifood_category_uuid}``.
    catalog_default_category: iFood category UUID for items with no mapped
                         collection (optional). Items with neither a mapped
                         collection nor a default are reported as errors — an
                         item cannot be pushed without a target category.
"""

from __future__ import annotations

import logging
import uuid

import requests
from shopman.offerman.protocols.projection import ProjectedItem, ProjectionResult

from shopman.shop.services import ifood_auth

logger = logging.getLogger(__name__)

# Fixed namespace so item/product UUIDs are stable across processes and syncs.
_UUID_NS = uuid.UUID("f0f4d7e2-0e2a-5c7a-9d1b-6b1e2a3c4d5e")


class IFoodRateLimitError(Exception):
    """Raised when the iFood API responds with 429 Too Many Requests."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"iFood rate limit hit; retry after {retry_after}s")


class IFoodCategoryError(Exception):
    """Raised when an item has no resolvable iFood category."""


def _get_config(channel: str = "ifood") -> dict:
    from django.conf import settings
    return getattr(settings, "SHOPMAN_IFOOD", {})


def _base_url(cfg: dict) -> str:
    return str(cfg.get("api_base") or "https://merchant-api.ifood.com.br").rstrip("/")


def _product_uuid(merchant_id: str, sku: str) -> str:
    return str(uuid.uuid5(_UUID_NS, f"{merchant_id}:product:{sku}"))


def _item_uuid(merchant_id: str, sku: str) -> str:
    return str(uuid.uuid5(_UUID_NS, f"{merchant_id}:item:{sku}"))


def _resolve_category_id(item: ProjectedItem, cfg: dict) -> str:
    """Map the item's internal collection to an iFood category UUID.

    Raises :class:`IFoodCategoryError` when neither a mapped collection nor a
    configured default is available — pushing to the wrong category silently
    would be worse than failing loudly.
    """
    category_map = cfg.get("catalog_category_map") or {}
    if item.category and item.category in category_map:
        return str(category_map[item.category])
    default = cfg.get("catalog_default_category")
    if default:
        return str(default)
    raise IFoodCategoryError(
        f"no iFood category for collection={item.category!r} "
        "(set catalog_category_map or catalog_default_category in SHOPMAN_IFOOD)"
    )


def _item_payload(item: ProjectedItem, *, merchant_id: str, category_id: str) -> dict:
    """Build the FullItemDto body for ``PUT /items`` from a ProjectedItem."""
    price = round(item.price_q / 100, 2)
    product_id = _product_uuid(merchant_id, item.sku)
    item_id = _item_uuid(merchant_id, item.sku)
    available = item.is_published and item.is_sellable
    return {
        "item": {
            "id": item_id,
            "productId": product_id,
            "status": "AVAILABLE" if available else "UNAVAILABLE",
            "price": {"value": price, "originalValue": price},
            "categoryId": category_id,
            "externalCode": item.sku,
            "index": 0,
            "shifts": [],
        },
        "products": [
            {
                "id": product_id,
                "name": item.name,
                "description": item.description,
                "externalCode": item.sku,
                **({"image": {"url": item.image_url}} if item.image_url else {}),
            }
        ],
    }


def _check_rate_limit(resp: requests.Response) -> None:
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        raise IFoodRateLimitError(retry_after=retry_after)


def _headers(cfg: dict) -> dict | None:
    """OAuth Bearer + own User-Agent, or None when iFood auth is not configured."""
    return ifood_auth.authorized_headers({"Content-Type": "application/json"})


def _upsert_item(item: ProjectedItem, cfg: dict, headers: dict) -> None:
    merchant_id = cfg["merchant_id"]
    category_id = _resolve_category_id(item, cfg)
    url = f"{_base_url(cfg)}/catalog/v2.0/merchants/{merchant_id}/items"
    resp = requests.put(
        url,
        json=_item_payload(item, merchant_id=merchant_id, category_id=category_id),
        headers=headers,
        timeout=int(cfg.get("timeout") or 30),
    )
    _check_rate_limit(resp)
    resp.raise_for_status()


def _set_item_status(sku: str, status: str, cfg: dict, headers: dict) -> None:
    merchant_id = cfg["merchant_id"]
    url = f"{_base_url(cfg)}/catalog/v2.0/merchants/{merchant_id}/items/status"
    resp = requests.patch(
        url,
        json={"itemId": _item_uuid(merchant_id, sku), "status": status},
        headers=headers,
        timeout=int(cfg.get("timeout") or 30),
    )
    _check_rate_limit(resp)
    resp.raise_for_status()


class IFoodCatalogProjection:
    """Pushes catalog items to the iFood Merchant Catalog API (v2.0)."""

    def project(
        self,
        items: list[ProjectedItem],
        *,
        channel: str,
        full_sync: bool = False,
    ) -> ProjectionResult:
        cfg = _get_config(channel)
        headers = _headers(cfg)
        if not headers:
            return ProjectionResult(
                success=False,
                errors=["iFood OAuth is not configured (client_id/client_secret)"],
                channel=channel,
            )

        errors: list[str] = []
        projected = 0
        for item in items:
            try:
                _upsert_item(item, cfg, headers)
                projected += 1
            except IFoodRateLimitError:
                raise
            except Exception as exc:
                logger.debug("catalog_projection_ifood.project degraded", exc_info=True)
                errors.append(f"{item.sku}: {exc}")

        return ProjectionResult(
            success=len(errors) == 0,
            projected=projected,
            errors=errors,
            channel=channel,
        )

    def retract(self, skus: list[str], *, channel: str) -> ProjectionResult:
        cfg = _get_config(channel)
        headers = _headers(cfg)
        if not headers:
            return ProjectionResult(
                success=False,
                errors=["iFood OAuth is not configured (client_id/client_secret)"],
                channel=channel,
            )

        errors: list[str] = []
        retracted = 0
        for sku in skus:
            try:
                _set_item_status(sku, "UNAVAILABLE", cfg, headers)
                retracted += 1
            except IFoodRateLimitError:
                raise
            except Exception as exc:
                logger.debug("catalog_projection_ifood.retract degraded", exc_info=True)
                errors.append(f"{sku}: {exc}")

        return ProjectionResult(
            success=len(errors) == 0,
            projected=retracted,
            errors=errors,
            channel=channel,
        )
