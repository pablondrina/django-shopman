"""
Stock signal receivers — auto-commit sessions after hold materialization,
and production voided → release holds + notify fermata sessions.
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def on_production_voided(sender, product_ref, date, action, work_order, **kwargs):
    """When production is voided, release demand holds and notify fermata sessions."""
    if action != "voided":
        return

    try:
        from shopman.stocking.models import Hold
        from shopman.stocking.models.enums import HoldStatus
        from shopman.stocking.service import Stock as stock
    except ImportError:
        return

    # Find pending holds for this SKU/date that are linked to planned quants
    holds = Hold.objects.filter(
        sku=product_ref,
        target_date=date,
        status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
    )

    session_keys = set()
    for hold in holds:
        ref = (hold.metadata or {}).get("reference")
        if ref:
            session_keys.add(ref)
        try:
            stock.release(hold.hold_id, reason="Produção cancelada")
        except Exception:
            logger.debug("on_production_voided: could not release hold %s", hold.hold_id)

    if not session_keys:
        return

    # Notify fermata sessions
    try:
        from shopman.ordering.models import Directive, Session

        sessions = Session.objects.filter(
            session_key__in=session_keys, state="open",
        )
        for session in sessions:
            check_result = (
                (session.data or {}).get("checks", {}).get("stock", {}).get("result", {})
            )
            if check_result.get("has_planned_holds"):
                from shopman.topics import NOTIFICATION_SEND

                Directive.objects.create(
                    topic=NOTIFICATION_SEND,
                    payload={
                        "session_key": session.session_key,
                        "template": "production_cancelled",
                        "context": {"sku": product_ref, "date": str(date)},
                    },
                )
                logger.info(
                    "on_production_voided: notified session %s about voided production of %s for %s",
                    session.session_key, product_ref, date,
                )
    except Exception:
        logger.warning("on_production_voided: failed to notify sessions", exc_info=True)


def on_holds_materialized(sender, hold_ids, sku, target_date, **kwargs):
    """React when planned holds are materialized (stock became physical)."""
    if not hold_ids:
        return

    from shopman.stocking.models import Hold

    session_keys = set()
    for hold_id in hold_ids:
        try:
            pk = int(hold_id.split(":")[1])
            hold = Hold.objects.get(pk=pk)
            ref = (hold.metadata or {}).get("reference")
            if ref:
                session_keys.add(ref)
        except (Hold.DoesNotExist, IndexError, ValueError, TypeError):
            pass

    if not session_keys:
        return

    from shopman.ordering.models import Session

    sessions = Session.objects.filter(
        session_key__in=session_keys, state="open",
    ).select_related("channel")

    for session in sessions:
        check_result = (
            (session.data or {}).get("checks", {}).get("stock", {}).get("result", {})
        )
        if not check_result.get("has_planned_holds"):
            continue

        if not _all_holds_materialized(check_result):
            continue

        try:
            _auto_commit_session(session)
        except Exception:
            logger.warning(
                "Failed to auto-commit session %s:%s",
                session.channel.ref, session.session_key, exc_info=True,
            )


def _all_holds_materialized(check_result: dict) -> bool:
    from shopman.stocking.models import Hold

    planned_holds = [h for h in check_result.get("holds", []) if h.get("is_planned")]
    if not planned_holds:
        return True

    for hold_data in planned_holds:
        hold_id = hold_data.get("hold_id")
        if not hold_id:
            continue
        try:
            pk = int(hold_id.split(":")[1])
            hold = Hold.objects.get(pk=pk)
            if hold.quant is None or hold.quant.target_date is not None:
                return False
        except (Hold.DoesNotExist, IndexError, ValueError):
            return False

    return True


def _auto_commit_session(session):
    from shopman.ordering.services.commit import CommitService

    idempotency_key = f"auto-commit-{session.session_key}-{uuid.uuid4().hex[:8]}"

    result = CommitService.commit(
        session_key=session.session_key,
        channel_ref=session.channel.ref,
        idempotency_key=idempotency_key,
        ctx={"actor": "stock_materialized"},
    )

    logger.info(
        "Auto-commit successful: session=%s:%s order=%s",
        session.channel.ref, session.session_key, result.get("order_ref"),
    )
