"""
Dedicated tests for InsightService.

Covers:
- recalculate: full flow with mock OrderHistoryBackend
- RFM scoring: recency, frequency, monetary at all thresholds
- RFM segmentation: all segment rules
- churn_risk: ratio-based and absolute-days-based
- LTV prediction: with/without frequency data
- recalculate_all: batch processing
- get_segment_customers / get_at_risk_customers
- Edge cases: no backend, no orders, single order
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from shopman.attending.contrib.insights.models import CustomerInsight
from shopman.attending.contrib.insights.service import InsightService
from shopman.attending.models import Customer, CustomerGroup
from shopman.attending.protocols.orders import OrderStats, OrderSummary


@pytest.fixture
def group(db):
    return CustomerGroup.objects.create(ref="regular", name="Regular", is_default=True, priority=0)


@pytest.fixture
def customer(db, group):
    return Customer.objects.create(
        ref="CUST-INS-001",
        first_name="Ana",
        last_name="Pereira",
        email="ana@example.com",
        phone="+5543999880001",
        group=group,
    )


@pytest.fixture
def customer2(db, group):
    return Customer.objects.create(
        ref="CUST-INS-002",
        first_name="Bruno",
        last_name="Costa",
        email="bruno@example.com",
        phone="+5543999880002",
        group=group,
    )


class MockOrderHistoryBackend:
    """In-memory mock for OrderHistoryBackend."""

    def __init__(self, stats=None, orders=None):
        self._stats = stats
        self._orders = orders or []

    def get_order_stats(self, customer_ref: str) -> OrderStats:
        return self._stats

    def get_customer_orders(self, customer_ref: str, limit: int = 10) -> list[OrderSummary]:
        return self._orders[:limit]


# ── Recalculate ──


class TestRecalculate:

    def test_recalculate_happy_path(self, customer, settings):
        """Full recalculate with stats and orders populates all fields."""
        now = datetime.now(timezone.utc)
        stats = OrderStats(
            total_orders=15,
            total_spent_q=500000,
            first_order_at=now - timedelta(days=180),
            last_order_at=now - timedelta(days=5),
            average_order_q=33333,
        )
        orders = [
            OrderSummary(
                order_ref=f"ORD-{i}",
                channel_ref="whatsapp",
                ordered_at=now - timedelta(days=i * 7),
                total_q=33333,
                items_count=3,
                status="completed",
            )
            for i in range(10)
        ]

        backend = MockOrderHistoryBackend(stats=stats, orders=orders)

        settings.ATTENDING = {
            "ORDER_HISTORY_BACKEND": "shopman.attending.tests.test_insights_service.MockOrderHistoryBackend",
        }

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "shopman.attending.contrib.insights.service._get_order_backend",
                lambda: backend,
            )
            insight = InsightService.recalculate(customer.ref)

        assert insight.total_orders == 15
        assert insight.total_spent_q == 500000
        assert insight.average_ticket_q == 33333
        assert insight.days_since_last_order == 5
        assert insight.preferred_weekday is not None
        assert insight.preferred_channel == "whatsapp"
        assert insight.rfm_recency is not None
        assert insight.rfm_frequency is not None
        assert insight.rfm_monetary is not None
        assert insight.rfm_segment != ""
        assert insight.churn_risk is not None
        assert insight.calculation_version == "v2"

    def test_recalculate_no_backend_resets_metrics(self, customer, settings):
        """No ORDER_HISTORY_BACKEND configured → resets to zero."""
        settings.ATTENDING = {}

        insight = InsightService.recalculate(customer.ref)

        assert insight.total_orders == 0
        assert insight.total_spent_q == 0
        assert insight.average_ticket_q == 0

    def test_recalculate_no_orders(self, customer, settings):
        """Backend returns zero stats → insight has zero values."""
        stats = OrderStats(
            total_orders=0,
            total_spent_q=0,
            first_order_at=None,
            last_order_at=None,
            average_order_q=0,
        )
        backend = MockOrderHistoryBackend(stats=stats, orders=[])

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "shopman.attending.contrib.insights.service._get_order_backend",
                lambda: backend,
            )
            insight = InsightService.recalculate(customer.ref)

        assert insight.total_orders == 0
        assert insight.days_since_last_order is None
        assert insight.average_days_between_orders is None

    def test_recalculate_single_order(self, customer, settings):
        """Single order → no average_days_between."""
        now = datetime.now(timezone.utc)
        stats = OrderStats(
            total_orders=1,
            total_spent_q=5000,
            first_order_at=now - timedelta(days=3),
            last_order_at=now - timedelta(days=3),
            average_order_q=5000,
        )
        orders = [
            OrderSummary(
                order_ref="ORD-SINGLE",
                channel_ref="balcao",
                ordered_at=now - timedelta(days=3),
                total_q=5000,
                items_count=2,
                status="completed",
            ),
        ]
        backend = MockOrderHistoryBackend(stats=stats, orders=orders)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "shopman.attending.contrib.insights.service._get_order_backend",
                lambda: backend,
            )
            insight = InsightService.recalculate(customer.ref)

        assert insight.total_orders == 1
        assert insight.average_days_between_orders is None

    def test_recalculate_nonexistent_customer_raises(self, db, settings):
        with pytest.raises(Customer.DoesNotExist):
            InsightService.recalculate("NONEXISTENT")

    def test_recalculate_is_idempotent(self, customer, settings):
        """Calling recalculate twice uses same insight record."""
        stats = OrderStats(
            total_orders=0, total_spent_q=0,
            first_order_at=None, last_order_at=None, average_order_q=0,
        )
        backend = MockOrderHistoryBackend(stats=stats)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "shopman.attending.contrib.insights.service._get_order_backend",
                lambda: backend,
            )
            i1 = InsightService.recalculate(customer.ref)
            i2 = InsightService.recalculate(customer.ref)

        assert i1.pk == i2.pk
        assert CustomerInsight.objects.filter(customer=customer).count() == 1


# ── RFM Scoring ──


class TestRecencyScore:

    def test_7_days_or_less_is_5(self):
        assert InsightService._calculate_recency_score(3) == 5
        assert InsightService._calculate_recency_score(7) == 5

    def test_30_days_is_4(self):
        assert InsightService._calculate_recency_score(15) == 4
        assert InsightService._calculate_recency_score(30) == 4

    def test_90_days_is_3(self):
        assert InsightService._calculate_recency_score(60) == 3
        assert InsightService._calculate_recency_score(90) == 3

    def test_180_days_is_2(self):
        assert InsightService._calculate_recency_score(120) == 2
        assert InsightService._calculate_recency_score(180) == 2

    def test_over_180_days_is_1(self):
        assert InsightService._calculate_recency_score(200) == 1
        assert InsightService._calculate_recency_score(365) == 1

    def test_none_days_is_1(self):
        assert InsightService._calculate_recency_score(None) == 1


class TestFrequencyScore:

    def test_20_plus_orders_is_5(self):
        assert InsightService._calculate_frequency_score(20) == 5
        assert InsightService._calculate_frequency_score(100) == 5

    def test_10_plus_is_4(self):
        assert InsightService._calculate_frequency_score(10) == 4
        assert InsightService._calculate_frequency_score(19) == 4

    def test_5_plus_is_3(self):
        assert InsightService._calculate_frequency_score(5) == 3
        assert InsightService._calculate_frequency_score(9) == 3

    def test_2_plus_is_2(self):
        assert InsightService._calculate_frequency_score(2) == 2
        assert InsightService._calculate_frequency_score(4) == 2

    def test_below_2_is_1(self):
        assert InsightService._calculate_frequency_score(1) == 1
        assert InsightService._calculate_frequency_score(0) == 1


class TestMonetaryScore:

    def test_1m_plus_is_5(self):
        assert InsightService._calculate_monetary_score(1000000) == 5
        assert InsightService._calculate_monetary_score(2000000) == 5

    def test_500k_plus_is_4(self):
        assert InsightService._calculate_monetary_score(500000) == 4
        assert InsightService._calculate_monetary_score(999999) == 4

    def test_200k_plus_is_3(self):
        assert InsightService._calculate_monetary_score(200000) == 3

    def test_50k_plus_is_2(self):
        assert InsightService._calculate_monetary_score(50000) == 2

    def test_below_50k_is_1(self):
        assert InsightService._calculate_monetary_score(49999) == 1
        assert InsightService._calculate_monetary_score(0) == 1


# ── RFM Segment ──


class TestRFMSegment:

    def test_champion_high_score(self):
        # r=5 + f=5 + m=5 = 15 >= 13
        assert InsightService._calculate_rfm_segment(5, 5, 5) == "champion"
        assert InsightService._calculate_rfm_segment(5, 4, 4) == "champion"

    def test_loyal_customer(self):
        # r>=4 and f>=3
        assert InsightService._calculate_rfm_segment(4, 3, 2) == "loyal_customer"

    def test_recent_customer(self):
        # r>=4 and f<=2
        assert InsightService._calculate_rfm_segment(4, 2, 1) == "recent_customer"
        assert InsightService._calculate_rfm_segment(5, 1, 1) == "recent_customer"

    def test_at_risk(self):
        # r<=2 and f>=3
        assert InsightService._calculate_rfm_segment(2, 3, 2) == "at_risk"
        assert InsightService._calculate_rfm_segment(1, 4, 1) == "at_risk"

    def test_lost(self):
        # r<=2 and f<=2
        assert InsightService._calculate_rfm_segment(1, 1, 1) == "lost"
        assert InsightService._calculate_rfm_segment(2, 2, 1) == "lost"

    def test_regular(self):
        # None of the above
        assert InsightService._calculate_rfm_segment(3, 2, 3) == "regular"
        assert InsightService._calculate_rfm_segment(3, 3, 2) == "regular"


# ── Churn Risk ──


class TestChurnRisk:

    def test_no_history_returns_05(self):
        assert InsightService._calculate_churn_risk(None, None) == Decimal("0.5")

    def test_ratio_over_3_returns_09(self):
        # 100 days / 30 avg = 3.33 > 3
        assert InsightService._calculate_churn_risk(100, Decimal("30")) == Decimal("0.9")

    def test_ratio_over_2_returns_07(self):
        # 70 / 30 = 2.33 > 2
        assert InsightService._calculate_churn_risk(70, Decimal("30")) == Decimal("0.7")

    def test_ratio_over_15_returns_04(self):
        # 50 / 30 = 1.67 > 1.5
        assert InsightService._calculate_churn_risk(50, Decimal("30")) == Decimal("0.4")

    def test_ratio_normal_returns_01(self):
        # 10 / 30 = 0.33 <= 1.5
        assert InsightService._calculate_churn_risk(10, Decimal("30")) == Decimal("0.1")

    def test_absolute_over_90_returns_08(self):
        # No avg_days, 91 days
        assert InsightService._calculate_churn_risk(91, None) == Decimal("0.8")

    def test_absolute_over_60_returns_05(self):
        assert InsightService._calculate_churn_risk(61, None) == Decimal("0.5")

    def test_absolute_over_30_returns_03(self):
        assert InsightService._calculate_churn_risk(31, None) == Decimal("0.3")

    def test_absolute_under_30_returns_01(self):
        assert InsightService._calculate_churn_risk(10, None) == Decimal("0.1")

    def test_zero_avg_days_uses_absolute(self):
        # avg_days=0 → treated as no avg
        assert InsightService._calculate_churn_risk(91, Decimal("0")) == Decimal("0.8")


# ── LTV ──


class TestLTV:

    def test_ltv_with_frequency(self):
        # avg_ticket=5000, avg_days=7 → 365/7 = 52.14 → 5000*52.14 = 260714
        result = InsightService._calculate_ltv(5000, Decimal("7"), 10)
        assert result == int(5000 * Decimal("365") / 7)

    def test_ltv_fallback_total_orders(self):
        # No avg_days, total_orders>=2 → avg_ticket * total_orders * 2
        result = InsightService._calculate_ltv(5000, None, 5)
        assert result == 5000 * 5 * 2

    def test_ltv_no_data_returns_none(self):
        # No avg_days, single order → None
        result = InsightService._calculate_ltv(5000, None, 1)
        assert result is None

    def test_ltv_zero_ticket_returns_zero(self):
        result = InsightService._calculate_ltv(0, Decimal("7"), 10)
        assert result == 0


# ── Recalculate All ──


class TestRecalculateAll:

    def test_recalculate_all_processes_all_customers(self, customer, customer2, settings):
        """recalculate_all processes all active customers."""
        settings.ATTENDING = {}  # No backend → reset metrics

        count = InsightService.recalculate_all()

        assert count == 2
        assert CustomerInsight.objects.count() == 2

    def test_recalculate_all_skips_inactive(self, customer, settings):
        """Inactive customers are skipped."""
        customer.is_active = False
        customer.save()
        settings.ATTENDING = {}

        count = InsightService.recalculate_all()

        assert count == 0


# ── Query Methods ──


class TestGetInsight:

    def test_get_insight_returns_insight(self, customer):
        insight = CustomerInsight.objects.create(
            customer=customer, total_orders=5, rfm_segment="loyal_customer",
        )

        result = InsightService.get_insight(customer.ref)
        assert result is not None
        assert result.pk == insight.pk

    def test_get_insight_not_found_returns_none(self, customer):
        result = InsightService.get_insight(customer.ref)
        assert result is None


class TestSegmentQueries:

    def test_get_segment_customers(self, customer, customer2):
        CustomerInsight.objects.create(
            customer=customer, rfm_segment="champion", total_orders=20,
        )
        CustomerInsight.objects.create(
            customer=customer2, rfm_segment="lost", total_orders=1,
        )

        champions = InsightService.get_segment_customers("champion")
        assert len(champions) == 1
        assert champions[0].customer.ref == customer.ref

    def test_get_at_risk_customers(self, customer, customer2):
        CustomerInsight.objects.create(
            customer=customer, churn_risk=Decimal("0.9"), rfm_segment="at_risk",
        )
        CustomerInsight.objects.create(
            customer=customer2, churn_risk=Decimal("0.2"), rfm_segment="loyal_customer",
        )

        at_risk = InsightService.get_at_risk_customers()
        assert len(at_risk) == 1
        assert at_risk[0].customer.ref == customer.ref

    def test_get_at_risk_custom_threshold(self, customer):
        CustomerInsight.objects.create(
            customer=customer, churn_risk=Decimal("0.5"), rfm_segment="regular",
        )

        # Default threshold 0.7 → not found
        assert len(InsightService.get_at_risk_customers()) == 0

        # Custom threshold 0.4 → found
        assert len(InsightService.get_at_risk_customers(min_churn_risk=Decimal("0.4"))) == 1


# ── Model Properties ──


class TestCustomerInsightProperties:

    def test_total_spent_decimal(self, customer):
        insight = CustomerInsight.objects.create(
            customer=customer, total_spent_q=250050,
        )
        assert insight.total_spent == Decimal("2500.50")

    def test_average_ticket_decimal(self, customer):
        insight = CustomerInsight.objects.create(
            customer=customer, average_ticket_q=3350,
        )
        assert insight.average_ticket == Decimal("33.50")

    def test_is_vip_champion(self, customer):
        insight = CustomerInsight.objects.create(
            customer=customer, rfm_segment="champion",
        )
        assert insight.is_vip is True

    def test_is_vip_loyal_customer(self, customer):
        insight = CustomerInsight.objects.create(
            customer=customer, rfm_segment="loyal_customer",
        )
        assert insight.is_vip is True

    def test_is_vip_regular_is_false(self, customer):
        insight = CustomerInsight.objects.create(
            customer=customer, rfm_segment="regular",
        )
        assert insight.is_vip is False

    def test_is_at_risk_high_churn(self, customer):
        insight = CustomerInsight.objects.create(
            customer=customer, churn_risk=Decimal("0.8"),
        )
        assert insight.is_at_risk is True

    def test_is_at_risk_low_churn(self, customer):
        insight = CustomerInsight.objects.create(
            customer=customer, churn_risk=Decimal("0.3"),
        )
        assert insight.is_at_risk is False

    def test_is_at_risk_none_churn(self, customer):
        insight = CustomerInsight.objects.create(
            customer=customer, churn_risk=None,
        )
        assert insight.is_at_risk is False
