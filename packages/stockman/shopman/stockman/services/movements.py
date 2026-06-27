"""
Stock movements — state-changing operations (receive, issue, adjust).

All methods use transaction.atomic() with appropriate locking.
"""

import logging

from django.db import transaction
from shopman.stockman.exceptions import StockError
from shopman.stockman.models.move import Move
from shopman.stockman.models.quant import Quant

logger = logging.getLogger('shopman.stockman')


class StockMovements:
    """State-changing stock movement methods."""

    @classmethod
    def receive(cls, quantity, sku, position=None,
                target_date=None, batch='',
                user=None, reason='Recebimento', kind=Move.Kind.ADJUST, **metadata):
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
                kind=kind,
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
              user=None, reason='Saída', kind=Move.Kind.ADJUST):
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
                kind=kind,
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

        if new_quantity < 0:
            raise StockError(
                'INVALID_QUANTITY',
                requested=new_quantity,
            )

        with transaction.atomic():
            locked_quant = Quant.objects.select_for_update().get(pk=quant.pk)
            delta = new_quantity - locked_quant._quantity

            if delta == 0:
                return None

            move = Move.objects.create(
                quant=locked_quant,
                delta=delta,
                reason=f"Ajuste: {reason}",
                kind=Move.Kind.ADJUST,
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

    @classmethod
    def transfer(cls, quantity, sku, from_position, to_position,
                 target_date=None, batch='', user=None, reason='Transferência'):
        """
        Relocate stock between positions (internal move, no economic in/out).

        Two ledger legs, atomic: issue from source, receive into destination —
        both ``kind=TRANSFER``. This is the canonical home for relocations
        (e.g. depósito→vitrine, vitrine→"ontem"). Net stock unchanged; only the
        position (and optionally target_date/batch) moves.

        Raises:
            StockError('INVALID_QUANTITY'): quantity <= 0
            StockError('QUANT_NOT_FOUND'): source coordinate has no quant
            StockError('INSUFFICIENT_QUANTITY'): source available < quantity
        """
        from shopman.stockman.services.queries import StockQueries

        if quantity <= 0:
            raise StockError('INVALID_QUANTITY', requested=quantity)
        if from_position == to_position:
            raise StockError('INVALID_TRANSFER', reason='origem == destino')

        with transaction.atomic():
            source = StockQueries.get_quant(
                sku, target_date=target_date, position=from_position, batch=batch,
            )
            if source is None:
                raise StockError('QUANT_NOT_FOUND', product=sku, position=str(from_position))

            cls.issue(
                quantity=quantity, quant=source, user=user,
                reason=reason, kind=Move.Kind.TRANSFER,
            )
            dest = cls.receive(
                quantity=quantity, sku=sku, position=to_position,
                target_date=target_date, batch=batch, user=user,
                reason=reason, kind=Move.Kind.TRANSFER,
            )
            logger.info(
                "stock.transfer",
                extra={
                    "sku": sku, "qty": str(quantity),
                    "from": str(from_position), "to": str(to_position),
                },
            )
            return dest
