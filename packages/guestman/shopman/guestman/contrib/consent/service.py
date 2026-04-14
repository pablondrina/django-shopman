"""Consent service — LGPD opt-in/opt-out management."""

import logging

from django.utils import timezone
from shopman.guestman.contrib.consent.models import (
    CommunicationConsent,
    ConsentStatus,
)
from shopman.guestman.models import Customer

logger = logging.getLogger(__name__)


class ConsentService:
    """
    Service for communication consent operations.

    Uses @classmethod for extensibility (consistent with other contrib services).
    """

    @classmethod
    def grant_consent(
        cls,
        customer_ref: str,
        channel: str,
        source: str = "",
        legal_basis: str = "consent",
        ip_address: str | None = None,
    ) -> CommunicationConsent:
        """
        Grant opt-in consent for a communication channel.

        Args:
            customer_ref: Customer code
            channel: Channel (whatsapp, email, sms, push)
            source: How consent was collected
            legal_basis: LGPD legal basis
            ip_address: IP at time of consent

        Returns:
            Updated CommunicationConsent

        Raises:
            Customer.DoesNotExist: If customer not found
        """
        customer = Customer.objects.get(ref=customer_ref, is_active=True)

        consent, _ = CommunicationConsent.objects.update_or_create(
            customer=customer,
            channel=channel,
            defaults={
                "status": ConsentStatus.OPTED_IN,
                "source": source,
                "legal_basis": legal_basis,
                "ip_address": ip_address,
                "consented_at": timezone.now(),
                "revoked_at": None,
            },
        )
        return consent

    @classmethod
    def revoke_consent(
        cls,
        customer_ref: str,
        channel: str,
    ) -> CommunicationConsent:
        """
        Revoke consent (opt-out) for a communication channel.

        Revocation is immediate. The revoked_at timestamp is preserved
        for audit trail.

        Args:
            customer_ref: Customer code
            channel: Channel to opt-out from

        Returns:
            Updated CommunicationConsent

        Raises:
            Customer.DoesNotExist: If customer not found
        """
        customer = Customer.objects.get(ref=customer_ref, is_active=True)

        consent, _ = CommunicationConsent.objects.update_or_create(
            customer=customer,
            channel=channel,
            defaults={
                "status": ConsentStatus.OPTED_OUT,
                "revoked_at": timezone.now(),
            },
        )
        return consent

    @classmethod
    def has_consent(cls, customer_ref: str, channel: str) -> bool:
        """
        Check if customer has active consent for a channel.

        Returns False for pending, opted_out, or missing consent.
        This is the primary check before sending any marketing communication.

        Args:
            customer_ref: Customer code
            channel: Channel to check

        Returns:
            True only if status is opted_in
        """
        try:
            consent = CommunicationConsent.objects.get(
                customer__ref=customer_ref,
                customer__is_active=True,
                channel=channel,
            )
            return consent.status == ConsentStatus.OPTED_IN
        except CommunicationConsent.DoesNotExist:
            return False

    @classmethod
    def get_consents(cls, customer_ref: str) -> list[CommunicationConsent]:
        """Get all consent records for a customer."""
        return list(
            CommunicationConsent.objects.filter(
                customer__ref=customer_ref,
                customer__is_active=True,
            )
        )

    @classmethod
    def get_opted_in_channels(cls, customer_ref: str) -> list[str]:
        """Get list of channels where customer has active consent."""
        return list(
            CommunicationConsent.objects.filter(
                customer__ref=customer_ref,
                customer__is_active=True,
                status=ConsentStatus.OPTED_IN,
            ).values_list("channel", flat=True)
        )

    @classmethod
    def get_marketable_customers(cls, channel: str) -> list[str]:
        """
        Get customer codes with active consent for a channel.

        Useful for building marketing campaign audiences.

        Args:
            channel: Channel to filter by

        Returns:
            List of customer codes
        """
        return list(
            CommunicationConsent.objects.filter(
                channel=channel,
                status=ConsentStatus.OPTED_IN,
                customer__is_active=True,
            ).values_list("customer__ref", flat=True)
        )
