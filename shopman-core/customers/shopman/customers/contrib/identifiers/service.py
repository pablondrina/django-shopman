"""Identifier service for lookup and management."""

from django.db import transaction

from shopman.customers.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.customers.models import Customer


class IdentifierService:
    """
    Service for customer identifier operations.

    Uses @classmethod for extensibility (see spec 000 section 12.1).
    """

    @classmethod
    def find_by_identifier(
        cls,
        identifier_type: str,
        identifier_value: str,
        include_native_fields: bool = True,
    ) -> Customer | None:
        """
        Find customer by identifier.

        Args:
            identifier_type: Type (phone, email, instagram, etc.)
            identifier_value: Value to search
            include_native_fields: Also search Customer.email/phone fields

        Returns:
            Customer if found, None otherwise
        """
        normalized = cls._normalize_value(identifier_type, identifier_value)

        # 1. CustomerIdentifier table (canonical source for multi-channel)
        try:
            ident = CustomerIdentifier.objects.select_related("customer").get(
                identifier_type=identifier_type,
                identifier_value=normalized,
            )
            if ident.customer.is_active:
                return ident.customer
        except CustomerIdentifier.DoesNotExist:
            pass

        # 2. Customer native fields (email, phone) - optional
        if include_native_fields:
            if identifier_type == IdentifierType.EMAIL:
                return Customer.objects.filter(
                    email__iexact=normalized, is_active=True
                ).first()
            elif identifier_type == IdentifierType.PHONE:
                # Phone is stored in E.164 format (with country code)
                # Legacy records without country code are handled by trying both
                customer = Customer.objects.filter(
                    phone=normalized, is_active=True
                ).first()
                if not customer and normalized.startswith("55"):
                    # Try legacy format (without country code)
                    customer = Customer.objects.filter(
                        phone=normalized[2:], is_active=True
                    ).first()
                return customer

        return None

    @classmethod
    def add_identifier(
        cls,
        customer_ref: str,
        identifier_type: str,
        identifier_value: str,
        is_primary: bool = False,
        source_system: str = "",
    ) -> CustomerIdentifier:
        """
        Add identifier to customer.

        Args:
            customer_ref: Customer ref
            identifier_type: Type (phone, email, instagram, etc.)
            identifier_value: Value to add
            is_primary: Mark as primary for this type
            source_system: Source of the identifier

        Returns:
            Created CustomerIdentifier

        Raises:
            Customer.DoesNotExist: If customer not found
        """
        customer = Customer.objects.get(ref=customer_ref, is_active=True)

        return CustomerIdentifier.objects.create(
            customer=customer,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            is_primary=is_primary,
            source_system=source_system,
        )

    @classmethod
    def find_or_create_customer(
        cls,
        identifier_type: str,
        identifier_value: str,
        defaults: dict | None = None,
    ) -> tuple[Customer, bool]:
        """
        Find customer by identifier or create new one.

        Args:
            identifier_type: Type (phone, email, instagram, etc.)
            identifier_value: Value to search/use
            defaults: Default values for new customer

        Returns:
            Tuple of (Customer, created: bool)
        """
        customer = cls.find_by_identifier(identifier_type, identifier_value)
        if customer:
            return customer, False

        # Create new customer + identifier atomically
        defaults = defaults or {}
        if "ref" not in defaults:
            defaults["ref"] = cls._generate_ref_from_identifier(
                identifier_type, identifier_value
            )

        with transaction.atomic():
            customer = Customer.objects.create(**defaults)
            cls.add_identifier(
                customer.ref,
                identifier_type,
                identifier_value,
                is_primary=True,
            )

        return customer, True

    @classmethod
    def get_identifiers(cls, customer_ref: str) -> list[CustomerIdentifier]:
        """Get all identifiers for a customer."""
        return list(
            CustomerIdentifier.objects.filter(
                customer__ref=customer_ref,
                customer__is_active=True,
            ).order_by("identifier_type", "-is_primary")
        )

    @classmethod
    def _normalize_value(cls, identifier_type: str, value: str) -> str:
        """Normalize identifier value based on type."""
        from shopman.customers.utils import normalize_phone

        if identifier_type in (IdentifierType.PHONE, IdentifierType.WHATSAPP):
            return normalize_phone(value)
        elif identifier_type == IdentifierType.EMAIL:
            return value.lower().strip()
        elif identifier_type == IdentifierType.INSTAGRAM:
            return normalize_phone(value, contact_type="instagram")
        return value.strip()

    @classmethod
    def _generate_ref_from_identifier(
        cls,
        identifier_type: str,
        identifier_value: str,
    ) -> str:
        """Generate customer ref from identifier."""
        import hashlib

        # Create a short hash
        hash_input = f"{identifier_type}:{identifier_value}"
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:8].upper()
        return f"CUST-{hash_value}"
