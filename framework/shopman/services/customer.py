"""
Customer resolution service.

Core: customers.services.customer (get_by_phone, create, etc.)
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def ensure(order) -> None:
    """
    Resolve or create the customer for the order.

    Strategy varies by channel type:
    - manychat → resolve by subscriber_id
    - ifood → resolve by iFood order ID
    - balcao → resolve by CPF or phone
    - default → resolve by phone

    Saves customer_ref in order.data["customer_ref"].

    SYNC — needs customer_ref before proceeding.
    """
    if not _customers_available():
        return

    channel_ref = order.channel.ref if order.channel else ""
    handle_type = getattr(order, "handle_type", "") or ""

    try:
        if handle_type == "manychat":
            customer = _handle_manychat(order)
        elif channel_ref == "ifood":
            customer = _handle_ifood(order)
        elif channel_ref == "balcao":
            customer = _handle_balcao(order)
        else:
            customer = _handle_phone(order)
    except _SkipAnonymous:
        return
    except Exception as exc:
        logger.warning("customer.ensure: failed for order %s: %s", order.ref, exc)
        return

    if customer and order.data.get("customer_ref") != customer.ref:
        order.data["customer_ref"] = customer.ref
        order.save(update_fields=["data", "updated_at"])

    if customer:
        _save_delivery_address(customer, order)
        _create_timeline_event(customer, order)
        _update_insights(customer.ref)


# ── strategy per channel ──


def _handle_manychat(order):
    subscriber_id = order.handle_ref
    customer_data = _get_customer_data(order)
    name = customer_data.get("name", "")

    if not subscriber_id:
        raise _SkipAnonymous()

    customer = _find_by_identifier("manychat", subscriber_id)
    if customer:
        _maybe_update_name(customer, name)
        return customer

    svc = _get_customer_service()
    phone = _normalize_phone_safe(customer_data.get("phone", ""))

    if phone:
        customer = svc.get_by_phone(phone)
        if customer:
            _add_identifier(customer, "manychat", subscriber_id, is_primary=True)
            _maybe_update_name(customer, name)
            return customer

    first_name, last_name = _split_name(name)
    ref = f"MC-{uuid.uuid4().hex[:8].upper()}"
    customer = svc.create(
        ref=ref, first_name=first_name, last_name=last_name,
        phone=phone, customer_type="individual", source_system="manychat",
    )
    _add_identifier(customer, "manychat", subscriber_id, is_primary=True)
    return customer


def _handle_ifood(order):
    customer_data = _get_customer_data(order)
    ifood_order_id = order.external_ref or order.handle_ref
    name = customer_data.get("name", "")

    if not ifood_order_id:
        raise _SkipAnonymous()

    customer = _find_by_identifier("ifood", ifood_order_id)
    if customer:
        _maybe_update_name(customer, name)
        return customer

    svc = _get_customer_service()
    first_name, last_name = _split_name(name)
    ref = f"IF-{uuid.uuid4().hex[:8].upper()}"
    customer = svc.create(
        ref=ref, first_name=first_name or "iFood",
        last_name=last_name or f"#{ifood_order_id[:8]}",
        customer_type="individual", source_system="ifood",
    )
    _add_identifier(customer, "ifood", ifood_order_id, is_primary=True)
    return customer


def _handle_balcao(order):
    customer_data = _get_customer_data(order)
    phone_raw = customer_data.get("phone", "")
    cpf = customer_data.get("cpf", "")
    name = customer_data.get("name", "")

    if phone_raw:
        return _handle_phone(order)

    if cpf:
        svc = _get_customer_service()
        cpf_normalized = "".join(filter(str.isdigit, cpf))
        if not cpf_normalized:
            raise _SkipAnonymous()

        customer = svc.get_by_document(cpf_normalized)
        if customer:
            _maybe_update_name(customer, name)
            return customer

        customer = _find_by_identifier("cpf", cpf_normalized)
        if customer:
            _maybe_update_name(customer, name)
            return customer

        first_name, last_name = _split_name(name)
        ref = f"CLI-{uuid.uuid4().hex[:8].upper()}"
        customer = svc.create(
            ref=ref, first_name=first_name or "Cliente",
            last_name=last_name or f"CPF {cpf_normalized[-4:]}",
            document=cpf_normalized, customer_type="individual", source_system="balcao",
        )
        _add_identifier(customer, "cpf", cpf_normalized, is_primary=True)
        return customer

    raise _SkipAnonymous()


def _handle_phone(order):
    svc = _get_customer_service()
    customer_data = _get_customer_data(order)
    phone_raw = customer_data.get("phone") or order.handle_ref
    name = customer_data.get("name", "")

    if not phone_raw:
        raise _SkipAnonymous()

    phone = _normalize_phone_safe(phone_raw)
    if not phone:
        raise _SkipAnonymous()

    customer = svc.get_by_phone(phone)
    if customer:
        _maybe_update_name(customer, name)
        return customer

    first_name, last_name = _split_name(name)
    ref = f"CLI-{uuid.uuid4().hex[:8].upper()}"
    customer = svc.create(
        ref=ref, first_name=first_name, last_name=last_name,
        phone=phone, customer_type="individual", source_system="shopman",
    )
    return customer


# ── helpers ──


class _SkipAnonymous(Exception):
    pass


def _customers_available() -> bool:
    try:
        from shopman.guestman.services import customer as _svc  # noqa: F401
        return True
    except ImportError:
        return False


def _get_customer_service():
    from shopman.guestman.services import customer as svc
    return svc


def _get_customer_data(order) -> dict:
    return order.snapshot.get("data", {}).get("customer", {}) or order.data.get("customer", {})


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(None, 1)
    return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "")


def _normalize_phone_safe(phone_raw: str) -> str:
    if not phone_raw:
        return ""
    try:
        from shopman.utils.phone import normalize_phone
        return normalize_phone(phone_raw)
    except Exception:
        return phone_raw


def _maybe_update_name(customer, name: str) -> None:
    if name and not customer.first_name:
        svc = _get_customer_service()
        first_name, last_name = _split_name(name)
        try:
            svc.update(customer.ref, first_name=first_name, last_name=last_name)
        except Exception:
            pass


def _find_by_identifier(provider: str, external_id: str):
    try:
        from shopman.guestman.contrib.identifiers.models import CustomerIdentifier
    except ImportError:
        return None

    try:
        ident = CustomerIdentifier.objects.select_related("customer").get(
            identifier_type=provider, identifier_value=str(external_id),
            customer__is_active=True,
        )
        return ident.customer
    except CustomerIdentifier.DoesNotExist:
        return None


def _add_identifier(customer, provider: str, value: str, *, is_primary: bool = False) -> None:
    try:
        from shopman.guestman.contrib.identifiers.models import CustomerIdentifier
    except ImportError:
        return

    CustomerIdentifier.objects.get_or_create(
        identifier_type=provider, identifier_value=str(value),
        defaults={"customer": customer, "is_primary": is_primary, "source_system": "shopman"},
    )


def _save_delivery_address(customer, order) -> None:
    delivery_address = (
        order.data.get("delivery_address")
        or order.snapshot.get("data", {}).get("delivery_address")
    )
    if not delivery_address:
        return

    try:
        from shopman.guestman.models import CustomerAddress

        if CustomerAddress.objects.filter(customer=customer, formatted_address=delivery_address).exists():
            return
        has_addresses = CustomerAddress.objects.filter(customer=customer).exists()
        CustomerAddress.objects.create(
            customer=customer, label="home", formatted_address=delivery_address,
            is_default=not has_addresses,
        )
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("customer.ensure: address save failed: %s", exc)


def _create_timeline_event(customer, order) -> None:
    try:
        from shopman.guestman.contrib.timeline.models import TimelineEvent
        from shopman.utils.monetary import format_money

        exists = TimelineEvent.objects.filter(
            customer=customer, event_type="order", reference=f"order:{order.ref}",
        ).exists()
        if exists:
            return

        TimelineEvent.objects.create(
            customer=customer, event_type="order", title=f"Pedido {order.ref}",
            description=f"Pedido realizado via {order.channel.name} — R$ {format_money(order.total_q)}",
            channel=order.channel.ref, reference=f"order:{order.ref}",
            metadata={"order_ref": order.ref, "total_q": order.total_q},
            created_by="shopman.services.customer.ensure",
        )
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("customer.ensure: timeline event failed: %s", exc)


def _update_insights(customer_ref: str) -> None:
    try:
        from shopman.guestman.contrib.insights.service import InsightService
        InsightService.recalculate(customer_ref)
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("customer.ensure: insight recalculation failed: %s", exc)
