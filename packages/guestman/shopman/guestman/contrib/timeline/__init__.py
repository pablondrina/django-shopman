"""
Customers Timeline - Customer interaction history.

Records every meaningful interaction: orders, contacts, notes, system events.
Provides a unified chronological view per customer — essential for CRM.

Usage:
    INSTALLED_APPS = [
        ...
        "customers",
        guestman.contrib.timeline",
    ]

    from shopman.guestman.contrib.timeline import TimelineService

    TimelineService.log_event(customer_ref, "order", "Pedido #123 confirmado")
    events = TimelineService.get_timeline(customer_ref)
"""


def __getattr__(name):
    if name == "TimelineService":
        from shopman.guestman.contrib.timeline.service import TimelineService

        return TimelineService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["TimelineService"]
