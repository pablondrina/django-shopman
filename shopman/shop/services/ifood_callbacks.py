"""iFood order status callbacks (WP-4) — push our lifecycle back to iFood.

The merchant must tell iFood how an order progresses. Verified live (routes
exist; a fake id returns ``404 OrderNotFound``):

- ``POST /order/v1.0/orders/{id}/confirm``          → accept the order.
- ``POST /order/v1.0/orders/{id}/readyToPickup``    → order is ready.
- ``POST /order/v1.0/orders/{id}/dispatch``         → order left for delivery.
- ``POST /order/v1.0/orders/{id}/requestCancellation`` → ask iFood to cancel.

Internal ``Order.Status`` → iFood action:

    CONFIRMED  → confirm
    READY      → readyToPickup
    DISPATCHED → dispatch
    CANCELLED  → requestCancellation

⚠️ ``requestCancellation`` requires a ``cancellationCode`` + ``reason`` from
iFood's fixed list, and post-confirmation cancellations may need iFood approval.
The codes must be validated during homologação — the default here is a
placeholder merchant-side code.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

from shopman.shop.services import ifood_auth

logger = logging.getLogger(__name__)


class IFoodCallbackError(Exception):
    """Raised when an iFood status callback fails."""


# Internal status → iFood order-action path segment.
STATUS_ACTION = {
    "confirmed": "confirm",
    "ready": "readyToPickup",
    "dispatched": "dispatch",
    "cancelled": "requestCancellation",
}


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_IFOOD", {}) or {}


def _base_url() -> str:
    return str(_cfg().get("api_base") or "https://merchant-api.ifood.com.br").rstrip("/")


def action_for_status(status: str) -> str | None:
    """Return the iFood action for an internal status, or None if none applies."""
    return STATUS_ACTION.get(str(status or "").lower())


def send_action(order_id: str, action: str, *, body: dict | None = None) -> None:
    """POST a status action to iFood. Raises :class:`IFoodCallbackError` on failure."""
    headers = ifood_auth.authorized_headers({"Content-Type": "application/json"})
    if not headers:
        raise IFoodCallbackError("iFood OAuth is not configured (client_id/client_secret)")

    url = f"{_base_url()}/order/v1.0/orders/{order_id}/{action}"
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=int(_cfg().get("timeout") or 30))
    except requests.RequestException as exc:
        raise IFoodCallbackError(f"iFood {action} request failed: {exc}") from exc

    # iFood returns 202 Accepted for status actions.
    if resp.status_code not in (200, 202):
        raise IFoodCallbackError(
            f"iFood {action} HTTP {resp.status_code}: {resp.text[:200]}"
        )
    logger.info("ifood_callbacks: %s ok for order %s", action, order_id)


def confirm(order_id: str) -> None:
    send_action(order_id, "confirm")


def ready_to_pickup(order_id: str) -> None:
    send_action(order_id, "readyToPickup")


def dispatch(order_id: str) -> None:
    send_action(order_id, "dispatch")


def fetch_cancellation_reasons(order_id: str) -> list[dict]:
    """Fetch the cancellation codes iFood accepts for a specific order.

    ``GET /order/v1.0/orders/{id}/cancellationReasons`` → list of
    ``{"cancelCodeId": "...", "description": "..."}``. Use it to discover the
    valid codes to configure ``cancellation_default_code``.
    """
    headers = ifood_auth.authorized_headers()
    if not headers:
        raise IFoodCallbackError("iFood OAuth is not configured (client_id/client_secret)")
    url = f"{_base_url()}/order/v1.0/orders/{order_id}/cancellationReasons"
    try:
        resp = requests.get(url, headers=headers, timeout=int(_cfg().get("timeout") or 30))
    except requests.RequestException as exc:
        raise IFoodCallbackError(f"iFood cancellationReasons request failed: {exc}") from exc
    if resp.status_code != 200:
        raise IFoodCallbackError(
            f"iFood cancellationReasons HTTP {resp.status_code}: {resp.text[:200]}"
        )
    try:
        reasons = resp.json()
    except ValueError as exc:
        raise IFoodCallbackError("iFood cancellationReasons response was not JSON") from exc
    return reasons if isinstance(reasons, list) else []


def request_cancellation(order_id: str, *, code: str = "", description: str = "") -> None:
    """Ask iFood to cancel an order with a valid cancellation code.

    The code must come from iFood's fixed list (see
    :func:`fetch_cancellation_reasons`). It is config-driven
    (``cancellation_default_code``) rather than guessed — sending a wrong code
    is worse than failing loudly.
    """
    code = str(code or _cfg().get("cancellation_default_code") or "").strip()
    if not code:
        raise IFoodCallbackError(
            "no iFood cancellation code — set SHOPMAN_IFOOD['cancellation_default_code'] "
            "(discover valid codes with fetch_cancellation_reasons)"
        )
    # iFood rejects requestCancellation with 400 when `reason` is empty
    # (verified live 2026-07-01) — it is required alongside the code.
    reason = (
        str(description or "").strip()
        or str(_cfg().get("cancellation_default_reason") or "").strip()
        or "Cancelado pela loja"
    )
    send_action(
        order_id,
        "requestCancellation",
        body={"reason": reason, "cancellationCode": code},
    )


def send_for_status(
    order_id: str,
    status: str,
    *,
    cancellation_reason: str = "",
    cancellation_code: str = "",
) -> bool:
    """Send the callback matching an internal status. Returns False if no action maps."""
    action = action_for_status(status)
    if not action:
        return False
    if action == "requestCancellation":
        request_cancellation(order_id, code=cancellation_code, description=cancellation_reason)
    else:
        send_action(order_id, action)
    return True


__all__ = [
    "confirm",
    "ready_to_pickup",
    "dispatch",
    "request_cancellation",
    "fetch_cancellation_reasons",
    "send_action",
    "send_for_status",
    "action_for_status",
    "STATUS_ACTION",
    "IFoodCallbackError",
]
