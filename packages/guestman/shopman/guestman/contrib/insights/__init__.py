"""
Guestman Insights - Customer analytics and RFM segmentation.

This contrib module provides CustomerInsight for calculated metrics,
RFM scoring, and churn prediction.

Usage:
    INSTALLED_APPS = [
        ...
        "customers",
        guestman.contrib.insights",
    ]

    from shopman.guestman.contrib.insights import InsightService

    insight = InsightService.get_insight(customer_ref)
    InsightService.recalculate(customer_ref)
"""


def __getattr__(name):
    if name == "InsightService":
        from shopman.guestman.contrib.insights.service import InsightService

        return InsightService
    if name == "CustomerInsight":
        from shopman.guestman.contrib.insights.models import CustomerInsight

        return CustomerInsight
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["InsightService", "CustomerInsight"]
