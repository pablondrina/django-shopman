"""
Crafting Demand Backend — Ordering integration.

Add 'shopman.crafting.contrib.demand' to INSTALLED_APPS to enable:
- OrderingDemandBackend implementing DemandProtocol
- Production suggestions based on historical order data

Configure via settings:
    CRAFTING = {
        "DEMAND_BACKEND": "shopman.crafting.contrib.demand.backend.OrderingDemandBackend",
    }
"""
