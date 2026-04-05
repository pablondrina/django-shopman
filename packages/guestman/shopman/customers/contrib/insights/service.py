"""Insight service for calculation and retrieval."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from collections import Counter

from django.conf import settings
from django.utils.module_loading import import_string

from shopman.customers.contrib.insights.models import CustomerInsight
from shopman.customers.models import Customer
from shopman.customers.protocols.orders import OrderHistoryBackend

logger = logging.getLogger(__name__)


def _get_order_backend() -> OrderHistoryBackend | None:
    """Get configured OrderHistoryBackend."""
    customers_settings = getattr(settings, "ATTENDING", {})
    backend_path = customers_settings.get("ORDER_HISTORY_BACKEND")
    if backend_path:
        backend_class = import_string(backend_path)
        return backend_class()
    return None


class InsightService:
    """
    Service for customer insight operations.

    Uses @classmethod for extensibility (see spec 000 section 12.1).
    """

    @classmethod
    def get_insight(cls, customer_ref: str) -> CustomerInsight | None:
        """
        Get insight for customer.

        Args:
            customer_ref: Customer ref

        Returns:
            CustomerInsight or None
        """
        try:
            return CustomerInsight.objects.select_related("customer").get(
                customer__ref=customer_ref,
                customer__is_active=True,
            )
        except CustomerInsight.DoesNotExist:
            return None

    @classmethod
    def recalculate(cls, customer_ref: str) -> CustomerInsight:
        """
        Recalculate insights for customer using OrderHistoryBackend.

        Args:
            customer_ref: Customer ref

        Returns:
            Updated CustomerInsight

        Raises:
            Customer.DoesNotExist: If customer not found
        """
        customer = Customer.objects.get(ref=customer_ref, is_active=True)

        # Get or create insight
        insight, _ = CustomerInsight.objects.get_or_create(customer=customer)

        # Get order backend
        backend = _get_order_backend()
        if not backend:
            # No backend configured - reset metrics
            insight.total_orders = 0
            insight.total_spent_q = 0
            insight.average_ticket_q = 0
            insight.save()
            return insight

        # Get stats from backend
        stats = backend.get_order_stats(customer_ref)

        # Update basic metrics
        insight.total_orders = stats.total_orders
        insight.total_spent_q = stats.total_spent_q
        insight.average_ticket_q = stats.average_order_q
        insight.first_order_at = stats.first_order_at
        insight.last_order_at = stats.last_order_at

        # Calculate days since last order
        if stats.last_order_at:
            delta = datetime.now(timezone.utc) - stats.last_order_at
            insight.days_since_last_order = delta.days
        else:
            insight.days_since_last_order = None

        # Calculate average days between orders
        if stats.total_orders > 1 and stats.first_order_at and stats.last_order_at:
            total_days = (stats.last_order_at - stats.first_order_at).days
            insight.average_days_between_orders = Decimal(
                total_days / (stats.total_orders - 1)
            )
        else:
            insight.average_days_between_orders = None

        # Get recent orders for pattern analysis
        orders = backend.get_customer_orders(customer_ref, limit=50)

        if orders:
            # Preferred weekday (0=Monday, 6=Sunday)
            weekdays = [o.ordered_at.weekday() for o in orders]
            insight.preferred_weekday = Counter(weekdays).most_common(1)[0][0]

            # Preferred hour
            hours = [o.ordered_at.hour for o in orders]
            insight.preferred_hour = Counter(hours).most_common(1)[0][0]

            # Channels used
            channels = list(set(o.channel_ref for o in orders))
            insight.channels_used = channels

            # Preferred channel
            channel_counts = Counter(o.channel_ref for o in orders)
            insight.preferred_channel = channel_counts.most_common(1)[0][0]

        # Calculate RFM scores
        insight.rfm_recency = cls._calculate_recency_score(
            insight.days_since_last_order
        )
        insight.rfm_frequency = cls._calculate_frequency_score(insight.total_orders)
        insight.rfm_monetary = cls._calculate_monetary_score(insight.total_spent_q)
        insight.rfm_segment = cls._calculate_rfm_segment(
            insight.rfm_recency,
            insight.rfm_frequency,
            insight.rfm_monetary,
        )

        # Churn risk
        insight.churn_risk = cls._calculate_churn_risk(
            insight.days_since_last_order,
            insight.average_days_between_orders,
        )

        # Predicted LTV (simple: avg_ticket * projected_orders_per_year)
        insight.predicted_ltv_q = cls._calculate_ltv(
            insight.average_ticket_q,
            insight.average_days_between_orders,
            insight.total_orders,
        )

        insight.calculation_version = "v2"
        insight.save()

        return insight

    @classmethod
    def recalculate_all(cls) -> int:
        """
        Recalculate insights for all active customers.

        Uses iterator() to avoid loading all customers into memory.

        Returns:
            Number of customers processed
        """
        count = 0
        for customer in Customer.objects.filter(is_active=True).only("ref").iterator(chunk_size=500):
            try:
                cls.recalculate(customer.ref)
                count += 1
            except (ValueError, TypeError, LookupError) as exc:
                logger.warning("recalculate_all: skipped customer %s: %s", customer.ref, exc)
        return count

    # ======================================================================
    # RFM Calculation Helpers
    # ======================================================================

    @classmethod
    def _calculate_recency_score(cls, days: int | None) -> int:
        """Calculate RFM Recency score (1-5)."""
        from shopman.customers.contrib.insights.conf import get_recency_thresholds

        if days is None:
            return 1
        for threshold, score in get_recency_thresholds():
            if days <= threshold:
                return score
        return 1

    @classmethod
    def _calculate_frequency_score(cls, orders: int) -> int:
        """Calculate RFM Frequency score (1-5)."""
        from shopman.customers.contrib.insights.conf import get_frequency_thresholds

        for threshold, score in get_frequency_thresholds():
            if orders >= threshold:
                return score
        return 1

    @classmethod
    def _calculate_monetary_score(cls, total_q: int) -> int:
        """Calculate RFM Monetary score (1-5)."""
        from shopman.customers.contrib.insights.conf import get_monetary_thresholds

        for threshold, score in get_monetary_thresholds():
            if total_q >= threshold:
                return score
        return 1

    @classmethod
    def _calculate_rfm_segment(cls, r: int, f: int, m: int) -> str:
        """Determine RFM segment."""
        score = r + f + m

        if score >= 13:
            return "champion"
        if r >= 4 and f >= 3:
            return "loyal_customer"
        if r >= 4 and f <= 2:
            return "recent_customer"
        if r <= 2 and f >= 3:
            return "at_risk"
        if r <= 2 and f <= 2:
            return "lost"
        return "regular"

    @classmethod
    def _calculate_ltv(
        cls,
        avg_ticket_q: int,
        avg_days_between: Decimal | None,
        total_orders: int,
    ) -> int | None:
        """
        Predict 12-month LTV using simple frequency projection.

        Formula: avg_ticket * (365 / avg_days_between_orders)
        Falls back to historical average if frequency unknown.
        """
        if avg_ticket_q <= 0:
            return 0

        if avg_days_between and avg_days_between > 0:
            orders_per_year = Decimal("365") / avg_days_between
            return int(avg_ticket_q * orders_per_year)

        # Fallback: extrapolate from total orders if we have history
        if total_orders >= 2:
            return avg_ticket_q * total_orders * 2
        return None

    @classmethod
    def get_segment_customers(
        cls,
        segment: str,
        limit: int = 100,
    ) -> list[CustomerInsight]:
        """
        Get customers by RFM segment for behavior-based segmentation.

        Args:
            segment: RFM segment (champion, loyal_customer, recent_customer,
                     at_risk, lost, regular)
            limit: Max results

        Returns:
            List of CustomerInsight with customer pre-loaded
        """
        return list(
            CustomerInsight.objects.filter(
                rfm_segment=segment,
                customer__is_active=True,
            )
            .select_related("customer")[:limit]
        )

    @classmethod
    def get_at_risk_customers(cls, min_churn_risk: Decimal = Decimal("0.7")) -> list[CustomerInsight]:
        """Get customers with high churn risk for retention campaigns."""
        return list(
            CustomerInsight.objects.filter(
                churn_risk__gte=min_churn_risk,
                customer__is_active=True,
            )
            .select_related("customer")
            .order_by("-churn_risk")
        )

    @classmethod
    def _calculate_churn_risk(
        cls,
        days_since: int | None,
        avg_days: Decimal | None,
    ) -> Decimal:
        """Calculate simplified churn risk."""
        if days_since is None:
            return Decimal("0.5")

        if avg_days and avg_days > 0:
            ratio = Decimal(days_since) / avg_days
            if ratio > 3:
                return Decimal("0.9")
            if ratio > 2:
                return Decimal("0.7")
            if ratio > 1.5:
                return Decimal("0.4")
            return Decimal("0.1")

        # No history, use absolute days
        if days_since > 90:
            return Decimal("0.8")
        if days_since > 60:
            return Decimal("0.5")
        if days_since > 30:
            return Decimal("0.3")
        return Decimal("0.1")
