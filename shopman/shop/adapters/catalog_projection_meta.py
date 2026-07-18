"""
Meta Catalog Projection adapter — Commerce Catalog via Graph ``items_batch``.

Implements ``CatalogProjectionBackend`` (Offerman) by pushing the internal catalog
(``ProjectedItem`` snapshots) to a **Meta Commerce Catalog**, which backs Instagram
Shopping + Facebook Shop (and, curated, WhatsApp — Arc G). One adapter, three
surfaces: the catalog is the single source Meta fans out from.

Contract (Graph API, ``POST /v{N}/{catalog_id}/items_batch``)
-------------------------------------------------------------

Body::

    {
      "item_type": "PRODUCT_ITEM",
      "allow_upsert": true,
      "requests": [
        {"method": "UPDATE", "retailer_id": "<sku>", "data": { …product fields… }},
        …
      ]
    }

- ``retailer_id`` is our stable SKU — re-syncing upserts the same product instead of
  duplicating (``allow_upsert`` makes UPDATE create-if-missing, so we never need to
  track Meta's internal id).
- **project** → ``method: "UPDATE"`` with the full ``data`` (title, description,
  availability, condition, price, link, image_link, brand, google_product_category,
  custom_label_0 = primary collection). Reads ``ProjectedItem.metadata["social"]``.
- **retract** → ``method: "UPDATE"`` with ``data: {"availability": "out of stock"}``.
  Non-destructive and reversible (mirrors the iFood adapter's UNAVAILABLE toggle); a
  later project flips it back. DELETE is the alternative but throws away the item, so
  we prefer availability. (Batch cap ≤5000 requests/call; Meta throttles ~100 calls/h.)

Price format (documented choice)
--------------------------------
Meta's **batch** API takes ``price`` as an **integer in the currency's minor unit**
(cents) plus a separate ``currency`` (ISO 4217) — NOT the ``"9.99 BRL"`` string the
CSV/RSS *feed* uses. That lines up 1:1 with our ``_q`` centavos convention: we send
``item.price_q`` verbatim and ``currency`` from config (default ``BRL``).

Availability enum is ``"in stock"`` / ``"out of stock"`` (with the space), condition
defaults to ``"new"``.

Authentication is a System User token via
:mod:`shopman.shop.services.meta_auth` (Bearer). Config lives in ``SHOPMAN_META``:

    catalog_id:    Meta Commerce Catalog id.
    access_token:  System User access token (Business Manager).
    api_version:   Graph version (default ``v21.0``).
    api_base:      Base URL (default ``https://graph.facebook.com``).
    currency:      ISO 4217 for ``price`` (default ``BRL``).
    store_url:     Public storefront base, used to build each item's ``link``.
    default_brand: Fallback ``brand`` when a product has none in its PIM.
    batch_size:    Max requests per ``items_batch`` call (default 5000, capped there).
"""

from __future__ import annotations

import logging

import requests
from shopman.offerman.protocols.projection import ProjectedItem, ProjectionResult

from shopman.shop.services import meta_auth

logger = logging.getLogger(__name__)

_MAX_BATCH = 5000  # Graph hard cap for items_batch
_AVAILABILITY_IN = "in stock"
_AVAILABILITY_OUT = "out of stock"


