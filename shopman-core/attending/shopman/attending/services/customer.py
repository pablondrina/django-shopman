"""Customer service - core CRUD and validation.

All write operations that touch >1 record use transaction.atomic().
"""

import logging
from dataclasses import dataclass

from django.db import transaction

from shopman.attending.models import Customer, CustomerGroup
from shopman.attending.signals import customer_created, customer_updated

logger = logging.getLogger(__name__)


@dataclass
class CustomerValidation:
    """Customer validation result."""

    valid: bool
    ref: str
    customer_id: int | None = None
    name: str | None = None
    group_ref: str | None = None
    listing_code: str | None = None
    default_address: dict | None = None
    error_code: str | None = None
    message: str | None = None


def get(ref: str) -> Customer | None:
    """Get customer by unique ref."""
    try:
        return Customer.objects.select_related("group").get(ref=ref, is_active=True)
    except Customer.DoesNotExist:
        return None


def get_by_uuid(uuid: str) -> Customer | None:
    """Get customer by UUID."""
    try:
        return Customer.objects.select_related("group").get(uuid=uuid, is_active=True)
    except Customer.DoesNotExist:
        return None


def get_by_document(document: str) -> Customer | None:
    """Get customer by document (CPF/CNPJ)."""
    doc_normalized = "".join(filter(str.isdigit, document))
    try:
        return Customer.objects.select_related("group").get(
            document=doc_normalized, is_active=True
        )
    except Customer.DoesNotExist:
        return None


def get_by_phone(phone: str) -> Customer | None:
    """Get customer by phone (exact match on normalized E.164)."""
    from shopman.utils.phone import normalize_phone

    phone_normalized = normalize_phone(phone)
    if not phone_normalized:
        return None
    try:
        return Customer.objects.select_related("group").get(
            phone=phone_normalized, is_active=True
        )
    except Customer.DoesNotExist:
        return None
    except Customer.MultipleObjectsReturned:
        return Customer.objects.filter(
            phone=phone_normalized, is_active=True
        ).first()


def get_by_email(email: str) -> Customer | None:
    """Get customer by email."""
    try:
        return Customer.objects.select_related("group").get(
            email__iexact=email, is_active=True
        )
    except Customer.DoesNotExist:
        return None
    except Customer.MultipleObjectsReturned:
        return Customer.objects.filter(
            email__iexact=email, is_active=True
        ).select_related("group").order_by("-updated_at").first()


def validate(ref: str) -> CustomerValidation:
    """Validate customer and return complete info for Session."""
    cust = get(ref)

    if not cust:
        return CustomerValidation(
            valid=False,
            ref=ref,
            error_code="CUSTOMER_NOT_FOUND",
            message=f"Customer '{ref}' not found",
        )

    default_addr = cust.default_address
    addr_dict = None
    if default_addr:
        addr_dict = {
            "label": default_addr.display_label,
            "formatted_address": default_addr.formatted_address,
            "short_address": default_addr.short_address,
            "complement": default_addr.complement,
            "latitude": float(default_addr.latitude) if default_addr.latitude else None,
            "longitude": (
                float(default_addr.longitude) if default_addr.longitude else None
            ),
        }

    return CustomerValidation(
        valid=True,
        ref=ref,
        customer_id=cust.id,
        name=cust.name,
        group_ref=cust.group.ref if cust.group else None,
        listing_code=cust.listing_code,
        default_address=addr_dict,
    )


def get_listing_code(ref: str) -> str | None:
    """Return customer's listing_code (for Offerman)."""
    cust = get(ref)
    if cust:
        return cust.listing_code
    return None


def search(query: str, limit: int = 20, offset: int = 0) -> list[Customer]:
    """Search customers by name, ref, document, phone, or email."""
    from django.db.models import Q

    qs = Customer.objects.filter(is_active=True)

    if query:
        qs = qs.filter(
            Q(ref__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(document__icontains=query)
            | Q(phone__icontains=query)
            | Q(email__icontains=query)
        )

    return list(qs.select_related("group").order_by("ref")[offset:offset + limit])


def groups() -> list[CustomerGroup]:
    """List all customer groups."""
    return list(CustomerGroup.objects.all())


def create(
    ref: str,
    first_name: str,
    last_name: str = "",
    customer_type: str = "individual",
    document: str = "",
    email: str = "",
    phone: str = "",
    group_ref: str | None = None,
    **kwargs,
) -> Customer:
    """Create a new customer."""
    group = None
    if group_ref:
        try:
            group = CustomerGroup.objects.get(ref=group_ref)
        except CustomerGroup.DoesNotExist:
            pass

    with transaction.atomic():
        cust = Customer.objects.create(
            ref=ref,
            first_name=first_name,
            last_name=last_name,
            customer_type=customer_type,
            document="".join(filter(str.isdigit, document)),
            email=email,
            phone=phone,
            group=group,
            **kwargs,
        )

    customer_created.send(sender=Customer, customer=cust)
    return cust


UPDATABLE_FIELDS = {
    "first_name",
    "last_name",
    "customer_type",
    "document",
    "email",
    "phone",
    "group",
    "notes",
    "metadata",
    "is_active",
    "source_system",
}


def update(ref: str, **fields) -> Customer | None:
    """Update customer fields (only whitelisted fields are accepted)."""
    cust = get(ref)
    if not cust:
        return None

    changes = {}
    for key, value in fields.items():
        if key not in UPDATABLE_FIELDS:
            continue
        if hasattr(cust, key):
            old_value = getattr(cust, key)
            if old_value != value:
                changes[key] = {"old": old_value, "new": value}
            setattr(cust, key, value)

    cust.save()
    if changes:
        customer_updated.send(sender=Customer, customer=cust, changes=changes)
    return cust
