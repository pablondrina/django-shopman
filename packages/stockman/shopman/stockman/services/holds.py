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
from shopman.stockman.conf import stockman_settings
from shopman.stockman.exceptions import StockError
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.models.hold import Hold
from shopman.stockman.models.move import Move
from shopman.stockman.models.quant import Quant
from shopman.stockman.services.availability import promise_decision_for_sku
from shopman.stockman.services.queries import _resolve_stock_profile
from shopman.stockman.services.scope import quants_eligible_for

logger = logging.getLogger('shopman.stockman')

def _parse_hold_id(hold_id: str) -> int:
    """Extract PK from hold_id."""
    if hold_id and hold_id.startswith('hold:'):
        try:
            return int(hold_id.split(':')[1])
        except (IndexError, ValueError):
            pass
    raise StockError('INVALID_HOLD', hold_id=hold_id)


def _find_quant_for_hold(
    sku: str,
    product,
    target_date: date,
    quantity: Decimal,
    *,
    allowed_positions: list[str] | None = None,
    excluded_positions: list[str] | None = None,
) -> Quant | None:
    """Find a quant with enough availability for the hold (FIFO).

    Uses the canonical :func:`quants_eligible_for` scope so hold eligibility
    matches the availability read (shelflife, batch expiry, channel positions).
    """
    quants = quants_eligible_for(
        sku,
        target_date=target_date,
        allowed_positions=allowed_positions,
        excluded_positions=excluded_positions,
    )

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
             expires_at=None, *,
             actor=None,
             allowed_positions: list[str] | None = None,
             excluded_positions: list[str] | None = None,
             **metadata):
        """
        Create quantity hold.

        Allocation model — 1:1 hold:quant by design:
            Each hold is anchored to exactly one Quant (or None for demand_ok holds).
            ``_find_quant_for_hold`` selects the best single Quant that can satisfy
            the full quantity. Splitting across multiple Quants is a deliberate
            non-goal for v1 — it would require a redesign of the fulfill flow, which
            assumes a single-quant anchor per hold.

        Demand-mode fallback:
            When ``policy == 'demand_ok'`` and no single Quant satisfies the
            requested quantity, a floating hold is created with ``quant=None``.
            This allows forward-selling (pre-orders, made-to-order items) without
            a physical Quant reservation. The hold is fulfilled later when stock
            arrives.

        Args:
            quantity: Amount to hold
            product: Product-like object or SKU string
            target_date: Desired date (None = today)
            expires_at: Expiration datetime (optional)
            actor: User creating the hold (optional, stored on Hold.actor)
            allowed_positions: Channel-scoped position allowlist. When set,
                the hold will only consider quants at those positions.
            excluded_positions: Channel-scoped position denylist. Typically
                used by remote channels to exclude staff-only positions
                (e.g. ``ontem``) from customer-facing reservations.

        Returns:
            hold_id in format "hold:{pk}"

        Raises:
            StockError('INSUFFICIENT_AVAILABLE'): If no availability
                and policy is not 'demand_ok'
        """
        if quantity <= 0:
            raise StockError('INVALID_QUANTITY', requested=quantity)

        target = target_date or date.today()
        profile = _resolve_stock_profile(product)
        sku = profile["sku"]

        with transaction.atomic():
            decision = promise_decision_for_sku(
                sku, quantity, target_date=target,
                allowed_positions=allowed_positions,
                excluded_positions=excluded_positions,
            )
            policy = profile["availability_policy"] or decision.availability_policy
            approved = decision.approved
            available = decision.available_qty

            if decision.is_paused:
                approved = False
                available = Decimal("0")
            elif policy == 'demand_ok':
                approved = True
                available = max(decision.available_qty, quantity)
            elif policy == 'stock_only':
                approved = quantity <= decision.available
                available = decision.available

            if not approved:
                raise StockError(
                    'INSUFFICIENT_AVAILABLE',
                    available=available,
                    requested=quantity,
                    reason_code=decision.reason_code,
                )

            quant = _find_quant_for_hold(
                sku, product, target, quantity,
                allowed_positions=allowed_positions,
                excluded_positions=excluded_positions,
            )

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
                        actor=actor,
                        metadata=metadata,
                    )
                    logger.info(
                        "stock.hold.created",
                        extra={
                            "sku": sku,
                            "qty": str(quantity),
                            "target": str(target),
                            "hold_id": hold.hold_id,
                            "actor": actor.pk if actor else None,
                        },
                    )
                    return hold.hold_id

            if policy == 'demand_ok':
                hold = Hold.objects.create(
                    sku=sku,
                    quant=None,
                    quantity=quantity,
                    target_date=target,
                    status=HoldStatus.PENDING,
                    expires_at=expires_at,
                    actor=actor,
                    metadata=metadata,
                )
                logger.info(
                    "stock.hold.demand",
                    extra={
                        "sku": sku,
                        "qty": str(quantity),
                        "target": str(target),
                        "hold_id": hold.hold_id,
                        "actor": actor.pk if actor else None,
                    },
                )
                return hold.hold_id

            raise StockError(
                'INSUFFICIENT_AVAILABLE',
                available=available,
                requested=quantity
            )

    @classmethod
    def confirm(cls, hold_id, actor=None):
        """
        Confirm hold (checkout started).

        Transition: PENDING -> CONFIRMED

        Args:
            hold_id: Hold identifier in "hold:{pk}" format.
            actor: User performing the action (logged to metadata).
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
            if actor is not None:
                hold.metadata['confirmed_by'] = actor.pk
            update_fields = ['status'] + (['metadata'] if actor is not None else [])
            hold.save(update_fields=update_fields)
            logger.info(
                "stock.hold.confirmed",
                extra={"hold_id": hold_id, "actor": actor.pk if actor else None},
            )
            return hold

    @classmethod
    def release(cls, hold_id, reason='Liberado', actor=None):
        """
        Release hold (cancellation).

        Transition: PENDING|CONFIRMED -> RELEASED

        Args:
            hold_id: Hold identifier in "hold:{pk}" format.
            reason: Human-readable release reason (stored in metadata).
            actor: User performing the action (logged to metadata).
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
            if actor is not None:
                hold.metadata['released_by'] = actor.pk
            hold.save(update_fields=['status', 'resolved_at', 'metadata'])
            logger.info(
                "stock.hold.released",
                extra={"hold_id": hold_id, "reason": reason, "actor": actor.pk if actor else None},
            )
            return hold

    @classmethod
    def fulfill(cls, hold_id, user=None, actor=None, *, quantity: Decimal | None = None):
        """
        Fulfill hold (deliver to customer).

        1. Validates status is CONFIRMED
        2. Creates negative Move on linked Quant
        3. Transition: CONFIRMED -> FULFILLED

        Args:
            hold_id: Hold identifier in "hold:{pk}" format.
            user: User attached to the Move record (ledger authorship).
            actor: User performing the fulfillment action (logged to metadata).
                   Falls back to `user` when not provided.
            quantity: Override the Move delta. When provided, only this amount
                is decremented from the quant (the hold may have reserved more
                due to session hold over-adoption). Defaults to `hold.quantity`.

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

            if hold.is_expired:
                raise StockError('HOLD_EXPIRED', hold_id=hold_id)

            if hold.quant is None:
                raise StockError('HOLD_IS_DEMAND', hold_id=hold_id)

            quant = Quant.objects.select_for_update().get(pk=hold.quant_id)

            consume_qty = quantity if quantity is not None else hold.quantity
            move = Move.objects.create(
                quant=quant,
                delta=-consume_qty,
                reason=f"Entrega hold:{hold.pk}",
                user=user
            )

            _actor = actor or user
            hold.status = HoldStatus.FULFILLED
            hold.resolved_at = timezone.now()
            if _actor is not None:
                hold.metadata['fulfilled_by'] = _actor.pk
            update_fields = ['status', 'resolved_at'] + (['metadata'] if _actor is not None else [])
            hold.save(update_fields=update_fields)

            logger.info(
                "stock.hold.fulfilled",
                extra={"hold_id": hold_id, "qty": str(hold.quantity), "actor": _actor.pk if _actor else None},
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

    # ── Reference-based queries ──────────────────────────────────

    @staticmethod
    def find_by_reference(
        reference: str,
        *,
        sku: str | None = None,
        status_in: list[str] | None = None,
    ):
        """Find holds by metadata.reference.

        Args:
            reference: The reference tag stored in Hold.metadata["reference"].
            sku: Optional SKU filter.
            status_in: Optional list of HoldStatus values to filter on.

        Returns:
            QuerySet[Hold] ordered by pk (FIFO).
        """
        qs = Hold.objects.filter(metadata__reference=reference)
        if sku:
            qs = qs.filter(sku=sku)
        if status_in:
            qs = qs.filter(status__in=status_in)
        return qs.order_by("pk")

    @staticmethod
    def find_active_by_reference(reference: str):
        """Find active (PENDING/CONFIRMED, not expired) holds for a reference.

        Returns:
            QuerySet[Hold] — active holds ordered by pk (FIFO).
        """
        return Hold.objects.filter(
            metadata__reference=reference,
        ).active().order_by("pk")

    @staticmethod
    def retag_reference(hold_id: str, new_reference: str) -> bool:
        """Update Hold.metadata.reference to a new value.

        Used to transfer a hold from session scope to order scope.

        Returns:
            True if the hold was updated, False if not found.
        """
        pk = _parse_hold_id(hold_id)
        try:
            hold = Hold.objects.get(pk=pk)
        except Hold.DoesNotExist:
            return False

        metadata = dict(hold.metadata or {})
        metadata["reference"] = new_reference
        hold.metadata = metadata
        hold.save(update_fields=["metadata"])
        return True
