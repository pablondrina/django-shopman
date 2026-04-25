"""
iFood Catalog Projection adapter.

Implements ``CatalogProjectionBackend`` protocol from Offerman.
Pushes the internal catalog (as ``ProjectedItem`` snapshots) to the
iFood Merchant API using the catalog v2.0 endpoint.

Configuration lives in ``SHOPMAN_IFOOD`` Django setting:
    catalog_api_token: Bearer token for the iFood Catalog API
    catalog_api_base:  Base URL (default: https://merchant-api.ifood.com.br)
    merchant_id:       iFood merchant UUID
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import requests
from shopman.offerman.protocols.projection import ProjectedItem, ProjectionResult

if TYPE_CHECKING:
    pass


class IFoodRateLimitError(Exception):
    """Raised when the iFood API responds with 429 Too Many Requests."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"iFood rate limit hit; retry after {retry_after}s")


def _get_config(channel: str = "ifood") -> dict:
    from django.conf import settings
    return getattr(settings, "SHOPMAN_IFOOD", {})


def _item_payload(item: ProjectedItem) -> dict:
    price = round(item.price_q / 100, 2)
    payload: dict = {
        "externalCode": item.sku,
        "name": item.name,
        "description": item.description,
        "price": {
            "value": price,
            "originalValue": price,
        },
        "available": item.is_published and item.is_sellable,
    }
    if item.image_url:
        payload["image"] = {"url": item.image_url}
    if item.category:
        payload["externalCategoryCode"] = item.category
    return payload


def _check_rate_limit(resp: requests.Response) -> None:
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        raise IFoodRateLimitError(retry_after=retry_after)


def _upsert_item(item: ProjectedItem, cfg: dict) -> None:
    base = cfg.get("catalog_api_base", "https://merchant-api.ifood.com.br").rstrip("/")
    merchant_id = cfg["merchant_id"]
    token = cfg["catalog_api_token"]
    url = f"{base}/catalog/v2.0/merchants/{merchant_id}/items/{item.sku}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.put(url, json=_item_payload(item), headers=headers)
    _check_rate_limit(resp)
    resp.raise_for_status()


class IFoodCatalogProjection:
    """Pushes catalog items to the iFood Merchant Catalog API."""

    def project(
        self,
        items: list[ProjectedItem],
        *,
        channel: str,
        full_sync: bool = False,
    ) -> ProjectionResult:
        cfg = _get_config(channel)
        token = cfg.get("catalog_api_token", "")
        if not token:
            return ProjectionResult(
                success=False,
                errors=["catalog_api_token is not configured in SHOPMAN_IFOOD"],
                channel=channel,
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
                errors.append(f"{item.sku}: {exc}")

        return ProjectionResult(
            success=len(errors) == 0,
            projected=projected,
            errors=errors,
            channel=channel,
        )

    def retract(self, skus: list[str], *, channel: str) -> ProjectionResult:
        cfg = _get_config(channel)
        token = cfg.get("catalog_api_token", "")
        if not token:
            return ProjectionResult(
                success=False,
                errors=["catalog_api_token is not configured in SHOPMAN_IFOOD"],
                channel=channel,
            )

        base = cfg.get("catalog_api_base", "https://merchant-api.ifood.com.br").rstrip("/")
        merchant_id = cfg["merchant_id"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        errors: list[str] = []
        retracted = 0
        for sku in skus:
            try:
                url = f"{base}/catalog/v2.0/merchants/{merchant_id}/items/{sku}/unavailable"
                resp = requests.post(url, headers=headers)
                _check_rate_limit(resp)
                resp.raise_for_status()
                retracted += 1
            except IFoodRateLimitError:
                raise
            except Exception as exc:
                errors.append(f"{sku}: {exc}")

        return ProjectionResult(
            success=len(errors) == 0,
            projected=retracted,
            errors=errors,
            channel=channel,
        )
