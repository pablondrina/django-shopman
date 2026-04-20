"""Shopman admin — Unfold admin for shop, rules, orders, alerts, KDS, closing, cash, channel, dashboard."""

from shopman.shop.admin.alerts import OperatorAlertAdmin  # noqa: F401
from shopman.shop.admin.cash_register import CashRegisterSessionAdmin  # noqa: F401
from shopman.shop.admin.channel import ChannelAdmin  # noqa: F401
from shopman.shop.admin.closing import DayClosingAdmin  # noqa: F401
from shopman.shop.admin.kds import KDSInstanceAdmin  # noqa: F401
from shopman.shop.admin.omotenashi import OmotenashiCopyAdmin  # noqa: F401
from shopman.shop.admin.orders import (  # noqa: F401
    ExpiryStatusFilter,
    FulfillmentOrderInline,
    SupplierFilter,
)
from shopman.shop.admin.rules import CouponAdmin, PromotionAdmin, RuleConfigAdmin  # noqa: F401
from shopman.shop.admin.shop import NotificationTemplateAdmin, ShopAdmin  # noqa: F401
