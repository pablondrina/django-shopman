"""
Customers Merge - Customer deduplication via merge.

Merges a source customer into a target customer, consolidating all
related data (contact points, identifiers, preferences, etc.) and
deactivating the source. Requires strong evidence via Gate G6.

Usage:
    INSTALLED_APPS = [
        ...
        "customers",
        guestman.contrib.merge",
    ]

    from shopman.guestman.contrib.merge import MergeService

    MergeService.merge(
        source_customer=source,
        target_customer=target,
        evidence={"staff_override": True},
        actor="admin:pablo",
    )
"""


def __getattr__(name):
    if name == "MergeService":
        from shopman.guestman.contrib.merge.service import MergeService

        return MergeService
    if name == "MergeAudit":
        from shopman.guestman.contrib.merge.models import MergeAudit

        return MergeAudit
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["MergeService", "MergeAudit"]
