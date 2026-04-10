"""
Stock planning — production planning operations (plan, replan, realize).

Extension that builds on top of movements for production scheduling.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from shopman.stockman.conf import stockman_settings
from shopman.stockman.exceptions import StockError
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.models.move import Move
from shopman.stockman.models.quant import Quant

logger = logging.getLogger('shopman.stockman')

# Default TTL for holds after stock materializes (minutes)
DEFAULT_MATERIALIZED_HOLD_TTL_MINUTES = 60


class StockPlanning:
    """Production planning methods."""

    @classmethod
    def plan(cls, quantity, product, target_date,
             position=None, user=None,
             reason='Produção planejada', **metadata):
        """
        Plan future production.

        Shortcut for receive() with mandatory target_date.

        Args:
            quantity: Amount to plan
            product: Product object (must have .sku)
            target_date: Target production date
        """
        from shopman.stockman.services.movements import StockMovements
        return StockMovements.receive(
            quantity=quantity,
            sku=product.sku,
            position=position,
            target_date=target_date,
            user=user,
            reason=reason,
            **metadata
        )

    @classmethod
    def replan(cls, quantity, product, target_date,
               reason, user=None):
        """
        Adjust existing plan.

        Finds Quant(sku, target_date) and adjusts quantity.
        """
        from shopman.stockman.services.movements import StockMovements
        from shopman.stockman.services.queries import StockQueries

        quant = StockQueries.get_quant(product.sku, target_date=target_date)

        if quant is None:
            raise StockError('QUANT_NOT_FOUND', product=str(product), target_date=target_date)

        StockMovements.adjust(quant, quantity, reason, user)
        quant.refresh_from_db()
        return quant

    @classmethod
    def realize(cls, product, target_date, actual_quantity,
                to_position, from_position=None, user=None,
                reason='Produção realizada'):
        """
        Realize production (planned -> physical).

        1. Finds planned Quant
        2. Adjusts quantity if actual_quantity differs
        3. Transfers to physical position (target_date=None)
        4. Holds are transferred automatically
        """
        if actual_quantity <= 0:
            raise StockError('INVALID_QUANTITY', requested=actual_quantity)

        from shopman.stockman.services.queries import StockQueries

        sku = product.sku
        quant = StockQueries.get_quant(sku, target_date=target_date, position=from_position)

        if quant is None and from_position is not None:
            # Fallback: try without position
            quant = StockQueries.get_quant(sku, target_date=target_date)

        if quant is None:
            raise StockError('QUANT_NOT_FOUND', product=str(product), target_date=target_date)

        with transaction.atomic():
            locked_quant = Quant.objects.select_for_update().get(pk=quant.pk)

            # Get or create physical quant
            physical_quant, _ = Quant.objects.get_or_create(
                sku=sku,
                position=to_position,
                target_date=None,
                batch='',
                defaults={'metadata': {}}
            )

            # Transfer actual_quantity from planned → physical.
            # The planned Quant may hold more stock (from multiple WOs),
            # so we only debit what was actually produced.
            Move.objects.create(
                quant=locked_quant,
                delta=-actual_quantity,
                reason=f"Transferência: {reason}",
                user=user
            )

            Move.objects.create(
                quant=physical_quant,
                delta=actual_quantity,
                reason=f"Recebido de produção: {reason}",
                user=user
            )

            # Transfer holds up to actual_quantity (FIFO)
            # Holds that were against planned stock get a TTL now
            # (the clock starts when stock materializes).
            transferred = Decimal('0')
            materialized_hold_ids = []
            now = timezone.now()
            hold_ttl_minutes = getattr(
                stockman_settings, 'MATERIALIZED_HOLD_TTL_MINUTES',
                DEFAULT_MATERIALIZED_HOLD_TTL_MINUTES,
            )
            materialized_expires_at = now + timedelta(minutes=hold_ttl_minutes)

            for hold in locked_quant.holds.filter(
                status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED]
            ).order_by('created_at'):
                if transferred >= actual_quantity:
                    break
                hold.quant = physical_quant
                # Start the clock: set expires_at if hold had no timeout
                # (was a purchase intention against planned stock)
                update_fields = ['quant']
                if hold.expires_at is None:
                    hold.expires_at = materialized_expires_at
                    update_fields.append('expires_at')
                hold.save(update_fields=update_fields)
                transferred += hold.quantity
                materialized_hold_ids.append(hold.hold_id)

            physical_quant.refresh_from_db()
            logger.info(
                "stock.realize",
                extra={
                    "sku": sku,
                    "target": str(target_date),
                    "actual_qty": str(actual_quantity),
                    "to_position": str(to_position),
                    "materialized_holds": len(materialized_hold_ids),
                },
            )

            # Emit signal after transaction commits (holds visible to receivers)
            if materialized_hold_ids:
                from shopman.stockman.signals import holds_materialized

                def _emit_signal():
                    holds_materialized.send(
                        sender=StockPlanning,
                        hold_ids=materialized_hold_ids,
                        sku=sku,
                        target_date=target_date,
                        to_position=to_position,
                    )

                transaction.on_commit(_emit_signal)

            return physical_quant
