"""
Shopman Guestman Adapter — Adapter para integração com Guestman.
"""

from __future__ import annotations

import logging
import threading

from shopman.identification.protocols import (
    AddressInfo,
    CustomerBackend,
    CustomerContext,
    CustomerInfo,
    CustomerValidationResult,
)

logger = logging.getLogger(__name__)


def _guestman_available() -> bool:
    """Check if Guestman is installed."""
    try:
        from shopman.attending.services import customer as CustomerService  # noqa: F811
        return True
    except ImportError:
        return False


class GuestmanBackend:
    """
    Adapter que conecta customer ao Guestman.
    """

    def get_customer(self, code: str) -> CustomerInfo | None:
        if not _guestman_available():
            logger.warning("get_customer: Guestman not installed")
            return None

        from shopman.attending.services import customer as CustomerService

        cust = CustomerService.get(code)
        if not cust:
            return None

        default_addr = None
        if cust.default_address:
            addr = cust.default_address
            default_addr = AddressInfo(
                label=addr.display_label,
                formatted_address=addr.formatted_address,
                short_address=addr.short_address,
                complement=addr.complement,
                delivery_instructions=getattr(addr, "delivery_instructions", None),
                latitude=float(addr.latitude) if addr.latitude else None,
                longitude=float(addr.longitude) if addr.longitude else None,
            )

        total_orders = 0
        is_vip = False
        is_at_risk = False
        favorite_products = []

        try:
            from shopman.attending.contrib.insights.service import InsightService
            insight = InsightService.get_insight(code)
            if insight:
                total_orders = insight.total_orders
                is_vip = insight.is_vip
                is_at_risk = insight.is_at_risk
                if insight.favorite_products:
                    favorite_products = [p.get("sku") for p in insight.favorite_products[:5] if p.get("sku")]
        except ImportError:
            pass

        return CustomerInfo(
            code=cust.ref,
            name=cust.name,
            customer_type=cust.customer_type,
            group_code=cust.group.code if cust.group else None,
            listing_code=cust.listing_code,
            phone=cust.phone,
            email=cust.email,
            default_address=default_addr,
            total_orders=total_orders,
            is_vip=is_vip,
            is_at_risk=is_at_risk,
            favorite_products=favorite_products,
        )

    def validate_customer(self, code: str) -> CustomerValidationResult:
        if not _guestman_available():
            return CustomerValidationResult(
                valid=False,
                code=code,
                error_code="GUESTMAN_NOT_INSTALLED",
                message="Guestman is not installed",
            )

        from shopman.attending.services import customer as CustomerService

        validation = CustomerService.validate(code)

        if not validation.valid:
            return CustomerValidationResult(
                valid=False,
                code=code,
                error_code=validation.error_code,
                message=validation.message,
            )

        cust_info = self.get_customer(code)

        return CustomerValidationResult(
            valid=True,
            code=code,
            info=cust_info,
        )

    def get_listing_code(self, customer_ref: str) -> str | None:
        if not _guestman_available():
            return None

        from shopman.attending.services import customer as CustomerService
        return CustomerService.get_listing_code(customer_ref)

    def get_customer_context(self, code: str) -> CustomerContext | None:
        if not _guestman_available():
            return None

        cust_info = self.get_customer(code)
        if not cust_info:
            return None

        prefs = {}
        try:
            from shopman.attending.contrib.preferences.service import PreferenceService
            prefs = PreferenceService.get_preferences_dict(code)
        except ImportError:
            pass

        recent_orders = []
        rfm_segment = None
        days_since = None

        try:
            from shopman.attending.contrib.insights.service import InsightService
            insight = InsightService.get_insight(code)
            if insight:
                rfm_segment = insight.rfm_segment
                days_since = insight.days_since_last_order

            from django.conf import settings
            from django.utils.module_loading import import_string

            guestman_settings = getattr(settings, "GUESTMAN", {})
            backend_path = guestman_settings.get("ORDER_HISTORY_BACKEND")
            if backend_path:
                backend_class = import_string(backend_path)
                backend = backend_class()
                orders = backend.get_customer_orders(code, limit=5)
                for o in orders:
                    recent_orders.append({
                        "order_ref": o.order_ref,
                        "ordered_at": o.ordered_at.isoformat(),
                        "total_q": o.total_q,
                        "channel_ref": o.channel_ref,
                        "items_count": o.items_count,
                    })
        except ImportError:
            pass

        recommended = cust_info.favorite_products[:3] if cust_info.favorite_products else []

        return CustomerContext(
            info=cust_info,
            preferences=prefs,
            recent_orders=recent_orders,
            rfm_segment=rfm_segment,
            days_since_last_order=days_since,
            recommended_products=recommended,
        )

    def record_order(self, customer_ref: str, order_data: dict) -> bool:
        if not _guestman_available():
            logger.warning("record_order: Guestman not installed")
            return False

        try:
            from shopman.attending.contrib.insights.service import InsightService
            InsightService.recalculate(customer_ref)
            return True
        except ImportError:
            return True
        except Exception as e:
            logger.warning("record_order: Failed for customer %s: %s", customer_ref, e)
            return False


# Singleton factory
_lock = threading.Lock()
_backend_instance: GuestmanBackend | None = None


def get_customer_backend() -> GuestmanBackend:
    """Return singleton instance of GuestmanBackend."""
    global _backend_instance
    if _backend_instance is None:
        with _lock:
            if _backend_instance is None:
                _backend_instance = GuestmanBackend()
    return _backend_instance


def reset_customer_backend() -> None:
    """Reset singleton (for tests)."""
    global _backend_instance
    _backend_instance = None
