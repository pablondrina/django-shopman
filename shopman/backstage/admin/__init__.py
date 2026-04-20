"""Backstage admin — KDS, closing, alerts, cash register, dashboard, shop extensions."""

from shopman.backstage.admin.alerts import OperatorAlertAdmin  # noqa: F401
from shopman.backstage.admin.cash_register import CashRegisterSessionAdmin  # noqa: F401
from shopman.backstage.admin.closing import DayClosingAdmin  # noqa: F401
from shopman.backstage.admin.kds import KDSInstanceAdmin  # noqa: F401
from shopman.backstage.admin.shop_extensions import ShopAdminWithBackstageURLs  # noqa: F401
