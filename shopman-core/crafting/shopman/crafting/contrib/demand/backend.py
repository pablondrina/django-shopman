"""
OmnimanDemandBackend — DemandProtocol implementation.

Queries Omniman OrderItems for historical demand and Stocking Holds
for committed quantities.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from shopman.crafting.protocols.demand import DailyDemand

logger = logging.getLogger(__name__)


class OmnimanDemandBackend:
    """
    DemandProtocol implementation backed by Omniman orders.

    history() → queries OrderItems from completed/delivered orders.
    committed() → sums active Holds from Stocking for a given SKU+date.
    """

    # Order statuses that represent fulfilled demand
    DEMAND_STATUSES = ("completed", "delivered")

    def history(
        self,
        product_ref: str,
        days: int = 28,
        same_weekday: bool = True,
    ) -> list[DailyDemand]:
        """
        Return historical demand for a product based on Omniman orders.

        Queries OrderItems where sku matches product_ref, from orders
        with status completed or delivered, grouped by date.
        """
        from omniman.models import OrderItem

        cutoff = timezone.now().date() - timedelta(days=days)
        today = timezone.now().date()

        qs = OrderItem.objects.filter(
            sku=product_ref,
            order__status__in=self.DEMAND_STATUSES,
            order__created_at__date__gte=cutoff,
            order__created_at__date__lt=today,
        )

        if same_weekday:
            target_weekday = today.weekday()
            qs = qs.filter(order__created_at__week_day=_django_weekday(target_weekday))

        daily = (
            qs.annotate(order_date=TruncDate("order__created_at"))
            .values("order_date")
            .annotate(total_sold=Coalesce(Sum("qty"), Decimal("0")))
            .order_by("order_date")
        )

        return [
            DailyDemand(
                date=row["order_date"],
                sold=row["total_sold"],
                wasted=Decimal("0"),
            )
            for row in daily
        ]

    def committed(self, product_ref: str, target_date: date) -> Decimal:
        """
        Return total committed quantity from Stocking Holds.

        Includes both reservation holds (quant set) and demand holds
        (quant=None, e.g. preorders) — any active hold for the given
        SKU and target_date counts as committed demand.

        Graceful: returns 0 if Stocking is not installed.
        """
        try:
            from shopman.stocking.models.hold import Hold

            total = (
                Hold.objects.filter(
                    sku=product_ref,
                    target_date=target_date,
                )
                .active()
                .aggregate(t=Coalesce(Sum("quantity"), Decimal("0")))["t"]
            )
            return total
        except ImportError:
            logger.debug("Stocking not available, committed() returning 0")
            return Decimal("0")
        except Exception:
            logger.warning(
                "Failed to query Stocking holds for %s on %s, returning 0",
                product_ref,
                target_date,
                exc_info=True,
            )
            return Decimal("0")


def _django_weekday(python_weekday: int) -> int:
    """
    Convert Python weekday (0=Monday) to Django __week_day (1=Sunday, 2=Monday, ..., 7=Saturday).
    """
    return (python_weekday + 2) % 7 or 7


def _sku_lookup(sku: str):
    """
    Build a Q filter to find Holds for a given SKU.

    Stocking uses GenericForeignKey, so we need to resolve via
    the Product model's content type.
    """
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import Q

    try:
        from shopman.offering.models import Product

        ct = ContentType.objects.get_for_model(Product)
        product_ids = Product.objects.filter(sku=sku).values_list("pk", flat=True)
        return Q(quant__content_type=ct, quant__object_id__in=product_ids)
    except ImportError:
        return Q(pk__in=[])
