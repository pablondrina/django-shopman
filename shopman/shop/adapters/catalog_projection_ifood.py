"""
iFood Catalog Projection adapter.

Implements ``CatalogProjectionBackend`` protocol from Offerman.
Pushes the internal catalog (as ``ProjectedItem`` snapshots) to the
iFood Merchant API.

Configuration (via ``SHOPMAN_IFOOD`` in settings):
    catalog_api_token:  Bearer token for the iFood Merchant API.
    catalog_api_base:   Base URL (default: https://merchant-api.ifood.com.br).
    merchant_id:        iFood merchant UUID.

Never logs the token value.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import requests

from shopman.offerman.protocols.projection import ProjectedItem, ProjectionResult

logger = logging.getLogger(__name__)

_DEFAULT_BASE = "https://merchant-api.ifood.com.br"
_CATALOG_PATH = "/catalog/v2.0/merchants/{merchant_id}/items"
_RETRACT_PATH = "/catalog/v2.0/merchants/{merchant_id}/items/{sku}/unavailable"
_REQUEST_TIMEOUT = 20


class IFoodRateLimitError(Exception):
    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(f"iFood rate limit — retry after {retry_after}s")


class IFoodCatalogProjection:
    """Concrete implementation of ``CatalogProjectionBackend`` for iFood."""

    def project(
        self,
        items: list[ProjectedItem],
        *,
        channel: str,
        full_sync: bool = False,
    ) -> ProjectionResult:
        cfg = _get_config()
        if not cfg.get("catalog_api_token"):
            return ProjectionResult(
                success=False,
                channel=channel,
                errors=["SHOPMAN_IFOOD.catalog_api_token not configured"],
            )

        errors: list[str] = []
        projected = 0

        for item in items:
            try:
                _upsert_item(item, cfg)
                projected += 1
            except IFoodRateLimitError:
                raise
            except Exception as exc:
                logger.warning("ifood.catalog: error projecting sku=%s: %s", item.sku, exc)
                errors.append(f"{item.sku}: {exc}")

        return ProjectionResult(
            success=not errors,
            projected=projected,
            errors=errors,
            channel=channel,
        )

    def retract(self, skus: list[str], *, channel: str) -> ProjectionResult:
        cfg = _get_config()
        if not cfg.get("catalog_api_token"):
            return ProjectionResult(
                success=False,
                channel=channel,
                errors=["SHOPMAN_IFOOD.catalog_api_token not configured"],
            )

        errors: list[str] = []
        projected = 0

        for sku in skus:
            try:
                _retract_item(sku, cfg)
                projected += 1
            except IFoodRateLimitError:
                raise
            except Exception as exc:
                logger.warning("ifood.catalog: error retracting sku=%s: %s", sku, exc)
                errors.append(f"{sku}: {exc}")

        return ProjectionResult(
            success=not errors,
            projected=projected,
            errors=errors,
            channel=channel,
        )


# ── Internal helpers ──────────────────────────────────────────────────────────


def _get_config() -> dict:
    from django.conf import settings
    return getattr(settings, "SHOPMAN_IFOOD", {})


def _headers(api_token: str) -> dict:
    return {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _item_payload(item: ProjectedItem) -> dict:
    price = float(Decimal(str(item.price_q)) / 100)
    payload: dict = {
        "externalCode": item.sku,
        "name": item.name,
        "description": item.description or "",
        "price": {"value": price, "originalValue": price},
        "available": item.is_published and item.is_sellable,
    }
    if item.image_url:
        payload["image"] = {"url": item.image_url}
    if item.category:
        payload["externalCategoryCode"] = item.category
    return payload


def _upsert_item(item: ProjectedItem, cfg: dict) -> None:
    merchant_id = cfg.get("merchant_id", "")
    base = cfg.get("catalog_api_base", _DEFAULT_BASE).rstrip("/")
    url = f"{base}{_CATALOG_PATH.format(merchant_id=merchant_id)}/{item.sku}"
    token = cfg["catalog_api_token"]

    resp = requests.put(
        url,
        json=_item_payload(item),
        headers=_headers(token),
        timeout=_REQUEST_TIMEOUT,
    )
    _check_rate_limit(resp)
    resp.raise_for_status()
    logger.debug("ifood.catalog: upserted sku=%s status=%s", item.sku, resp.status_code)


def _retract_item(sku: str, cfg: dict) -> None:
    merchant_id = cfg.get("merchant_id", "")
    base = cfg.get("catalog_api_base", _DEFAULT_BASE).rstrip("/")
    url = f"{base}{_RETRACT_PATH.format(merchant_id=merchant_id, sku=sku)}"
    token = cfg["catalog_api_token"]

    resp = requests.post(
        url,
        json={},
        headers=_headers(token),
        timeout=_REQUEST_TIMEOUT,
    )
    _check_rate_limit(resp)
    resp.raise_for_status()
    logger.debug("ifood.catalog: retracted sku=%s status=%s", sku, resp.status_code)


def _check_rate_limit(resp: requests.Response) -> None:
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        raise IFoodRateLimitError(retry_after=retry_after)
