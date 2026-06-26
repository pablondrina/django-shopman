"""Customer-facing order reads and mutations.

Storefront and API surfaces should use this module instead of importing
Orderman, Guestman, or Offerman models directly.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError

from shopman.shop.services import payment as payment_service

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset({"new", "confirmed", "preparing", "ready", "dispatched"})
DEFAULT_CHANNEL_REF = "web"
ORDER_ACCESS_SESSION_KEY = "shopman_order_access_refs"
MAX_SESSION_ORDER_ACCESS_REFS = 20


def get_order(ref: str):
    """Return an order by ref or raise Http404."""
    from shopman.orderman.models import Order

    return get_object_or_404(Order, ref=ref)


def get_accessible_order(request, ref: str):
    """Return an order only when the current customer/session may see it."""
    order = get_order(ref)
    if request_can_access_order(request, order):
        return order
    logger.warning(
        "customer_order_access_denied order=%s user=%s",
        order.ref,
        getattr(getattr(request, "user", None), "pk", None),
    )
    raise Http404


def find_order(ref: str):
    """Return an order by ref, or None when it does not exist."""
    from shopman.orderman.models import Order

    return Order.objects.filter(ref=ref).first()


def grant_order_access(request, order_ref: str) -> None:
    """Bind an order ref to the current browser session after checkout/access-link."""
    if not order_ref or not hasattr(request, "session"):
        return
    refs = [
        str(ref)
        for ref in (request.session.get(ORDER_ACCESS_SESSION_KEY) or [])
        if ref
    ]
    if order_ref in refs:
        refs.remove(order_ref)
    refs.append(str(order_ref))
    request.session[ORDER_ACCESS_SESSION_KEY] = refs[-MAX_SESSION_ORDER_ACCESS_REFS:]
    request.session.modified = True


def request_can_access_order(request, order) -> bool:
    """Return True for staff, same checkout session, or matching customer identity."""
    user = getattr(request, "user", None)
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    if _session_can_access_order(request, order.ref):
        return True
    return customer_can_access_order(getattr(request, "customer", None), order)


def user_can_access_order(user, order) -> bool:
    """Return True when a Django user may subscribe/read an order channel."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    customer_ref, phone = _customer_identity_from_user(user)
    return order_matches_customer_identity(order, customer_ref=customer_ref, phone=phone)


def customer_can_access_order(customer_info, order) -> bool:
    """Return True when request.customer matches the order's sealed identity."""
    if customer_info is None:
        return False
    customer_ref, phone = _customer_identity_from_info(customer_info)
    return order_matches_customer_identity(order, customer_ref=customer_ref, phone=phone)


def order_matches_customer_identity(
    order,
    *,
    customer_ref: str | None = None,
    phone: str | None = None,
) -> bool:
    """Compare order identity without exposing whether the ref exists."""
    data = order.data if isinstance(order.data, dict) else {}
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}

    if customer_ref:
        if str(data.get("customer_ref") or "") == customer_ref:
            return True
        if str(customer.get("ref") or "") == customer_ref:
            return True

    if phone:
        candidates = [
            order.handle_ref if order.handle_type in {"phone", "whatsapp"} else "",
            str(customer.get("phone") or ""),
            str(data.get("customer_phone") or ""),
        ]
        return any(_same_phone(phone, candidate) for candidate in candidates if candidate)

    return False


def active_order_count_for_customer(
    *,
    customer_ref: str | None = None,
    phone: str | None = None,
) -> int:
    """Count active orders for the authenticated customer identity."""
    from shopman.orderman.models import Order

    identity = customer_identity_filter(customer_ref=customer_ref, phone=phone)
    if identity is None:
        return 0
    return Order.objects.filter(identity, status__in=ACTIVE_STATUSES).distinct().count()


def active_order_count_for_phone(phone: str) -> int:
    """Count active orders for the customer phone used by account badges."""
    return active_order_count_for_customer(phone=phone)


def last_reorder_context(*, customer_uuid, min_days: int) -> tuple[str | None, list[dict]]:
    """Return the last old-enough order ref and sealed snapshot items for reorder."""
    try:
        from shopman.guestman.services import customer as customer_service

        customer = customer_service.get_by_uuid(str(customer_uuid))
    except Exception:
        logger.warning("reorder_customer_lookup_failed customer_uuid=%s", customer_uuid, exc_info=True)
        return None, []

    if customer is None:
        logger.debug("reorder_customer_not_found customer_uuid=%s", customer_uuid)
        return None, []

    try:
        from shopman.orderman.models import Order

        identity = customer_identity_filter(customer_ref=customer.ref, phone=customer.phone)
        if identity is None:
            return None, []

        last = (
            Order.objects.filter(identity)
            .distinct()
            .order_by("-created_at")
            .prefetch_related("items")
            .first()
        )
    except Exception:
        logger.warning("reorder_order_lookup_failed customer_ref=%s", customer.ref, exc_info=True)
        return None, []

    if not last:
        logger.debug("reorder_no_previous_order customer_ref=%s", customer.ref)
        return None, []

    days_since = (timezone.now() - last.created_at).days
    if min_days > 0 and days_since < min_days:
        logger.debug(
            "reorder_previous_order_too_recent order_ref=%s days_since=%s min_days=%s",
            last.ref,
            days_since,
            min_days,
        )
        return None, []

    return last.ref, _reorder_display_items(last)


