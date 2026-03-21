"""
DirectiveHandler for stock.hold — creates stock holds for order items.

Registered in orchestration.py via ``register_stock_extensions()``.
Processed by the ordering dispatch system (at-least-once).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from shopman.stocking import stock, StockError

logger = logging.getLogger("shopman.contrib.stock")


class StockHoldHandler:
    """
    Processes ``stock.hold`` directives after commit.

    Payload (from CommitService):
        - order_ref: str
        - channel_ref: str
        - session_key: str
        - rev: int
        - items: list[{sku, qty}]

    For each item, creates a hold via ``stock.hold()``.
    Idempotent: skips items that already have a hold recorded in the
    directive's own payload (``result.holds``).
    """

    topic = "stock.hold"

    def handle(self, *, message, ctx):
        payload = message.payload
        items = payload.get("items", [])
        order_ref = payload.get("order_ref", "?")

        if not items:
            logger.warning("stock.hold: no items in directive for order %s", order_ref)
            return

        # Already-processed holds (idempotency on retry)
        existing = {h["sku"] for h in payload.get("result", {}).get("holds", [])}

        holds = list(payload.get("result", {}).get("holds", []))

        # Compute TTL from channel config if available
        expires_at = self._compute_expires_at(payload)

        for item in items:
            sku = item["sku"]
            if sku in existing:
                logger.debug("stock.hold: skipping %s (already held) for order %s", sku, order_ref)
                continue

            qty = Decimal(str(item["qty"]))

            try:
                hold_id = stock.hold(
                    qty,
                    _SkuRef(sku),
                    expires_at=expires_at,
                    order_ref=order_ref,
                )
                holds.append({"hold_id": hold_id, "sku": sku, "qty": str(qty)})
                logger.info(
                    "stock.hold: created %s for sku=%s qty=%s order=%s",
                    hold_id, sku, qty, order_ref,
                )
            except StockError as exc:
                logger.error(
                    "stock.hold: failed for sku=%s qty=%s order=%s — %s",
                    sku, qty, order_ref, exc,
                )
                raise

        # Persist holds result into directive payload for idempotency
        if not payload.get("result"):
            payload["result"] = {}
        payload["result"]["holds"] = holds
        message.payload = payload
        message.save(update_fields=["payload"])

    @staticmethod
    def _compute_expires_at(payload):
        """Derive hold expiration from channel stock config, if available."""
        # The channel config is not directly in the payload, but the
        # orchestration layer can inject ttl. For now, no TTL by default.
        ttl = payload.get("stock_hold_ttl")
        if ttl:
            return timezone.now() + timedelta(seconds=int(ttl))
        return None


class _SkuRef:
    """Minimal product-like object for stock.hold() — just carries a sku."""

    __slots__ = ("sku",)

    def __init__(self, sku: str):
        self.sku = sku
