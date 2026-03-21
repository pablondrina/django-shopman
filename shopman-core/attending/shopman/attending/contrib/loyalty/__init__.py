"""
Attending Loyalty - Simple points/stamps loyalty program.

Native loyalty program (not plugin). Supports both points-based and
stamp-based programs — configurable per deployment.

Usage:
    INSTALLED_APPS = [
        ...
        "attending",
        "attending.contrib.loyalty",
    ]

    from shopman.attending.contrib.loyalty import LoyaltyService

    LoyaltyService.enroll("CUST-001")
    LoyaltyService.earn_points("CUST-001", 100, "Pedido #123")
    balance = LoyaltyService.get_balance("CUST-001")
    LoyaltyService.redeem_points("CUST-001", 50, "Desconto aplicado")
"""


def __getattr__(name):
    if name == "LoyaltyService":
        from shopman.attending.contrib.loyalty.service import LoyaltyService

        return LoyaltyService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["LoyaltyService"]