def _reorder_display_items(order) -> list[dict]:
    """Return display-safe reorder item rows for the compact home CTA."""
    order_items = list(order.items.all())
    if not order_items:
        return _named_snapshot_items((order.snapshot or {}).get("items") or [])

    product_names: dict[str, str] = {}
    skus = {item.sku for item in order_items if item.sku}
    if skus:
        try:
            from shopman.offerman.models import Product

            product_names = dict(
                Product.objects.filter(sku__in=skus).values_list("sku", "name")
            )
        except Exception:
            logger.warning("reorder_product_name_lookup_failed order=%s", order.ref, exc_info=True)

    rows: list[dict] = []
    for item in order_items:
        name = (item.name or "").strip() or product_names.get(item.sku, "").strip()
        if not name:
            continue
        rows.append(
            {
                "sku": item.sku,
                "name": name,
                "qty": item.qty,
                "unit_price_q": item.unit_price_q,
                "line_total_q": item.line_total_q,
            }
        )
    return rows


def _named_snapshot_items(items: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        rows.append({**item, "name": name})
    return rows


def get_payment_status(order) -> str | None:
    """Return the canonical payment status for an order."""
    return payment_service.get_payment_status(order)


def resolve_payment_timeout_if_due(order) -> bool:
    """Cancel an unpaid digital order when its displayed payment deadline passed."""
    from shopman.orderman.models import Order

    if _resolve_payment_timeout_directive_if_due(order):
        return True

    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method not in {"pix", "card"}:
        return False
    if order.status not in {Order.Status.NEW, Order.Status.CONFIRMED}:
        return False

    expires_at = _parse_payment_deadline(payment.get("expires_at"))
    if not expires_at or timezone.now() < expires_at:
        return False

    status = str(get_payment_status(order) or payment.get("status") or "").lower()
    if status == "unknown" or payment_service.has_sufficient_captured_payment(order) is True:
        return False
    if method == "card" and status == "authorized":
        return False

    payment_service.cancel(order, reason="payment_timeout")

    from shopman.shop.services import notification
    from shopman.shop.services.cancellation import cancel

    cancelled = cancel(
        order,
        reason="payment_timeout",
        actor="payment.timeout",
        extra_data={"payment_timeout_at": timezone.now().isoformat()},
    )
    if cancelled:
        notification.send(order, "payment_expired")
        order.refresh_from_db()
    return cancelled


def resolve_confirmation_timeout_if_due(order) -> bool:
    """Resolve an overdue store-confirmation timeout without requiring a worker."""
    from shopman.shop.directives import CONFIRMATION_TIMEOUT
    from shopman.shop.handlers.confirmation import ConfirmationTimeoutHandler

    return _resolve_due_directive_for_order(
        order,
        topic=CONFIRMATION_TIMEOUT,
        handler=ConfirmationTimeoutHandler(),
        log_name="confirmation_timeout",
    )


def resolve_delivery_auto_complete_if_due(order) -> bool:
    """Fecha um pedido em entrega vencido sem exigir o worker (resolve no acesso)."""
    from shopman.shop.directives import DELIVERY_AUTO_COMPLETE
    from shopman.shop.handlers.delivery_auto_complete import DeliveryAutoCompleteHandler

    return _resolve_due_directive_for_order(
        order,
        topic=DELIVERY_AUTO_COMPLETE,
        handler=DeliveryAutoCompleteHandler(),
        log_name="delivery_auto_complete",
    )


def _resolve_payment_timeout_directive_if_due(order) -> bool:
    from shopman.shop.directives import PAYMENT_TIMEOUT
    from shopman.shop.handlers.payment_timeout import PaymentTimeoutHandler

    return _resolve_due_directive_for_order(
        order,
        topic=PAYMENT_TIMEOUT,
        handler=PaymentTimeoutHandler(),
        log_name="payment_timeout",
    )


def _resolve_due_directive_for_order(order, *, topic: str, handler, log_name: str) -> bool:
    from shopman.orderman.models import Directive

    now = timezone.now()
    with transaction.atomic():
        directive = (
            Directive.objects.select_for_update(skip_locked=True)
            .filter(
                topic=topic,
                status=Directive.Status.QUEUED,
                payload__order_ref=order.ref,
                available_at__lte=now,
            )
            .order_by("available_at", "id")
            .first()
        )
        if directive is None:
            return False
        directive.status = Directive.Status.RUNNING
        directive.attempts += 1
        directive.started_at = now
        directive.save(update_fields=["status", "attempts", "started_at", "updated_at"])

    try:
        handler.handle(message=directive, ctx={"actor": "customer_surface"})
        directive.refresh_from_db()
        if directive.status == Directive.Status.RUNNING:
            directive.status = Directive.Status.DONE
            directive.error_code = ""
            directive.last_error = ""
            directive.save(update_fields=["status", "error_code", "last_error", "updated_at"])
        order.refresh_from_db()
        return directive.status == Directive.Status.DONE
    except DirectiveTerminalError as exc:
        logger.warning(
            "%s_terminal order=%s directive=%s error=%s",
            log_name,
            order.ref,
            directive.pk,
            exc,
        )
        directive.status = Directive.Status.FAILED
        directive.error_code = "terminal"
        directive.last_error = str(exc)[:500]
        directive.save(update_fields=["status", "error_code", "last_error", "updated_at"])
        return False
    except DirectiveTransientError as exc:
        logger.warning(
            "%s_transient order=%s directive=%s error=%s",
            log_name,
            order.ref,
            directive.pk,
            exc,
        )
        directive.status = Directive.Status.QUEUED
        directive.error_code = "transient"
        directive.available_at = timezone.now() + timedelta(seconds=30)
        directive.last_error = str(exc)[:500]
        directive.save(update_fields=["status", "error_code", "available_at", "last_error", "updated_at"])
        return False
    except Exception as exc:
        logger.exception("%s_failed order=%s directive=%s", log_name, order.ref, directive.pk)
        directive.status = Directive.Status.QUEUED
        directive.error_code = "transient"
        directive.available_at = timezone.now() + timedelta(seconds=30)
        directive.last_error = str(exc)[:500]
        directive.save(update_fields=["status", "error_code", "available_at", "last_error", "updated_at"])
        return False


def requires_payment_gate(order) -> bool:
    """Return True when the customer must complete payment before tracking."""
    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method not in {"pix", "card"}:
        return False
    if order.status != "confirmed":
        return False
    expires_at = _parse_payment_deadline(payment.get("expires_at"))
    if expires_at and timezone.now() >= expires_at:
        return False

    status = str(get_payment_status(order) or payment.get("status") or "").lower()
    if payment_service.has_sufficient_captured_payment(order) is True:
        return False
    if method == "card" and status == "authorized":
        return False
    return True


def _parse_payment_deadline(value) -> datetime | None:
    if not value:
        return None
    dt = parse_datetime(str(value))
    if dt is None:
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if not timezone.is_aware(dt):
        return timezone.make_aware(dt)
    return dt


def ensure_payment_intent(order) -> bool:
    """Ensure a digital payment order has a Payman intent before payment UI.

    This is a recovery guard for stale/misconfigured data. The customer-facing
    storefront routes PIX/card orders to the payment page immediately, so a
    missing intent must be repaired before payment actions are shown.
    ``payment_service.initiate`` is idempotent and remains the only writer.
    """
    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method not in {"pix", "card"}:
        return False
    if payment.get("intent_ref"):
        return True
    if method == "pix" and not _payment_can_start(order):
        return False

    payment_service.initiate(order)
    return bool(((order.data or {}).get("payment") or {}).get("intent_ref"))


def _payment_can_start(order) -> bool:
    if order.status != "new":
        return True
    try:
        from shopman.shop.config import ChannelConfig

        cfg = ChannelConfig.for_channel(order.channel_ref)
    except Exception:
        logger.warning("payment_start_config_lookup_failed order=%s", order.ref, exc_info=True)
        return False
    return cfg.payment.timing != "post_commit"


def mock_confirm_payment(order) -> bool:
    """Drive the local mock payment confirmation flow."""
    return payment_service.mock_confirm(order)


def is_cancelled(order) -> bool:
    return order.status == "cancelled"


def can_cancel(order) -> bool:
    return payment_service.can_cancel(order)


def cancel(order) -> None:
    from shopman.shop.services.cancellation import cancel as cancel_order

    cancel_order(order, reason="customer_requested", actor="customer.self_cancel")


def confirm_received(order) -> bool:
    """Customer confirms a dispatched delivery arrived → mark delivered."""
    from shopman.shop.services import operator_orders

    return operator_orders.confirm_received(order, actor="customer.self_confirm")


def should_skip_confirmation(order) -> bool:
    """True when the channel auto-confirms and confirmation page should redirect."""
    if not order.channel_ref:
        return False

    try:
        from shopman.shop.config import ChannelConfig

        cfg = ChannelConfig.for_channel(order.channel_ref).confirmation
        return cfg.mode == "auto_confirm"
    except Exception:
        logger.warning("confirmation_config_lookup_failed order=%s", order.ref, exc_info=True)
        return False


def add_reorder_items(
    request,
    order,
    *,
    cart_service=None,
    channel_ref: str = DEFAULT_CHANNEL_REF,
) -> list[str]:
    """Add previous order items to the cart and return display names skipped."""
    from shopman.shop.services.cart import CartUnavailableError

    if cart_service is None:
        msg = "cart_service is required for customer reorder mutations"
        raise ValueError(msg)

    skipped: list[str] = []

    for item in order.items.all():
        product = _sellable_product(item.sku)
        if product is None:
            skipped.append(item.sku)
            continue

        price_q = _price_q(product, channel_ref=channel_ref)
        try:
            cart_service.add_item(
                request,
                sku=item.sku,
                qty=int(item.qty),
                unit_price_q=price_q,
                name=product.name,
                is_d1=False,
            )
        except CartUnavailableError:
            skipped.append(product.name or item.sku)
        except Exception:
            logger.warning("reorder_add_item_failed order=%s sku=%s", order.ref, item.sku, exc_info=True)
            skipped.append(product.name or item.sku)

    return skipped


def _sellable_product(sku: str):
    from shopman.offerman.models import Product

    product = Product.objects.filter(sku=sku, is_published=True).first()
    if product and product.is_sellable:
        return product
    return None


def _session_can_access_order(request, order_ref: str) -> bool:
    if not hasattr(request, "session"):
        return False
    return str(order_ref) in {
        str(ref)
        for ref in (request.session.get(ORDER_ACCESS_SESSION_KEY) or [])
        if ref
    }


def _customer_identity_from_info(customer_info) -> tuple[str | None, str | None]:
    customer_ref = None
    try:
        from shopman.shop.projections.customer_context import customer_ref_by_uuid

        customer_ref = customer_ref_by_uuid(customer_info.uuid)
    except Exception:
        logger.warning(
            "customer_order_access_customer_ref_lookup_failed customer_uuid=%s",
            getattr(customer_info, "uuid", None),
            exc_info=True,
        )
    return customer_ref, getattr(customer_info, "phone", None)


def _customer_identity_from_user(user) -> tuple[str | None, str | None]:
    try:
        from shopman.doorman.models import CustomerUser
        from shopman.guestman.models import Customer

        link = CustomerUser.objects.filter(user=user).first()
        if link is None:
            return None, None
        customer = Customer.objects.filter(uuid=link.customer_id, is_active=True).first()
        if customer is None:
            return None, None
        return customer.ref, customer.phone
    except Exception:
        logger.warning(
            "customer_order_access_user_lookup_failed user=%s",
            getattr(user, "pk", None),
            exc_info=True,
        )
        return None, None


def _same_phone(left: str, right: str) -> bool:
    try:
        from shopman.utils.phone import normalize_phone

        return normalize_phone(left) == normalize_phone(right)
    except Exception:
        logger.debug("customer_orders._same_phone degraded; using fallback", exc_info=True)
        return str(left).strip() == str(right).strip()


def customer_identity_filter(
    *,
    customer_ref: str | None = None,
    phone: str | None = None,
):
    query = Q()
    if customer_ref:
        query |= Q(data__customer_ref=customer_ref)
    if phone:
        query |= Q(handle_type="phone", handle_ref=phone)
    return query if query.children else None


def _price_q(product, *, channel_ref: str) -> int:
    from shopman.offerman.models import ListingItem

    item = (
        ListingItem.objects.filter(
            listing__ref=channel_ref,
            listing__is_active=True,
            product=product,
            is_published=True,
        )
        .order_by("-min_qty")
        .first()
    )
    if item:
        return item.price_q
    return product.base_price_q or 0


__all__ = [
    "ACTIVE_STATUSES",
    "ORDER_ACCESS_SESSION_KEY",
    "active_order_count_for_customer",
    "active_order_count_for_phone",
    "add_reorder_items",
    "can_cancel",
    "cancel",
    "customer_can_access_order",
    "customer_identity_filter",
    "ensure_payment_intent",
    "get_accessible_order",
    "find_order",
    "get_order",
    "get_payment_status",
    "grant_order_access",
    "is_cancelled",
    "last_reorder_context",
    "mock_confirm_payment",
    "order_matches_customer_identity",
    "resolve_confirmation_timeout_if_due",
    "resolve_payment_timeout_if_due",
    "requires_payment_gate",
    "request_can_access_order",
    "should_skip_confirmation",
    "user_can_access_order",
]
