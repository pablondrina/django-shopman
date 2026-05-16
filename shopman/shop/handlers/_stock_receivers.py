"""
Stock signal receivers — auto-commit sessions after hold materialization,
and production voided → release holds + notify sessions with planned holds.
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def on_production_voided(sender, product_ref, date, action, work_order, **kwargs):
    """When production is voided, release demand holds and notify sessions with planned holds."""
    if action != "voided":
        return

    from shopman.stockman import Hold, HoldStatus
    from shopman.stockman.service import Stock as stock

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

    # Notify sessions that had planned holds for this SKU/date
    try:
        from shopman.orderman.models import Directive, Session

        sessions = Session.objects.filter(
            session_key__in=session_keys, state="open",
        )
        for session in sessions:
            check_result = (
                (session.data or {}).get("checks", {}).get("stock", {}).get("result", {})
            )
            if check_result.get("has_planned_holds"):
                from shopman.shop.directives import NOTIFICATION_SEND

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
    """React when planned holds are materialized (stock became physical).

    Two responsibilities:
    1. Fire an **active notification** to the shopper (AVAILABILITY-PLAN §8):
       "seu produto chegou, você tem até HH:MM pra confirmar". Honours
       ``feedback_transparent_timeouts`` — the shopper left the site, the
       storefront toast would never reach them. Uses the existing notification
       registry to route through WhatsApp / SMS / email based on
       customer preferences.
    2. Auto-commit the session when every planned hold has materialized
       (existing behaviour — ADR-007).
    """
    if not hold_ids:
        return

    from shopman.stockman.models import Hold

    session_keys = set()
    hold_ids_by_session: dict[str, list[str]] = {}
    for hold_id in hold_ids:
        try:
            pk = int(hold_id.split(":")[1])
            hold = Hold.objects.get(pk=pk)
            ref = (hold.metadata or {}).get("reference")
            if ref:
                session_keys.add(ref)
                hold_ids_by_session.setdefault(ref, []).append(hold_id)
        except (Hold.DoesNotExist, IndexError, ValueError, TypeError):
            pass

    if not session_keys:
        return

    from shopman.orderman.models import Session

    sessions = Session.objects.filter(
        session_key__in=session_keys, state="open",
    )

    for session in sessions:
        check_result = (
            (session.data or {}).get("checks", {}).get("stock", {}).get("result", {})
        )

        # (1) Active notification — fire for every materialization event,
        # independent of auto-commit. The shopper needs to know their
        # reserved item arrived.
        try:
            _notify_stock_arrived(
                session,
                sku=sku,
                target_date=target_date,
                hold_ids=hold_ids_by_session.get(session.session_key, []),
            )
        except Exception:
            logger.warning(
                "on_holds_materialized: notify failed session=%s sku=%s",
                session.session_key, sku, exc_info=True,
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
                session.channel_ref, session.session_key, exc_info=True,
            )


def _notify_stock_arrived(session, *, sku: str, target_date, hold_ids: list[str] | None = None) -> None:
    """Dispatch a ``stock.arrived`` notification for the session's shopper.

    Resolves the customer from the session, looks up the product name, and
    calls the canonical ``notify()`` registry which routes via the
    customer's preferred channel (ManyChat, SMS, email). Silent no-op when
    the session has no associated customer yet (anonymous cart).
    """
    from shopman.shop.notifications import notify

    customer = _resolve_session_customer(session)
    if customer is None:
        logger.debug(
            "stock.arrived not dispatched (session %s has no customer)",
            session.session_key,
        )
        return

    product_name = sku
    try:
        from shopman.offerman.models import Product

        product = Product.objects.filter(sku=sku).first()
        if product is not None:
            product_name = product.name
    except Exception:
        logger.debug("stock_arrived: product lookup failed for sku=%s", sku, exc_info=True)

    try:
        backend = _notification_backend(customer)
        notify(
            event="stock.arrived",
            recipient=_notification_recipient(customer, backend=backend),
            context={
                "sku": sku,
                "product_name": product_name,
                "target_date": str(target_date) if target_date else None,
                "deadline_at": _deadline_at_for_holds(hold_ids or []),
                "cart_url": _cart_url(),
                "session_key": session.session_key,
            },
            backend=backend,
        )
    except Exception:
        logger.warning(
            "stock.arrived dispatch failed sku=%s customer=%s",
            sku, getattr(customer, "pk", None), exc_info=True,
        )


def _resolve_session_customer(session):
    customer = getattr(session, "customer", None)
    if customer is not None:
        return customer

    data = session.data or {}
    customer_data = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    customer_id = (
        data.get("customer_id")
        or data.get("customer_uuid")
        or customer_data.get("uuid")
    )
    customer_ref = data.get("customer_ref") or customer_data.get("ref")
    phone = data.get("customer_phone") or customer_data.get("phone")

    try:
        from shopman.guestman.models import Customer
    except Exception:
        return None

    if customer_id:
        try:
            customer = Customer.objects.filter(pk=customer_id).first()
            if customer is not None:
                return customer
        except (TypeError, ValueError):
            pass
        try:
            customer = Customer.objects.filter(uuid=str(customer_id)).first()
            if customer is not None:
                return customer
        except (TypeError, ValueError):
            pass

    if customer_ref:
        customer = Customer.objects.filter(ref=customer_ref).first()
        if customer is not None:
            return customer

    if phone:
        return Customer.objects.filter(phone=phone, is_active=True).first()

    return None


def _notification_backend(customer) -> str | None:
    try:
        from shopman.shop.services import customer_context

        enabled = customer_context.enabled_notification_channels(
            customer.ref,
            ("whatsapp", "sms", "email"),
        )
    except Exception:
        enabled = frozenset()

    if "whatsapp" in enabled and getattr(customer, "phone", ""):
        return "manychat"
    if "sms" in enabled and getattr(customer, "phone", ""):
        return "sms"
    if "email" in enabled and getattr(customer, "email", ""):
        return "email"
    return None


def _notification_recipient(customer, *, backend: str | None = None) -> str:
    if backend == "email" and getattr(customer, "email", ""):
        return customer.email
    if backend in {"manychat", "sms"} and getattr(customer, "phone", ""):
        return customer.phone
    return (
        getattr(customer, "phone", "")
        or getattr(customer, "email", "")
        or getattr(customer, "ref", "")
        or str(getattr(customer, "pk", ""))
    )


def _deadline_at_for_holds(hold_ids: list[str]) -> str | None:
    pks: list[int] = []
    for hold_id in hold_ids:
        try:
            pks.append(int(hold_id.split(":")[1]))
        except (IndexError, ValueError, TypeError):
            continue
    if not pks:
        return None

    from shopman.stockman.models import Hold

    deadlines = list(
        Hold.objects.filter(pk__in=pks, expires_at__isnull=False)
        .values_list("expires_at", flat=True)
    )
    if not deadlines:
        return None
    return min(deadlines).isoformat()


def _cart_url() -> str:
    try:
        from django.urls import reverse

        path = reverse("storefront:cart")
    except Exception:
        path = "/cart/"

    try:
        from django.conf import settings

        base_url = getattr(settings, "SHOPMAN_BASE_URL", "").rstrip("/")
    except Exception:
        base_url = ""

    return f"{base_url}{path}" if base_url else path


def _all_holds_materialized(check_result: dict) -> bool:
    from shopman.stockman.models import Hold

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
    from shopman.orderman.services.commit import CommitService

    idempotency_key = f"auto-commit-{session.session_key}-{uuid.uuid4().hex[:8]}"

    result = CommitService.commit(
        session_key=session.session_key,
        channel_ref=session.channel_ref,
        idempotency_key=idempotency_key,
        ctx={"actor": "stock_materialized"},
    )

    logger.info(
        "Auto-commit successful: session=%s:%s order=%s",
        session.channel_ref, session.session_key, result.order_ref,
    )
