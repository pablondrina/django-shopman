"""
Stock holds — reservation lifecycle (hold, confirm, release, fulfill).

All methods use transaction.atomic() with appropriate locking.
"""

import logging
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from shopman.stocking.conf import stockman_settings
from shopman.stocking.exceptions import StockError
from shopman.stocking.models.enums import HoldStatus
from shopman.stocking.models.hold import Hold
from shopman.stocking.models.move import Move
from shopman.stocking.models.quant import Quant
from shopman.stocking.shelflife import filter_valid_quants


logger = logging.getLogger('shopman.stocking')

# Defaults when product doesn't implement StockableProduct protocol
PRODUCT_DEFAULTS = {
    'shelflife': None,
    'availability_policy': 'planned_ok',
}


def _get_product_attr(product, attr: str, default=None):
    """Get product attribute with fallback to default."""
    value = getattr(product, attr, None)
    if value is not None:
        return value
    return PRODUCT_DEFAULTS.get(attr, default)


def _parse_hold_id(hold_id: str) -> int:
    """Extract PK from hold_id."""
    if hold_id and hold_id.startswith('hold:'):
        try:
            return int(hold_id.split(':')[1])
        except (IndexError, ValueError):
            pass
    raise StockError('INVALID_HOLD', hold_id=hold_id)


def _find_quant_for_hold(sku: str, product, target_date: date, quantity: Decimal) -> Quant | None:
    """Find a quant with enough availability for the hold (FIFO)."""
    quants = Quant.objects.filter(sku=sku)
    quants = filter_valid_quants(quants, product, target_date)

    # Annotate held_qty to avoid N+1
    now = timezone.now()
    quants = quants.annotate(
        _held_qty=Coalesce(
            Sum(
                'holds__quantity',
                filter=Q(
                    holds__status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
                ) & (
                    Q(holds__expires_at__isnull=True) | Q(holds__expires_at__gte=now)
                ),
            ),
            Decimal('0'),
        )
    ).order_by('created_at')

    for quant in quants:
        available = quant._quantity - quant._held_qty
        if available >= quantity:
            return quant

    return None


