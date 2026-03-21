"""Preference service for management."""

from decimal import Decimal
from typing import Any

from shopman.attending.contrib.preferences.models import CustomerPreference, PreferenceType
from shopman.attending.models import Customer


class PreferenceService:
    """
    Service for customer preference operations.

    Uses @classmethod for extensibility (see spec 000 section 12.1).
    """

    @classmethod
    def get_preference(
        cls,
        customer_ref: str,
        category: str,
        key: str,
    ) -> Any | None:
        """
        Get a specific preference value.

        Args:
            customer_ref: Customer ref
            category: Preference category
            key: Preference key

        Returns:
            Preference value or None if not found
        """
        try:
            pref = CustomerPreference.objects.get(
                customer__ref=customer_ref,
                customer__is_active=True,
                category=category,
                key=key,
            )
            return pref.value
        except CustomerPreference.DoesNotExist:
            return None

    @classmethod
    def set_preference(
        cls,
        customer_ref: str,
        category: str,
        key: str,
        value: Any,
        preference_type: str = PreferenceType.EXPLICIT,
        confidence: Decimal = Decimal("1.00"),
        source: str = "",
    ) -> CustomerPreference:
        """
        Set a preference value (create or update).

        Args:
            customer_ref: Customer ref
            category: Preference category
            key: Preference key
            value: Preference value
            preference_type: explicit, inferred, or restriction
            confidence: Confidence level (0.00 to 1.00)
            source: Source of the preference

        Returns:
            CustomerPreference instance

        Raises:
            Customer.DoesNotExist: If customer not found
        """
        customer = Customer.objects.get(ref=customer_ref, is_active=True)

        pref, _ = CustomerPreference.objects.update_or_create(
            customer=customer,
            category=category,
            key=key,
            defaults={
                "value": value,
                "preference_type": preference_type,
                "confidence": confidence,
                "source": source,
            },
        )
        return pref

    @classmethod
    def get_preferences(
        cls,
        customer_ref: str,
        category: str | None = None,
    ) -> list[CustomerPreference]:
        """
        Get all preferences for a customer.

        Args:
            customer_ref: Customer ref
            category: Optional category filter

        Returns:
            List of CustomerPreference
        """
        qs = CustomerPreference.objects.filter(
            customer__ref=customer_ref,
            customer__is_active=True,
        )
        if category:
            qs = qs.filter(category=category)
        return list(qs)

    @classmethod
    def get_preferences_dict(
        cls,
        customer_ref: str,
    ) -> dict[str, dict[str, Any]]:
        """
        Get all preferences as nested dict.

        Returns:
            {category: {key: value, ...}, ...}
        """
        prefs = cls.get_preferences(customer_ref)
        result: dict[str, dict[str, Any]] = {}
        for pref in prefs:
            if pref.category not in result:
                result[pref.category] = {}
            result[pref.category][pref.key] = pref.value
        return result

    @classmethod
    def delete_preference(
        cls,
        customer_ref: str,
        category: str,
        key: str,
    ) -> bool:
        """
        Delete a preference.

        Returns:
            True if deleted, False if not found
        """
        deleted, _ = CustomerPreference.objects.filter(
            customer__ref=customer_ref,
            customer__is_active=True,
            category=category,
            key=key,
        ).delete()
        return deleted > 0

    @classmethod
    def get_restrictions(cls, customer_ref: str) -> list[CustomerPreference]:
        """Get all restrictions for a customer."""
        return list(
            CustomerPreference.objects.filter(
                customer__ref=customer_ref,
                customer__is_active=True,
                preference_type=PreferenceType.RESTRICTION,
            )
        )
