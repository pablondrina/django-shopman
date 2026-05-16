"""Shopman Utils — shared primitives and admin helpers for the Shopman suite."""

from shopman.utils.contrib.admin_unfold.badges import unfold_badge, unfold_badge_numeric
from shopman.utils.contrib.admin_unfold.tables import table_badge

__version__ = "0.3.0"

__all__ = ["table_badge", "unfold_badge", "unfold_badge_numeric"]
