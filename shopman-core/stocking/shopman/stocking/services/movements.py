"""
Stock movements — state-changing operations (receive, issue, adjust).

All methods use transaction.atomic() with appropriate locking.
"""

import logging

from django.db import transaction

from shopman.stocking.exceptions import StockError
from shopman.stocking.models.move import Move
from shopman.stocking.models.quant import Quant

logger = logging.getLogger('shopman.stocking')


class StockMovements:
    """State-changing stock movement methods."""

    @classmethod
    def receive(cls, quantity, sku, position=None,
                target_date=None, batch='',
                user=None, reason='Recebimento', **metadata):
        """
        Stock entry.

        Creates or updates Quant at specified coordinate.
        Creates Move with positive delta.

        Args:
            quantity: Amount to receive
            sku: Product SKU string
            position: Position instance (optional)
            target_date: Future date for planned stock (optional)
            batch: Batch ref string (optional)
            user: User performing the operation (optional)
            reason: Reason for the movement
        """
        if quantity <= 0:
            raise StockError('INVALID_QUANTITY', requested=quantity)

        with transaction.atomic():
            quant, created = Quant.objects.get_or_create(
                sku=sku,
                position=position,
                target_date=target_date,
                batch=batch,
                defaults={'metadata': metadata}
            )

            Move.objects.create(
                quant=quant,
                delta=quantity,
                reason=reason,
                user=user,
                metadata=metadata
            )

            quant.refresh_from_db()
            logger.info(
                "stock.receive",
                extra={
                    "sku": sku,
                    "qty": str(quantity),
                    "position": str(position),
                    "reason": reason,
                    "quant_id": quant.pk,
                },
            )
            return quant

    @classmethod
    def issue(cls, quantity, quant,
              user=None, reason='Saída'):
        """
        Stock exit.

        Raises:
            StockError('INSUFFICIENT_QUANTITY'): If quantity > quant.available
            StockError('INVALID_QUANTITY'): If quantity <= 0

        Concurrency:
            - Runs under transaction.atomic()
            - Uses select_for_update() on Quant
            - Verifies availability after lock
        """
        if quantity <= 0:
            raise StockError('INVALID_QUANTITY', requested=quantity)

        with transaction.atomic():
            locked_quant = Quant.objects.select_for_update().get(pk=quant.pk)

            if locked_quant.available < quantity:
                raise StockError(
                    'INSUFFICIENT_QUANTITY',
                    available=locked_quant.available,
                    requested=quantity
                )

            move = Move.objects.create(
                quant=locked_quant,
                delta=-quantity,
                reason=reason,
                user=user
            )
            logger.info(
                "stock.issue",
                extra={
                    "quant_id": quant.pk,
                    "qty": str(quantity),
                    "reason": reason,
                },
            )
            return move

    @classmethod
    def adjust(cls, quant, new_quantity, reason, user=None):
        """
        Inventory adjustment.

        Calculates delta automatically: new_quantity - quant.quantity

        Raises:
            StockError('REASON_REQUIRED'): If reason is empty
        """
        if not reason:
            raise StockError('REASON_REQUIRED')

        with transaction.atomic():
            locked_quant = Quant.objects.select_for_update().get(pk=quant.pk)
            delta = new_quantity - locked_quant._quantity

            if delta == 0:
                return None

            move = Move.objects.create(
                quant=locked_quant,
                delta=delta,
                reason=f"Ajuste: {reason}",
                user=user
            )
            logger.info(
                "stock.adjust",
                extra={
                    "quant_id": quant.pk,
                    "delta": str(delta),
                    "reason": reason,
                },
            )
            return move