class MetaRateLimitError(Exception):
    """Raised when the Graph API responds with 429 Too Many Requests."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Meta rate limit hit; retry after {retry_after}s")


def _get_config() -> dict:
    from django.conf import settings

    return getattr(settings, "SHOPMAN_META", {}) or {}


def _base_url(cfg: dict) -> str:
    return str(cfg.get("api_base") or "https://graph.facebook.com").rstrip("/")


def _api_version(cfg: dict) -> str:
    return str(cfg.get("api_version") or "v21.0").strip("/")


def _endpoint(cfg: dict) -> str:
    return f"{_base_url(cfg)}/{_api_version(cfg)}/{cfg['catalog_id']}/items_batch"


def _batch_size(cfg: dict) -> int:
    size = int(cfg.get("batch_size") or _MAX_BATCH)
    return max(1, min(size, _MAX_BATCH))


def _chunk(seq: list, size: int):
    for start in range(0, len(seq), size):
        yield seq[start : start + size]


def _product_link(sku: str, cfg: dict) -> str:
    """Public storefront URL for the product (Meta requires a non-empty link on create)."""
    store_url = str(cfg.get("store_url") or "").rstrip("/")
    return f"{store_url}/{sku}" if store_url else ""


def _item_data(item: ProjectedItem, cfg: dict) -> dict:
    """Build the Meta ``data`` object for one product from a ProjectedItem + its PIM."""
    social = item.metadata.get("social") if isinstance(item.metadata, dict) else {}
    social = social if isinstance(social, dict) else {}
    available = item.is_published and item.is_sellable

    data: dict = {
        "title": item.name,
        "description": item.description or item.name,
        "availability": _AVAILABILITY_IN if available else _AVAILABILITY_OUT,
        "condition": str(social.get("condition") or "new"),
        # Integer minor units (cents) + separate currency — see module docstring.
        "price": int(item.price_q),
        "currency": str(cfg.get("currency") or "BRL"),
        "link": _product_link(item.sku, cfg),
        "image_link": item.image_url or "",
    }

    brand = str(social.get("brand") or cfg.get("default_brand") or "").strip()
    if brand:
        data["brand"] = brand
    if social.get("gtin"):
        data["gtin"] = str(social["gtin"])
    if social.get("google_product_category"):
        data["google_product_category"] = str(social["google_product_category"])
    if item.category:
        data["custom_label_0"] = item.category  # coleção primária (segmentação de ads)

    # Galeria → additional_image_link (string separada por vírgula, até 10 no Meta).
    gallery = item.metadata.get("gallery") if isinstance(item.metadata, dict) else None
    if isinstance(gallery, (list, tuple)):
        extra = [str(u) for u in gallery if u and str(u) != (item.image_url or "")][:10]
        if extra:
            data["additional_image_link"] = ",".join(extra)

    return data


def build_batch_requests(items: list[ProjectedItem], cfg: dict) -> list[dict]:
    """The ``requests`` list for a project (upsert) — one UPDATE per item."""
    return [
        {"method": "UPDATE", "retailer_id": item.sku, "data": _item_data(item, cfg)}
        for item in items
    ]


def build_retract_requests(skus: list[str]) -> list[dict]:
    """The ``requests`` list for a retract — UPDATE availability to out of stock."""
    return [
        {"method": "UPDATE", "retailer_id": sku, "data": {"availability": _AVAILABILITY_OUT}}
        for sku in skus
    ]


def _check_rate_limit(resp: requests.Response) -> None:
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        raise MetaRateLimitError(retry_after=retry_after)


def _post_batch(requests_list: list[dict], cfg: dict, headers: dict) -> None:
    """POST one chunk of ``requests`` to items_batch (raises on 429 / HTTP error)."""
    resp = requests.post(
        _endpoint(cfg),
        json={
            "item_type": "PRODUCT_ITEM",
            "allow_upsert": True,
            "requests": requests_list,
        },
        headers=headers,
        timeout=int(cfg.get("timeout") or 30),
    )
    _check_rate_limit(resp)
    resp.raise_for_status()


class MetaCatalogProjection:
    """Pushes catalog items to a Meta Commerce Catalog (Graph items_batch)."""

    def project(
        self,
        items: list[ProjectedItem],
        *,
        channel: str,
        full_sync: bool = False,
    ) -> ProjectionResult:
        cfg = _get_config()
        headers = meta_auth.authorized_headers({"Content-Type": "application/json"})
        if not headers:
            return ProjectionResult(
                success=False,
                errors=["Meta não configurado (access_token/catalog_id)"],
                channel=channel,
            )

        errors: list[str] = []
        projected = 0
        for chunk in _chunk(build_batch_requests(items, cfg), _batch_size(cfg)):
            try:
                _post_batch(chunk, cfg, headers)
                projected += len(chunk)
            except MetaRateLimitError:
                raise
            except Exception as exc:
                logger.debug("catalog_projection_meta.project degraded", exc_info=True)
                skus = ", ".join(r["retailer_id"] for r in chunk)
                errors.append(f"{skus}: {exc}")

        return ProjectionResult(
            success=len(errors) == 0,
            projected=projected,
            errors=errors,
            channel=channel,
        )

    def retract(self, skus: list[str], *, channel: str) -> ProjectionResult:
        cfg = _get_config()
        headers = meta_auth.authorized_headers({"Content-Type": "application/json"})
        if not headers:
            return ProjectionResult(
                success=False,
                errors=["Meta não configurado (access_token/catalog_id)"],
                channel=channel,
            )

        errors: list[str] = []
        retracted = 0
        for chunk in _chunk(build_retract_requests(skus), _batch_size(cfg)):
            try:
                _post_batch(chunk, cfg, headers)
                retracted += len(chunk)
            except MetaRateLimitError:
                raise
            except Exception as exc:
                logger.debug("catalog_projection_meta.retract degraded", exc_info=True)
                ids = ", ".join(r["retailer_id"] for r in chunk)
                errors.append(f"{ids}: {exc}")

        return ProjectionResult(
            success=len(errors) == 0,
            projected=retracted,
            errors=errors,
            channel=channel,
        )
