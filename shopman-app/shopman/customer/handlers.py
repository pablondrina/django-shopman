"""
Shopman Customer Handlers — Processa directives customer.ensure.

Garante que o cliente existe no Guestman após commit do pedido.

Suporta múltiplos canais:
- WhatsApp (Manychat): busca por ExternalIdentity(provider="manychat")
- Balcão (PDV): anônimo, CPF-only, ou phone
- iFood: busca por ExternalIdentity(provider="ifood")
- Web/outros: busca por phone (fluxo padrão)
"""

from __future__ import annotations

import logging
import uuid

from shopman.ordering.models import Directive

logger = logging.getLogger(__name__)


def _guestman_available() -> bool:
    """Check if Guestman is installed."""
    try:
        from shopman.attending.services import customer as _svc  # noqa: F401

        return True
    except ImportError:
        return False


def _identifiers_available() -> bool:
    """Check if Guestman identifiers contrib is installed."""
    try:
        from shopman.attending.contrib.identifiers.models import CustomerIdentifier  # noqa: F401

        return True
    except ImportError:
        return False


def _get_customer_service():
    """Import and return attending.services.customer module. Easily mockable."""
    from shopman.attending.services import customer as svc

    return svc


class CustomerEnsureHandler:
    """
    Garante que o cliente existe no Guestman após o commit.

    Topic: customer.ensure

    Idempotente: se customer já existe, apenas vincula.
    """

    topic = "customer.ensure"

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        payload = message.payload
        order_ref = payload.get("order_ref")

        if not order_ref:
            logger.warning("CustomerEnsureHandler: missing order_ref")
            message.status = "failed"
            message.last_error = "missing order_ref"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        try:
            order = Order.objects.select_related("channel").get(ref=order_ref)
        except Order.DoesNotExist:
            logger.warning("CustomerEnsureHandler: order %s not found", order_ref)
            message.status = "failed"
            message.last_error = f"Order not found: {order_ref}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        if not _guestman_available():
            logger.warning("CustomerEnsureHandler: Guestman not installed, skipping.")
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # Dispatch based on channel/handle_type
        channel_ref = order.channel.ref if order.channel else ""
        handle_type = order.handle_type or ""

        try:
            if handle_type == "manychat":
                customer, created = self._handle_manychat(order)
            elif channel_ref == "ifood":
                customer, created = self._handle_ifood(order)
            elif channel_ref == "balcao":
                customer, created = self._handle_balcao(order)
            else:
                customer, created = self._handle_phone(order)
        except _SkipAnonymous:
            logger.info(
                "CustomerEnsureHandler: anonymous order %s, skipping.", order_ref,
            )
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return
        except Exception as exc:
            logger.error(
                "CustomerEnsureHandler: failed for order %s: %s", order_ref, exc,
            )
            message.status = "failed"
            message.last_error = f"Customer ensure failed: {exc}"[:500]
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # Link order to customer
        if customer and order.data.get("customer_ref") != customer.ref:
            order.data["customer_ref"] = customer.ref
            order.save(update_fields=["data", "updated_at"])

        if customer:
            # Save delivery address if present
            delivery_address = (
                order.data.get("delivery_address")
                or order.snapshot.get("data", {}).get("delivery_address")
            )
            if delivery_address:
                _save_delivery_address(customer, delivery_address)

            # Create TimelineEvent
            _create_timeline_event(customer, order)

            # Update RFM insights
            _update_insights(customer.ref)

        action = "created" if created else "linked"
        logger.info(
            "CustomerEnsureHandler: %s customer %s for order %s",
            action, customer.ref if customer else "anonymous", order_ref,
        )
        message.status = "done"
        message.save(update_fields=["status", "updated_at"])

    # ------------------------------------------------------------------ channel strategies

    def _handle_manychat(self, order) -> tuple:
        """WhatsApp: busca/cria Customer via Manychat subscriber_id."""
        customer_data = _get_customer_data(order)
        subscriber_id = order.handle_ref
        name = customer_data.get("name", "")

        if not subscriber_id:
            raise _SkipAnonymous()

        # Try to find by Manychat ExternalIdentity
        customer = _find_by_identifier("manychat", subscriber_id)

        if customer:
            _maybe_update_name(customer, name)
            return customer, False

        CustomerService = _get_customer_service()

        phone_raw = customer_data.get("phone", "")
        phone = _normalize_phone_safe(phone_raw)

        # Try to find by phone first (dedup)
        if phone:
            customer = CustomerService.get_by_phone(phone)
            if customer:
                _add_identifier(customer, "manychat", subscriber_id, is_primary=True)
                _maybe_update_name(customer, name)
                return customer, False

        # Create new customer
        first_name, last_name = _split_name(name)
        code = f"MC-{uuid.uuid4().hex[:8].upper()}"
        customer = CustomerService.create(
            ref=code,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            customer_type="individual",
            source_system="manychat",
        )

        _add_identifier(customer, "manychat", subscriber_id, is_primary=True)

        logger.info(
            "CustomerEnsureHandler: created manychat customer %s for subscriber %s",
            customer.ref, subscriber_id,
        )
        return customer, True

    def _handle_ifood(self, order) -> tuple:
        """iFood: busca/cria Customer via external_id do iFood."""
        customer_data = _get_customer_data(order)
        ifood_order_id = order.external_ref or order.handle_ref
        name = customer_data.get("name", "")

        if not ifood_order_id:
            raise _SkipAnonymous()

        customer = _find_by_identifier("ifood", ifood_order_id)

        if customer:
            _maybe_update_name(customer, name)
            return customer, False

        CustomerService = _get_customer_service()

        first_name, last_name = _split_name(name)
        code = f"IF-{uuid.uuid4().hex[:8].upper()}"
        customer = CustomerService.create(
            ref=code,
            first_name=first_name or "iFood",
            last_name=last_name or f"#{ifood_order_id[:8]}",
            customer_type="individual",
            source_system="ifood",
        )

        _add_identifier(customer, "ifood", ifood_order_id, is_primary=True)

        logger.info(
            "CustomerEnsureHandler: created ifood customer %s for order %s",
            customer.ref, ifood_order_id,
        )
        return customer, True

    def _handle_balcao(self, order) -> tuple:
        """Balcão: anônimo, CPF-only, ou phone."""
        customer_data = _get_customer_data(order)
        phone_raw = customer_data.get("phone", "")
        cpf = customer_data.get("cpf", "")
        name = customer_data.get("name", "")

        # Case 1: phone presente → fluxo normal
        if phone_raw:
            return self._handle_phone(order)

        # Case 2: CPF sem phone
        if cpf:
            CustomerService = _get_customer_service()

            cpf_normalized = "".join(filter(str.isdigit, cpf))
            if not cpf_normalized:
                raise _SkipAnonymous()

            customer = CustomerService.get_by_document(cpf_normalized)
            if customer:
                _maybe_update_name(customer, name)
                return customer, False

            customer = _find_by_identifier("cpf", cpf_normalized)
            if customer:
                _maybe_update_name(customer, name)
                return customer, False

            first_name, last_name = _split_name(name)
            code = f"CLI-{uuid.uuid4().hex[:8].upper()}"
            customer = CustomerService.create(
                ref=code,
                first_name=first_name or "Cliente",
                last_name=last_name or f"CPF {cpf_normalized[-4:]}",
                document=cpf_normalized,
                customer_type="individual",
                source_system="balcao",
            )

            _add_identifier(customer, "cpf", cpf_normalized, is_primary=True)

            logger.info(
                "CustomerEnsureHandler: created CPF customer %s for balcão",
                customer.ref,
            )
            return customer, True

        # Case 3: anônimo (sem phone nem CPF)
        raise _SkipAnonymous()

    def _handle_phone(self, order) -> tuple:
        """Fluxo padrão: busca/cria Customer por phone."""
        CustomerService = _get_customer_service()

        customer_data = _get_customer_data(order)
        phone_raw = customer_data.get("phone") or order.handle_ref
        name = customer_data.get("name", "")

        if not phone_raw:
            raise _SkipAnonymous()

        phone = _normalize_phone_safe(phone_raw)
        if not phone:
            raise _SkipAnonymous()

        customer = CustomerService.get_by_phone(phone)
        created = False

        if not customer:
            first_name, last_name = _split_name(name)
            code = f"CLI-{uuid.uuid4().hex[:8].upper()}"
            customer = CustomerService.create(
                ref=code,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                customer_type="individual",
                source_system="shopman",
            )
            created = True
            logger.info(
                "CustomerEnsureHandler: created customer %s for order %s",
                customer.ref, order.ref,
            )
        else:
            _maybe_update_name(customer, name)

        return customer, created


