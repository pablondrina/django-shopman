"""Shopman admin — Unfold admin for shop, rules, orders, channel."""

from shopman.shop.admin.channel import ChannelAdmin  # noqa: F401
from shopman.shop.admin.omotenashi import OmotenashiCopyAdmin  # noqa: F401
from shopman.shop.admin.orders import (  # noqa: F401
    ExpiryStatusFilter,
    FulfillmentOrderInline,
    SupplierFilter,
)
from shopman.shop.admin.rules import RuleConfigAdmin  # noqa: F401
from shopman.shop.admin.shop import NotificationTemplateAdmin, ShopAdmin  # noqa: F401
