"""Guestman identity services."""

from __future__ import annotations

from shopman.guestman.models import ContactPoint, Customer, ExternalIdentity


def ensure_contact_point(
    customer: Customer,
    *,
    type: str,
    value_normalized: str,
    is_primary: bool = True,
    is_verified: bool = False,
) -> ContactPoint:
    """Ensure a normalized contact point exists for the customer."""
    contact_point, created = ContactPoint.objects.get_or_create(
        customer=customer,
        type=type,
        value_normalized=value_normalized,
        defaults={
            "is_primary": is_primary,
            "is_verified": is_verified,
        },
    )
    updates: list[str] = []
    if not created:
        if is_primary and not contact_point.is_primary:
            contact_point.is_primary = True
            updates.append("is_primary")
        if is_verified and not contact_point.is_verified:
            contact_point.is_verified = True
            updates.append("is_verified")
        if updates:
            contact_point.save(update_fields=updates)
    return contact_point


def ensure_external_identity(
    customer: Customer,
    *,
    provider: str,
    external_id: str,
    metadata: dict | None = None,
) -> ExternalIdentity:
    """Ensure an external identity is linked to the customer."""
    identity, created = ExternalIdentity.objects.get_or_create(
        provider=provider,
        provider_uid=external_id,
        defaults={
            "customer": customer,
            "provider_meta": metadata or {},
        },
    )
    if identity.customer_id != customer.id:
        raise ValueError("External identity is already linked to another customer.")
    if not created and metadata is not None and identity.provider_meta != metadata:
        identity.provider_meta = metadata
        identity.save(update_fields=["provider_meta"])
    return identity
