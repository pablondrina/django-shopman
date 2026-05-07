"""Customer-facing order reads and commands.

Storefront and API surfaces should use this module instead of importing
Orderman, Guestman, or Offerman models directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.utils.monetary import format_money

from shopman.shop.projections.types import ORDER_STATUS_COLORS, ORDER_STATUS_LABELS_PT
from shopman.shop.services import payment as payment_service

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset({"new", "confirmed", "preparing", "ready", "dispatched"})
CANCELLABLE_STATUSES = frozenset({"new", "confirmed"})
DEFAULT_CHANNEL_REF = "web"
ORDER_ACCESS_SESSION_KEY = "shopman_order_access_refs"
MAX_SESSION_ORDER_ACCESS_REFS = 20


@dataclass(frozen=True)
class OrderHistorySummary:
    """Canonical compact order summary consumed by customer projections."""

    ref: str
    created_at: Any
    total_q: int
    status: str
    status_label: str
    status_color: str
    item_count: int


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

    identity = _customer_identity_filter(customer_ref=customer_ref, phone=phone)
    if identity is None:
        return 0
    return Order.objects.filter(identity, status__in=ACTIVE_STATUSES).distinct().count()


def active_order_count_for_phone(phone: str) -> int:
    """Count active orders for the customer phone used by account badges."""
    return active_order_count_for_customer(phone=phone)


def history_summaries_for_customer(
    *,
    customer_ref: str | None = None,
    phone: str | None = None,
    filter_param: str = "todos",
    limit: int = 50,
) -> tuple[OrderHistorySummary, ...]:
    """Return order summaries for one authenticated customer identity.

    ``customer_ref`` is the canonical sealed link. ``phone`` is accepted as the
    external handle for orders that entered through phone-based surfaces, so
    history, account, badges, loyalty and quick reorder do not contradict each
    other when the same customer is resolved from different entry points.
    """
    try:
        from shopman.orderman.models import Order

        identity = _customer_identity_filter(customer_ref=customer_ref, phone=phone)
        if identity is None:
            return ()

        qs = Order.objects.filter(identity).distinct().order_by("-created_at")
        qs = _apply_history_filter(qs, filter_param)
        return _summaries_from_orders(qs[:limit])
    except Exception:
        logger.warning(
            "customer_order_history_failed customer_ref=%s phone=%s",
            customer_ref,
            phone,
            exc_info=True,
        )
        return ()


def history_summaries_for_phone(
    phone: str,
    *,
    filter_param: str = "todos",
    limit: int = 50,
) -> tuple[OrderHistorySummary, ...]:
    """Return canonical order summaries for a phone, degrading to an empty tuple."""
    return history_summaries_for_customer(
        phone=phone,
        filter_param=filter_param,
        limit=limit,
    )


def history_summaries_for_customer_ref(
    customer_ref: str,
    *,
    limit: int = 10,
) -> tuple[OrderHistorySummary, ...]:
    """Return canonical order summaries for a customer ref."""
    return history_summaries_for_customer(customer_ref=customer_ref, limit=limit)


def order_history_for_phone(phone: str, *, limit: int = 20) -> list[dict]:
    """Return API-ready customer order history for the authenticated account API."""
    return [
        {
            "ref": order.ref,
            "created_at": order.created_at,
            "total_display": f"R$ {format_money(order.total_q)}",
            "status": order.status,
            "status_label": order.status_label,
        }
        for order in history_summaries_for_phone(phone, limit=limit)
    ]


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

        identity = _customer_identity_filter(customer_ref=customer.ref, phone=customer.phone)
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
        msg = "cart_service is required for customer reorder commands"
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
        from shopman.shop.services.customer_context import customer_ref_by_uuid

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
        return str(left).strip() == str(right).strip()


def _customer_identity_filter(
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


def _apply_history_filter(qs, filter_param: str):
    if filter_param == "ativos":
        return qs.filter(status__in=ACTIVE_STATUSES)
    if filter_param == "anteriores":
        return qs.exclude(status__in=ACTIVE_STATUSES)
    return qs


def _summaries_from_orders(orders) -> tuple[OrderHistorySummary, ...]:
    return tuple(
        OrderHistorySummary(
            ref=order.ref,
            created_at=order.created_at,
            total_q=order.total_q,
            status=order.status,
            status_label=ORDER_STATUS_LABELS_PT.get(order.status, order.status),
            status_color=ORDER_STATUS_COLORS.get(
                order.status,
                "bg-surface-alt text-on-surface/60 border border-outline",
            ),
            item_count=order.items.count(),
        )
        for order in orders
    )


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
    "OrderHistorySummary",
    "active_order_count_for_customer",
    "active_order_count_for_phone",
    "add_reorder_items",
    "can_cancel",
    "cancel",
    "customer_can_access_order",
    "ensure_payment_intent",
    "get_accessible_order",
    "find_order",
    "get_order",
    "get_payment_status",
    "grant_order_access",
    "history_summaries_for_customer",
    "history_summaries_for_phone",
    "history_summaries_for_customer_ref",
    "is_cancelled",
    "last_reorder_context",
    "mock_confirm_payment",
    "order_matches_customer_identity",
    "order_history_for_phone",
    "resolve_payment_timeout_if_due",
    "requires_payment_gate",
    "request_can_access_order",
    "should_skip_confirmation",
    "user_can_access_order",
]
