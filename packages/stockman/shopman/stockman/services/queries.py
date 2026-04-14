"""
Stock queries — read-only operations.

All methods are classmethod on Stock and use no locking.
"""

from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

from shopman.stockman.models.hold import Hold
from shopman.stockman.models.position import Position
from shopman.stockman.models.quant import Quant
from shopman.stockman.shelflife import filter_valid_quants


def _resolve_stock_profile(sku_or_product):
    """Resolve sku + stock profile from either a product-like object or the catalog contract."""
    from shopman.stockman.adapters.sku_validation import get_sku_validator

    sku = sku_or_product if isinstance(sku_or_product, str) else sku_or_product.sku
    shelflife = getattr(sku_or_product, "shelflife", None) if not isinstance(sku_or_product, str) else None
    availability_policy = (
        getattr(sku_or_product, "availability_policy", None)
        if not isinstance(sku_or_product, str)
        else None
    )

    if shelflife is None or availability_policy is None:
        info = get_sku_validator().get_sku_info(sku)
        if info is not None:
            if shelflife is None:
                shelflife = info.shelflife_days
            if availability_policy is None:
                availability_policy = info.availability_policy

    return {
        "sku": sku,
        "shelflife": shelflife,
        "availability_policy": availability_policy or "planned_ok",
    }


class StockQueries:
    """Read-only stock query methods."""

    @classmethod
    def available(cls, sku_or_product, target_date: date | None = None,
                  position: Position | None = None, *,
                  product=None) -> Decimal:
        """
        Available quantity for sale/hold.

        available = valid_quantity - active_holds

        Args:
            sku_or_product: SKU string or product object (for backwards compat).
                           If product object, its .sku is used.
            target_date: Desired date (None = today)
            position: Specific position (None = all)
            product: Product object for shelflife filtering (optional).
                    If sku_or_product is a product object, it's used directly.

        Returns:
            Decimal with available quantity
        """
        target = target_date or date.today()

        # Support both sku string and product object
        profile = _resolve_stock_profile(sku_or_product)
        sku = profile["sku"]
        if product is None:
            product = sku_or_product if not isinstance(sku_or_product, str) else None
        if product is None and profile["shelflife"] is not None:
            from types import SimpleNamespace

            product = SimpleNamespace(
                sku=sku,
                shelflife=profile["shelflife"],
                availability_policy=profile["availability_policy"],
            )

        quants = Quant.objects.filter(sku=sku)

        if position:
            quants = quants.filter(position=position)

        if product is not None:
            quants = filter_valid_quants(quants, product, target)
        else:
            # No product for shelflife — include physical + up to target date
            quants = quants.filter(
                Q(target_date__isnull=True) | Q(target_date__lte=target)
            )

        total = quants.aggregate(
            t=Coalesce(Sum('_quantity'), Decimal('0'))
        )['t']

        held_qs = Hold.objects.filter(
            sku=sku,
            target_date=target,
        ).active()
        if position:
            held_qs = held_qs.filter(quant__position=position)
        held = held_qs.aggregate(
            t=Coalesce(Sum('quantity'), Decimal('0'))
        )['t']

        return total - held

    @classmethod
    def promise(
        cls,
        sku: str,
        quantity,
        *,
        target_date: date | None = None,
        safety_margin: int = 0,
        allowed_positions: list[str] | None = None,
    ):
        """Return Stockman's explicit promise decision for a SKU."""
        from shopman.stockman.services.availability import promise_decision_for_sku

        return promise_decision_for_sku(
            sku,
            quantity,
            target_date=target_date,
            safety_margin=safety_margin,
            allowed_positions=allowed_positions,
        )

    @classmethod
    def demand(cls, sku_or_product, target_date: date) -> Decimal:
        """
        Pending demand (holds without linked stock).

        Returns:
            Sum of Hold.quantity where quant=None and target_date=date
        """
        sku = sku_or_product if isinstance(sku_or_product, str) else sku_or_product.sku
        return Hold.objects.filter(
            sku=sku,
            target_date=target_date,
            quant__isnull=True,
        ).active().aggregate(
            t=Coalesce(Sum('quantity'), Decimal('0'))
        )['t']

    @classmethod
    def committed(cls, sku_or_product, target_date: date | None = None) -> Decimal:
        """
        Total quantity committed (active holds) for product/date.

        Returns:
            Sum of active hold quantities
        """
        target = target_date or date.today()
        sku = sku_or_product if isinstance(sku_or_product, str) else sku_or_product.sku

        return Hold.objects.filter(
            sku=sku,
            target_date=target,
        ).active().aggregate(
            t=Coalesce(Sum('quantity'), Decimal('0'))
        )['t']

    @classmethod
    def get_quant(cls, sku_or_product, position: Position | None = None,
                  target_date: date | None = None, batch: str = '') -> Quant | None:
        """Get specific quant by coordinates."""
        sku = sku_or_product if isinstance(sku_or_product, str) else sku_or_product.sku
        return Quant.objects.filter(
            sku=sku,
            position=position,
            target_date=target_date,
            batch=batch
        ).first()

    @classmethod
    def list_quants(cls, sku_or_product=None, position: Position | None = None,
                    include_future: bool = True, include_empty: bool = False):
        """List quants with filters."""
        qs = Quant.objects.all()

        if sku_or_product is not None:
            sku = sku_or_product if isinstance(sku_or_product, str) else sku_or_product.sku
            qs = qs.filter(sku=sku)

        if position is not None:
            qs = qs.filter(position=position)

        if not include_future:
            qs = qs.filter(Q(target_date__isnull=True) | Q(target_date__lte=date.today()))

        if not include_empty:
            qs = qs.filter(_quantity__gt=0)

        return qs
