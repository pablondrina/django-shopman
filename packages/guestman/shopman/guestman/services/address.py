"""Address service.

All operations that modify >1 record use transaction.atomic().
"""

from django.db import transaction
from shopman.guestman.exceptions import CustomerError
from shopman.guestman.models import CustomerAddress
from shopman.guestman.services.customer import get


def addresses(customer_ref: str) -> list[CustomerAddress]:
    """List customer addresses."""
    cust = get(customer_ref)
    if not cust:
        return []
    return list(cust.addresses.all())


def default_address(customer_ref: str) -> CustomerAddress | None:
    """Return default address."""
    cust = get(customer_ref)
    if not cust:
        return None
    return cust.default_address


def has_address(customer_ref: str, formatted_address: str) -> bool:
    """Check whether the customer already has the exact address stored."""
    cust = get(customer_ref)
    if not cust:
        return False
    return cust.addresses.filter(formatted_address=formatted_address).exists()


def has_any_address(customer_ref: str) -> bool:
    """Check whether the customer has any address registered."""
    cust = get(customer_ref)
    if not cust:
        return False
    return cust.addresses.exists()


def get_address(customer_ref: str, address_id: int) -> CustomerAddress | None:
    """Return a specific address owned by the customer."""
    cust = get(customer_ref)
    if not cust:
        return None
    return cust.addresses.filter(pk=address_id).first()


def address_belongs_to_other_customer(customer_ref: str, address_id: int) -> bool:
    """Check whether an address exists but belongs to another customer."""
    return CustomerAddress.objects.filter(pk=address_id).exclude(
        customer__ref=customer_ref
    ).exists()


def add_address(
    customer_ref: str,
    label: str,
    formatted_address: str,
    place_id: str | None = None,
    components: dict | None = None,
    coordinates: tuple[float, float] | None = None,
    complement: str = "",
    delivery_instructions: str = "",
    label_custom: str = "",
    is_default: bool = False,
) -> CustomerAddress:
    """
    Add address to customer.

    Args:
        customer_ref: Customer ref
        label: "home", "work", "other"
        formatted_address: Complete formatted address
        place_id: Google Places ID
        components: Dict with street_number, route, neighborhood, etc.
        coordinates: (latitude, longitude)
        complement: Complement
        delivery_instructions: Delivery instructions
        label_custom: Custom label (when label="other")
        is_default: Set as default
    """
    cust = get(customer_ref)
    if not cust:
        raise CustomerError("CUSTOMER_NOT_FOUND", customer_ref=customer_ref)

    comp = components or {}

    # is_default=True triggers save() which demotes other defaults → atomic
    with transaction.atomic():
        addr = CustomerAddress.objects.create(
            customer=cust,
            label=label,
            label_custom=label_custom,
            place_id=place_id or "",
            formatted_address=formatted_address,
            street_number=comp.get("street_number", ""),
            route=comp.get("route", ""),
            neighborhood=comp.get("neighborhood", ""),
            city=comp.get("city", ""),
            state=comp.get("state", ""),
            state_code=comp.get("state_code", ""),
            postal_code=comp.get("postal_code", ""),
            country=comp.get("country", "Brasil"),
            country_code=comp.get("country_code", "BR"),
            latitude=coordinates[0] if coordinates else None,
            longitude=coordinates[1] if coordinates else None,
            complement=complement,
            delivery_instructions=delivery_instructions,
            is_default=is_default,
            is_verified=bool(place_id),
        )

    return addr


def set_default_address(customer_ref: str, address_id: int) -> CustomerAddress:
    """Set address as default."""
    cust = get(customer_ref)
    if not cust:
        raise CustomerError("CUSTOMER_NOT_FOUND", customer_ref=customer_ref)

    with transaction.atomic():
        try:
            addr = CustomerAddress.objects.get(pk=address_id, customer=cust)
        except CustomerAddress.DoesNotExist as e:
            raise CustomerError("ADDRESS_NOT_FOUND", address_id=address_id) from e

        addr.is_default = True
        addr.save()
        return addr


def update_address(customer_ref: str, address_id: int, **fields) -> CustomerAddress:
    """Update an existing address owned by the customer."""
    cust = get(customer_ref)
    if not cust:
        raise CustomerError("CUSTOMER_NOT_FOUND", customer_ref=customer_ref)

    try:
        addr = CustomerAddress.objects.get(pk=address_id, customer=cust)
    except CustomerAddress.DoesNotExist as e:
        raise CustomerError("ADDRESS_NOT_FOUND", address_id=address_id) from e

    updatable_fields = {
        "label",
        "label_custom",
        "formatted_address",
        "route",
        "street_number",
        "neighborhood",
        "city",
        "state",
        "state_code",
        "postal_code",
        "country",
        "country_code",
        "complement",
        "delivery_instructions",
        "is_default",
    }
    updates: list[str] = []
    for key, value in fields.items():
        if key in updatable_fields and hasattr(addr, key) and getattr(addr, key) != value:
            setattr(addr, key, value)
            updates.append(key)

    if updates:
        addr.save(update_fields=updates)
    return addr


def delete_address(customer_ref: str, address_id: int) -> bool:
    """Delete address."""
    cust = get(customer_ref)
    if not cust:
        raise CustomerError("CUSTOMER_NOT_FOUND", customer_ref=customer_ref)

    try:
        addr = CustomerAddress.objects.get(pk=address_id, customer=cust)
        addr.delete()
        return True
    except CustomerAddress.DoesNotExist as e:
        raise CustomerError("ADDRESS_NOT_FOUND", address_id=address_id) from e


def delete_all_addresses(customer_ref: str) -> int:
    """Delete all addresses belonging to the customer."""
    cust = get(customer_ref)
    if not cust:
        raise CustomerError("CUSTOMER_NOT_FOUND", customer_ref=customer_ref)
    deleted, _ = cust.addresses.all().delete()
    return deleted
