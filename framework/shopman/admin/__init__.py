"""Shopman admin — Unfold admin for shop, rules, orders, alerts, KDS, closing, dashboard."""

from shopman.admin.alerts import OperatorAlertAdmin  # noqa: F401
from shopman.admin.closing import DayClosingAdmin  # noqa: F401
from shopman.admin.kds import KDSInstanceAdmin  # noqa: F401
from shopman.admin.orders import (  # noqa: F401
    ExpiryStatusFilter,
    FulfillmentOrderInline,
    SupplierFilter,
)
from shopman.admin.rules import CouponAdmin, PromotionAdmin, RuleConfigAdmin  # noqa: F401
from shopman.admin.shop import ShopAdmin  # noqa: F401
