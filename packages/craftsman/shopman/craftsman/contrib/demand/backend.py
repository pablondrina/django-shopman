"""
OrderingDemandBackend — DemandProtocol implementation.

Queries Orderman OrderItems for historical demand and Stockman Holds
for committed quantities.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from shopman.craftsman.protocols.demand import DailyDemand

logger = logging.getLogger(__name__)


class OrderingDemandBackend:
    """
    DemandProtocol implementation backed by Orderman orders.

    history() → queries OrderItems from completed/delivered orders.
    committed() → sums active Holds from Stockman for a given SKU+date.
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
        Return historical demand for a product based on Orderman orders.

        Queries OrderItems where sku matches product_ref, from orders
        with status completed or delivered, grouped by date.
        """
        from shopman.orderman.models import OrderItem

        # localdate(), não now().date(): sob USE_TZ, os lookups de ORM abaixo
        # (__date, __week_day) extraem o dia convertendo created_at para
        # settings.TIME_ZONE. now().date() devolve o dia em UTC — as duas noções
        # de "hoje" divergem na janela 00:00–03:00 UTC (fim de tarde/noite no
        # Brasil, justo quando a produção é planejada), e o filtro same_weekday
        # passa a caçar o dia da semana errado, zerando o histórico. localdate()
        # casa com o fuso usado pelos lookups.
        cutoff = timezone.localdate() - timedelta(days=days)
        today = timezone.localdate()

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

        # Build waste map from WorkOrderItem (kind=waste) — same date range
        waste_by_date: dict = {}
        try:
            from shopman.craftsman.models import WorkOrderItem

            waste_qs = (
                WorkOrderItem.objects.filter(
                    kind=WorkOrderItem.Kind.WASTE,
                    item_ref=product_ref,
                    work_order__target_date__gte=cutoff,
                    work_order__target_date__lt=today,
                )
                .values("work_order__target_date")
                .annotate(total_wasted=Coalesce(Sum("quantity"), Decimal("0")))
            )
            if same_weekday:
                waste_by_date = {
                    row["work_order__target_date"]: row["total_wasted"]
                    for row in waste_qs
                    if row["work_order__target_date"].weekday() == today.weekday()
                }
            else:
                waste_by_date = {
                    row["work_order__target_date"]: row["total_wasted"]
                    for row in waste_qs
                }
        except Exception:
            # Graceful — waste fica zero se o modelo não estiver disponível,
            # mas a degradação precisa ficar visível no log.
            logger.debug(
                "waste map indisponível para %s; demanda segue com waste=0",
                product_ref,
                exc_info=True,
            )

        return [
            DailyDemand(
                date=row["order_date"],
                sold=row["total_sold"],
                wasted=waste_by_date.get(row["order_date"], Decimal("0")),
            )
            for row in daily
        ]

    def committed(self, product_ref: str, target_date: date) -> Decimal:
        """
        Return total committed quantity from Stockman Holds.

        Includes both reservation holds (quant set) and demand holds
        (quant=None, e.g. preorders) — any active hold for the given
        SKU and target_date counts as committed demand.

        Graceful: returns 0 if Stockman is not installed.
        """
        try:
            from shopman.stockman.models.hold import Hold

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
            logger.debug("Stockman not available, committed() returning 0")
            return Decimal("0")
        except Exception:
            logger.warning(
                "Failed to query Stockman holds for %s on %s, returning 0",
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

    Stockman uses GenericForeignKey, so we need to resolve via
    the Product model's content type.
    """
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import Q

    try:
        from shopman.offerman.models import Product

        ct = ContentType.objects.get_for_model(Product)
        product_ids = Product.objects.filter(sku=sku).values_list("pk", flat=True)
        return Q(quant__content_type=ct, quant__object_id__in=product_ids)
    except ImportError:
        return Q(pk__in=[])