class StockHolds:
    """Hold lifecycle methods."""

    @classmethod
    def hold(cls, quantity, product, target_date=None,
             expires_at=None, **metadata):
        """
        Create quantity hold.

        Args:
            quantity: Amount to hold
            product: Product object (must have .sku, optionally .availability_policy)
            target_date: Desired date (None = today)
            expires_at: Expiration datetime (optional)

        Returns:
            hold_id in format "hold:{pk}"

        Raises:
            StockError('INSUFFICIENT_AVAILABLE'): If no availability
                and policy is not 'demand_ok'
        """
        if quantity <= 0:
            raise StockError('INVALID_QUANTITY', requested=quantity)

        target = target_date or date.today()
        policy = _get_product_attr(product, 'availability_policy', 'planned_ok')
        sku = product.sku

        with transaction.atomic():
            quant = _find_quant_for_hold(sku, product, target, quantity)

            if quant:
                quant = Quant.objects.select_for_update().get(pk=quant.pk)

                if quant.available >= quantity:
                    hold = Hold.objects.create(
                        sku=sku,
                        quant=quant,
                        quantity=quantity,
                        target_date=target,
                        status=HoldStatus.PENDING,
                        expires_at=expires_at,
                        metadata=metadata
                    )
                    logger.info(
                        "stock.hold.created",
                        extra={
                            "sku": sku,
                            "qty": str(quantity),
                            "target": str(target),
                            "hold_id": hold.hold_id,
                        },
                    )
                    return hold.hold_id

            # Not enough availability — compute actual total for error reporting
            from shopman.stocking.services.queries import StockQueries
            current_available = StockQueries.available(sku, target, product=product)

            if policy == 'demand_ok':
                hold = Hold.objects.create(
                    sku=sku,
                    quant=None,
                    quantity=quantity,
                    target_date=target,
                    status=HoldStatus.PENDING,
                    expires_at=expires_at,
                    metadata=metadata
                )
                logger.info(
                    "stock.hold.demand",
                    extra={
                        "sku": sku,
                        "qty": str(quantity),
                        "target": str(target),
                        "hold_id": hold.hold_id,
                    },
                )
                return hold.hold_id

            raise StockError(
                'INSUFFICIENT_AVAILABLE',
                available=current_available,
                requested=quantity
            )

    @classmethod
    def confirm(cls, hold_id):
        """
        Confirm hold (checkout started).

        Transition: PENDING -> CONFIRMED
        """
        pk = _parse_hold_id(hold_id)

        with transaction.atomic():
            try:
                hold = Hold.objects.select_for_update().get(pk=pk)
            except Hold.DoesNotExist:
                raise StockError('INVALID_HOLD', hold_id=hold_id) from None

            if hold.status != HoldStatus.PENDING:
                raise StockError(
                    'INVALID_STATUS',
                    current=hold.status,
                    expected=HoldStatus.PENDING
                )

            hold.status = HoldStatus.CONFIRMED
            hold.save(update_fields=['status'])
            logger.info(
                "stock.hold.confirmed",
                extra={"hold_id": hold_id},
            )
            return hold

    @classmethod
    def release(cls, hold_id, reason='Liberado'):
        """
        Release hold (cancellation).

        Transition: PENDING|CONFIRMED -> RELEASED
        """
        pk = _parse_hold_id(hold_id)

        with transaction.atomic():
            try:
                hold = Hold.objects.select_for_update().get(pk=pk)
            except Hold.DoesNotExist:
                raise StockError('INVALID_HOLD', hold_id=hold_id) from None

            if hold.status not in [HoldStatus.PENDING, HoldStatus.CONFIRMED]:
                raise StockError(
                    'INVALID_STATUS',
                    current=hold.status,
                    expected=[HoldStatus.PENDING, HoldStatus.CONFIRMED]
                )

            hold.status = HoldStatus.RELEASED
            hold.resolved_at = timezone.now()
            hold.metadata['release_reason'] = reason
            hold.save(update_fields=['status', 'resolved_at', 'metadata'])
            logger.info(
                "stock.hold.released",
                extra={"hold_id": hold_id, "reason": reason},
            )
            return hold

    @classmethod
    def fulfill(cls, hold_id, user=None):
        """
        Fulfill hold (deliver to customer).

        1. Validates status is CONFIRMED
        2. Creates negative Move on linked Quant
        3. Transition: CONFIRMED -> FULFILLED

        Returns:
            Created Move
        """
        pk = _parse_hold_id(hold_id)

        with transaction.atomic():
            try:
                hold = Hold.objects.select_for_update().get(pk=pk)
            except Hold.DoesNotExist:
                raise StockError('INVALID_HOLD', hold_id=hold_id) from None

            if hold.status != HoldStatus.CONFIRMED:
                raise StockError(
                    'INVALID_STATUS',
                    current=hold.status,
                    expected=HoldStatus.CONFIRMED
                )

            if hold.quant is None:
                raise StockError('HOLD_IS_DEMAND', hold_id=hold_id)

            quant = Quant.objects.select_for_update().get(pk=hold.quant_id)

            move = Move.objects.create(
                quant=quant,
                delta=-hold.quantity,
                reason=f"Entrega hold:{hold.pk}",
                user=user
            )

            hold.status = HoldStatus.FULFILLED
            hold.resolved_at = timezone.now()
            hold.save(update_fields=['status', 'resolved_at'])

            logger.info(
                "stock.hold.fulfilled",
                extra={"hold_id": hold_id, "qty": str(hold.quantity)},
            )
            return move

    @classmethod
    def release_expired(cls):
        """
        Release all expired holds in batches.

        Returns:
            Number of holds released
        """
        now = timezone.now()
        total = 0
        batch_size = stockman_settings.EXPIRED_BATCH_SIZE

        while True:
            with transaction.atomic():
                batch_ids = list(
                    Hold.objects.select_for_update(skip_locked=True)
                    .expired()
                    .values_list('pk', flat=True)[:batch_size]
                )

                if not batch_ids:
                    break

                Hold.objects.filter(pk__in=batch_ids).update(
                    status=HoldStatus.RELEASED,
                    resolved_at=now,
                )
                total += len(batch_ids)

        if total:
            logger.info(
                "stock.holds.expired_released",
                extra={"released": total},
            )
        return total
