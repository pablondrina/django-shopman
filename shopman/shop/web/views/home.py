"""Home view — institutional landing page."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_sameorigin


@method_decorator(xframe_options_sameorigin, name="dispatch")
class HomeView(View):
    """Institutional home page — brand vitrine.

    SAMEORIGIN permite embed no admin (WP-S4 preview iframe), sem abrir a página a clickjacking de terceiros.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        context = {"last_order_ref": self._last_order_ref(request)}
        return render(request, "storefront/home.html", context)

    @staticmethod
    def _last_order_ref(request: HttpRequest) -> str | None:
        """Resolve ref do último pedido do cliente logado para o quick-reorder."""
        customer_info = getattr(request, "customer", None)
        if customer_info is None:
            return None
        try:
            from shopman.guestman.services import customer as customer_service
            from shopman.orderman.models import Order

            cust = customer_service.get_by_uuid(str(customer_info.uuid))
            if cust is None:
                return None
            last = (
                Order.objects
                .filter(data__customer_ref=cust.ref)
                .order_by("-created_at")
                .values_list("ref", flat=True)
                .first()
            )
            return last
        except Exception:
            return None
