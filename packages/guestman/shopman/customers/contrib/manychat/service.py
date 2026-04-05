"""Manychat sync service."""

from shopman.customers.models import Customer
from shopman.customers.contrib.identifiers.models import CustomerIdentifier, IdentifierType


class ManychatService:
    """
    Service for Manychat integration.

    Uses @classmethod for extensibility (see spec 000 section 12.1).
    """

    @classmethod
    def sync_subscriber(
        cls,
        subscriber_data: dict,
        source_system: str = "manychat",
    ) -> tuple[Customer, bool]:
        """
        Sync a Manychat subscriber to Customers.

        Args:
            subscriber_data: Manychat subscriber data with fields like:
                - id: Manychat subscriber ID
                - first_name: First name
                - last_name: Last name
                - phone: Phone number
                - email: Email
                - ig_id: Instagram ID (optional)
                - ig_username: Instagram username (optional)
                - fb_id: Facebook ID (optional)
                - wa_phone: WhatsApp phone (optional)
                - custom_fields: Dict of custom fields (optional)
            source_system: Source identifier

        Returns:
            Tuple of (Customer, created: bool)
        """
        manychat_id = subscriber_data.get("id")
        if not manychat_id:
            raise ValueError("Subscriber data must contain 'id' field")

        # Try to find existing customer by Manychat ID
        customer = cls._find_by_manychat_id(manychat_id)

        if customer:
            # Update existing customer
            cls._update_customer(customer, subscriber_data)
            return customer, False

        # Try to find by other identifiers
        customer = cls._find_by_identifiers(subscriber_data)

        if customer:
            # Link Manychat ID to existing customer
            cls._add_manychat_identifiers(customer, subscriber_data, source_system)
            cls._update_customer(customer, subscriber_data)
            return customer, False

        # Create new customer
        customer = cls._create_customer(subscriber_data, source_system)
        cls._add_manychat_identifiers(customer, subscriber_data, source_system)
        return customer, True

    @classmethod
    def _find_by_manychat_id(cls, manychat_id: str) -> Customer | None:
        """Find customer by Manychat ID."""
        try:
            ident = CustomerIdentifier.objects.select_related("customer").get(
                identifier_type=IdentifierType.MANYCHAT,
                identifier_value=manychat_id,
            )
            return ident.customer if ident.customer.is_active else None
        except CustomerIdentifier.DoesNotExist:
            return None

    @classmethod
    def _find_by_identifiers(cls, data: dict) -> Customer | None:
        """Try to find customer by phone, email, or other identifiers."""
        # Try phone
        if data.get("phone"):
            phone = cls._normalize_phone(data["phone"])
            try:
                ident = CustomerIdentifier.objects.select_related("customer").get(
                    identifier_type=IdentifierType.PHONE,
                    identifier_value=phone,
                )
                return ident.customer if ident.customer.is_active else None
            except CustomerIdentifier.DoesNotExist:
                pass

        # Try email
        if data.get("email"):
            email = data["email"].lower().strip()
            try:
                ident = CustomerIdentifier.objects.select_related("customer").get(
                    identifier_type=IdentifierType.EMAIL,
                    identifier_value=email,
                )
                return ident.customer if ident.customer.is_active else None
            except CustomerIdentifier.DoesNotExist:
                pass

        # Try WhatsApp phone
        if data.get("wa_phone"):
            phone = cls._normalize_phone(data["wa_phone"])
            try:
                ident = CustomerIdentifier.objects.select_related("customer").get(
                    identifier_type=IdentifierType.WHATSAPP,
                    identifier_value=phone,
                )
                return ident.customer if ident.customer.is_active else None
            except CustomerIdentifier.DoesNotExist:
                pass

        return None

    @classmethod
    def _create_customer(cls, data: dict, source_system: str) -> Customer:
        """Create new customer from Manychat data."""
        import hashlib

        # Generate ref from Manychat ID
        hash_value = hashlib.md5(data["id"].encode()).hexdigest()[:8].upper()
        ref = f"MC-{hash_value}"

        return Customer.objects.create(
            ref=ref,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            source_system=source_system,
            metadata={"manychat_custom_fields": data.get("custom_fields", {})},
        )

    @classmethod
    def _update_customer(cls, customer: Customer, data: dict) -> None:
        """Update customer with Manychat data."""
        updated = False

        if data.get("first_name") and not customer.first_name:
            customer.first_name = data["first_name"]
            updated = True

        if data.get("last_name") and not customer.last_name:
            customer.last_name = data["last_name"]
            updated = True

        if data.get("email") and not customer.email:
            customer.email = data["email"]
            updated = True

        if data.get("phone") and not customer.phone:
            customer.phone = data["phone"]
            updated = True

        # Update custom fields in metadata
        if data.get("custom_fields"):
            if "manychat_custom_fields" not in customer.metadata:
                customer.metadata["manychat_custom_fields"] = {}
            customer.metadata["manychat_custom_fields"].update(data["custom_fields"])
            updated = True

        if updated:
            customer.save()

    @classmethod
    def _add_manychat_identifiers(
        cls,
        customer: Customer,
        data: dict,
        source_system: str,
    ) -> None:
        """Add Manychat-related identifiers to customer."""
        identifiers_to_add = []

        # Manychat ID
        if data.get("id"):
            identifiers_to_add.append(
                (IdentifierType.MANYCHAT, data["id"], True)
            )

        # Phone
        if data.get("phone"):
            identifiers_to_add.append(
                (IdentifierType.PHONE, cls._normalize_phone(data["phone"]), False)
            )

        # Email
        if data.get("email"):
            identifiers_to_add.append(
                (IdentifierType.EMAIL, data["email"].lower().strip(), False)
            )

        # Instagram
        if data.get("ig_id"):
            identifiers_to_add.append(
                (IdentifierType.INSTAGRAM, data["ig_id"], False)
            )

        # Facebook
        if data.get("fb_id"):
            identifiers_to_add.append(
                (IdentifierType.FACEBOOK, data["fb_id"], False)
            )

        # WhatsApp
        if data.get("wa_phone"):
            identifiers_to_add.append(
                (IdentifierType.WHATSAPP, cls._normalize_phone(data["wa_phone"]), False)
            )

        # Telegram
        if data.get("tg_id"):
            identifiers_to_add.append(
                (IdentifierType.TELEGRAM, data["tg_id"], False)
            )

        for id_type, id_value, is_primary in identifiers_to_add:
            CustomerIdentifier.objects.get_or_create(
                identifier_type=id_type,
                identifier_value=id_value,
                defaults={
                    "customer": customer,
                    "is_primary": is_primary,
                    "source_system": source_system,
                },
            )

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normalize phone number. Delegates to centralized normalize_phone."""
        from shopman.customers.utils import normalize_phone

        return normalize_phone(phone)
