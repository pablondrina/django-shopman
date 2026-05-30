"""Internal interaction context for projection builders and surface adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InteractionContext:
    """Normalized context for resolving projections without creating a control plane."""

    channel_ref: str
    surface_ref: str
    customer_ref: str = ""
    session_key: str = ""
    order_ref: str = ""
    phone: str = ""
    timezone: str = ""
    locale: str = ""
    device: str = ""
    viewport: str = ""
    origin: str = ""
    handoff: str = ""
    target_kind: str = ""
    target_ref: str = ""
    is_authenticated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_request(
        cls,
        request: Any | None,
        *,
        channel_ref: str,
        surface_ref: str,
        target_kind: str = "",
        target_ref: str = "",
    ) -> InteractionContext:
        customer = getattr(request, "customer", None) if request is not None else None
        session = getattr(request, "session", None) if request is not None else None
        headers = getattr(request, "headers", {}) if request is not None else {}
        meta = getattr(request, "META", {}) if request is not None else {}

        return cls(
            channel_ref=channel_ref,
            surface_ref=surface_ref,
            customer_ref=str(getattr(customer, "ref", "") or ""),
            session_key=str(getattr(session, "session_key", "") or ""),
            order_ref=target_ref if target_kind == "order" else "",
            phone=str(getattr(customer, "phone", "") or ""),
            timezone=str(getattr(customer, "timezone", "") or ""),
            locale=str(headers.get("Accept-Language", "") or ""),
            device=str(headers.get("User-Agent", "") or "")[:160],
            viewport=str(headers.get("Viewport-Width", "") or ""),
            origin=str(headers.get("Referer", "") or ""),
            handoff=str(headers.get("X-Shopman-Handoff", "") or ""),
            target_kind=target_kind,
            target_ref=target_ref,
            is_authenticated=bool(customer),
            metadata={
                "ip": str(meta.get("REMOTE_ADDR", "") or ""),
                "path": str(getattr(request, "path", "") or ""),
            },
        )

    @classmethod
    def from_order(
        cls,
        order: Any,
        *,
        surface_ref: str,
        channel_ref: str | None = None,
    ) -> InteractionContext:
        data = getattr(order, "data", None) or {}
        customer = data.get("customer") if isinstance(data, dict) else {}
        customer_ref = ""
        phone = ""
        if isinstance(customer, dict):
            customer_ref = str(customer.get("ref") or customer.get("customer_ref") or "")
            phone = str(customer.get("phone") or "")

        return cls(
            channel_ref=channel_ref or str(getattr(order, "channel_ref", "") or ""),
            surface_ref=surface_ref,
            customer_ref=customer_ref,
            order_ref=str(getattr(order, "ref", "") or ""),
            phone=phone,
            target_kind="order",
            target_ref=str(getattr(order, "ref", "") or ""),
            is_authenticated=bool(customer_ref or phone),
        )