class _SkipAnonymous(Exception):
    """Raised when order is anonymous — no customer to create."""


# ------------------------------------------------------------------ helpers


def _get_customer_data(order) -> dict:
    """Extract customer data from order snapshot or data."""
    return (
        order.snapshot.get("data", {}).get("customer", {})
        or order.data.get("customer", {})
    )


def _split_name(full_name: str) -> tuple[str, str]:
    """Split a full name into first and last name."""
    parts = full_name.strip().split(None, 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    return first, last


def _normalize_phone_safe(phone_raw: str) -> str:
    """Normalize phone, returning raw on failure."""
    if not phone_raw:
        return ""
    try:
        from shopman.utils.phone import normalize_phone

        return normalize_phone(phone_raw)
    except Exception:
        return phone_raw


def _maybe_update_name(customer, name: str) -> None:
    """Update customer name if currently empty and name is provided."""
    if name and not customer.first_name:
        CustomerService = _get_customer_service()

        first_name, last_name = _split_name(name)
        try:
            CustomerService.update(
                customer.ref,
                first_name=first_name,
                last_name=last_name,
            )
        except Exception as exc:
            logger.warning(
                "CustomerEnsureHandler: could not update name for %s: %s",
                customer.ref, exc,
            )


def _find_by_identifier(provider: str, external_id: str):
    """Find Customer by ExternalIdentity (CustomerIdentifier)."""
    if not _identifiers_available():
        return None

    from shopman.attending.contrib.identifiers.models import CustomerIdentifier

    type_map = {
        "manychat": "manychat",
        "ifood": "ifood",
        "cpf": "cpf",
    }
    id_type = type_map.get(provider, provider)

    try:
        ident = CustomerIdentifier.objects.select_related("customer").get(
            identifier_type=id_type,
            identifier_value=str(external_id),
            customer__is_active=True,
        )
        return ident.customer
    except CustomerIdentifier.DoesNotExist:
        return None


def _add_identifier(customer, provider: str, value: str, *, is_primary: bool = False) -> None:
    """Add identifier to customer (idempotent)."""
    if not _identifiers_available():
        return

    from shopman.attending.contrib.identifiers.models import CustomerIdentifier

    CustomerIdentifier.objects.get_or_create(
        identifier_type=provider,
        identifier_value=str(value),
        defaults={
            "customer": customer,
            "is_primary": is_primary,
            "source_system": "shopman",
        },
    )


def _create_timeline_event(customer, order) -> None:
    """Create a timeline event for the order placement."""
    try:
        from shopman.attending.contrib.timeline.models import TimelineEvent

        exists = TimelineEvent.objects.filter(
            customer=customer,
            event_type="order",
            reference=f"order:{order.ref}",
        ).exists()

        if not exists:
            from shopman.utils.monetary import format_money

            TimelineEvent.objects.create(
                customer=customer,
                event_type="order",
                title=f"Pedido {order.ref}",
                description=f"Pedido realizado via {order.channel.name} — R$ {format_money(order.total_q)}",
                channel=order.channel.ref,
                reference=f"order:{order.ref}",
                metadata={
                    "order_ref": order.ref,
                    "total_q": order.total_q,
                    "items_count": order.items.count(),
                },
                created_by="shopman.customer.ensure",
            )
    except ImportError:
        pass  # timeline contrib not installed
    except Exception as exc:
        logger.warning("CustomerEnsureHandler: timeline event failed: %s", exc)


def _save_delivery_address(customer, address_text: str) -> None:
    """Save delivery address to Guestman if not already present."""
    try:
        from shopman.attending.models import CustomerAddress

        exists = CustomerAddress.objects.filter(
            customer=customer,
            formatted_address=address_text,
        ).exists()
        if exists:
            return

        has_addresses = CustomerAddress.objects.filter(customer=customer).exists()

        CustomerAddress.objects.create(
            customer=customer,
            label="home",
            formatted_address=address_text,
            is_default=not has_addresses,
        )
        logger.info(
            "CustomerEnsureHandler: saved address for customer %s", customer.ref,
        )
    except ImportError:
        pass  # address model not available
    except Exception as exc:
        logger.warning("CustomerEnsureHandler: address save failed: %s", exc)


def _update_insights(customer_ref: str) -> None:
    """Recalculate customer insights (RFM) after order."""
    try:
        from shopman.attending.contrib.insights.service import InsightService

        InsightService.recalculate(customer_ref)
    except ImportError:
        pass  # insights contrib not installed
    except Exception as exc:
        logger.warning("CustomerEnsureHandler: insight recalculation failed: %s", exc)
