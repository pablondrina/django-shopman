"""
Customers Insights - Customer analytics and RFM segmentation.

This contrib module provides CustomerInsight for calculated metrics,
RFM scoring, and churn prediction.

Usage:
    INSTALLED_APPS = [
        ...
        "customers",
        "customers.contrib.insights",
    ]

    from shopman.customers.contrib.insights import InsightService

    insight = InsightService.get_insight(customer_ref)
    InsightService.recalculate(customer_ref)
"""


def __getattr__(name):
    if name == "InsightService":
        from shopman.customers.contrib.insights.service import InsightService

        return InsightService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["InsightService"]
