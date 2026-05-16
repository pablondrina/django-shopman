"""Small helpers for API-facing SurfaceAction payloads."""

from __future__ import annotations

from typing import Any

from shopman.shop.projections.types import SurfaceActionProjection

from .projections import projection_data


def action_payload(
    *,
    ref: str,
    kind: str,
    label: str,
    priority: str = "secondary",
    enabled: bool = True,
    reason: str = "",
    href: str = "",
    method: str = "",
    payload_schema: dict[str, Any] | None = None,
    idempotency: str = "none",
    confirmation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return projection_data(SurfaceActionProjection(
        ref=ref,
        kind=kind,
        label=label,
        priority=priority,
        enabled=enabled,
        reason=reason,
        href=href,
        method=method,
        payload_schema=payload_schema or {},
        idempotency=idempotency,
        confirmation=confirmation or {},
    ))


def retry_after_action(retry_after_seconds: int) -> dict[str, Any]:
    return action_payload(
        ref="retry_after",
        kind="instruction",
        label="Tentar novamente",
        priority="secondary",
        enabled=False,
        reason=f"Aguarde {retry_after_seconds} segundos antes de tentar novamente.",
    )
