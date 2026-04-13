"""Timeline service — log and query customer interactions."""

import logging

from shopman.guestman.contrib.timeline.models import TimelineEvent
from shopman.guestman.models import Customer

logger = logging.getLogger(__name__)


class TimelineService:
    """
    Service for customer timeline operations.

    Uses @classmethod for extensibility (consistent with other contrib services).
    """

    @classmethod
    def log_event(
        cls,
        customer_ref: str,
        event_type: str,
        title: str,
        description: str = "",
        channel: str = "",
        reference: str = "",
        metadata: dict | None = None,
        created_by: str = "",
    ) -> TimelineEvent:
        """
        Record an interaction in the customer timeline.

        Args:
            customer_ref: Customer ref
            event_type: Type (order, contact, note, visit, loyalty, system)
            title: Short summary of the event
            description: Detailed description
            channel: Origin channel (whatsapp, pdv, ecommerce)
            reference: External reference (order:123, ticket:456)
            metadata: Extra data as JSON
            created_by: Who created the event

        Returns:
            Created TimelineEvent

        Raises:
            Customer.DoesNotExist: If customer not found
        """
        customer = Customer.objects.get(ref=customer_ref, is_active=True)

        return TimelineEvent.objects.create(
            customer=customer,
            event_type=event_type,
            title=title,
            description=description,
            channel=channel,
            reference=reference,
            metadata=metadata or {},
            created_by=created_by,
        )

    @classmethod
    def get_timeline(
        cls,
        customer_ref: str,
        limit: int = 50,
        event_type: str | None = None,
    ) -> list[TimelineEvent]:
        """
        Get customer timeline (most recent first).

        Args:
            customer_ref: Customer ref
            limit: Max events to return
            event_type: Filter by type (optional)

        Returns:
            List of TimelineEvent ordered by -created_at
        """
        qs = TimelineEvent.objects.filter(
            customer__ref=customer_ref,
            customer__is_active=True,
        )
        if event_type:
            qs = qs.filter(event_type=event_type)
        return list(qs[:limit])

    @classmethod
    def has_event(cls, customer_ref: str, event_type: str, reference: str) -> bool:
        """Check whether an event already exists for idempotent callers."""
        return TimelineEvent.objects.filter(
            customer__ref=customer_ref,
            customer__is_active=True,
            event_type=event_type,
            reference=reference,
        ).exists()

    @classmethod
    def get_recent_across_customers(
        cls,
        limit: int = 50,
        event_type: str | None = None,
    ) -> list[TimelineEvent]:
        """
        Get recent timeline events across all customers.

        Useful for CRM dashboards showing latest activity.

        Args:
            limit: Max events to return
            event_type: Filter by type (optional)

        Returns:
            List of TimelineEvent with customer pre-loaded
        """
        qs = TimelineEvent.objects.filter(
            customer__is_active=True,
        ).select_related("customer")
        if event_type:
            qs = qs.filter(event_type=event_type)
        return list(qs[:limit])
