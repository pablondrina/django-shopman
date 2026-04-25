"""Home view — institutional landing page."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_sameorigin

REORDER_MIN_DAYS = 7  # show reorder card only after this many days since last order


@method_decorator(xframe_options_sameorigin, name="dispatch")
class HomeView(View):
    """Institutional home page — brand vitrine.

    SAMEORIGIN permite embed no admin (WP-S4 preview iframe), sem abrir a página a clickjacking de terceiros.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        last_order_ref, last_order_items = self._reorder_context(request)
        context = {
            "last_order_ref": last_order_ref,
            "last_order_items": last_order_items,
        }
        return render(request, "storefront/home.html", context)

    @staticmethod
    def _reorder_context(request: HttpRequest) -> tuple[str | None, list[dict]]:
        """Return (last_order_ref, items) for the quick-reorder card.

        Only non-empty when the customer is authenticated, has a previous order,
        and their last order was more than REORDER_MIN_DAYS ago. Items come from
        Order.snapshot["items"] — the sealed snapshot written at commit time.
        """
        customer_info = getattr(request, "customer", None)
        if customer_info is None:
            return None, []
        try:
            from django.utils import timezone
            from shopman.guestman.services import customer as customer_service
            from shopman.orderman.models import Order

            cust = customer_service.get_by_uuid(str(customer_info.uuid))
            if cust is None:
                return None, []
            last = (
                Order.objects
                .filter(data__customer_ref=cust.ref)
                .order_by("-created_at")
                .values("ref", "snapshot", "created_at")
                .first()
            )
            if not last:
                return None, []

            days_since = (timezone.now() - last["created_at"]).days
            if days_since <= REORDER_MIN_DAYS:
                return None, []

            items = last["snapshot"].get("items") or []
            return last["ref"], items
        except Exception:
            return None, []
