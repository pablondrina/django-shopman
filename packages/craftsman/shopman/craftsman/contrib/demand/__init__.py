"""
Crafting Demand Backend — Ordering integration.

Add 'shopman.craftsman.contrib.demand' to INSTALLED_APPS to enable:
- OrderingDemandBackend implementing DemandProtocol
- Production suggestions based on historical order data

Configure via settings:
    CRAFTING = {
        "DEMAND_BACKEND": "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend",
    }
"""
