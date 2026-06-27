"""
Inventory availability backend — answers Craftsman's read-only InventoryProtocol
via Stockman (Buyman WP-B5b).

Craftsman's ingredient-availability guardrails (over-plan on adjust, missing-on-
finish, shortage status on suggestions) are dormant until CRAFTSMAN["INVENTORY_BACKEND"]
points here. It only READS: for each MaterialNeed it asks Stockman how much of that
sku is on hand. The stock ledger is written elsewhere (signal-path). Lazy imports
keep the module loadable without Stockman/Craftsman (ADR-001).
"""

from __future__ import annotations


class InventoryAvailabilityBackend:
    """Read-only ingredient availability over Stockman (InventoryProtocol)."""

    def available(self, materials):
        from shopman.craftsman.protocols.inventory import AvailabilityResult, MaterialStatus
        from shopman.stockman import stock

        items = []
        all_available = True
        for need in materials:
            on_hand = stock.available(need.sku)
            if on_hand < need.quantity:
                all_available = False
            items.append(
                MaterialStatus(sku=need.sku, needed=need.quantity, available=on_hand)
            )
        return AvailabilityResult(all_available=all_available, materials=items)
