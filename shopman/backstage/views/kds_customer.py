"""Customer-facing KDS status board."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from shopman.backstage.projections.kds import build_kds_customer_status
from shopman.shop.models import Shop


@require_GET
def kds_customer_board_view(request: HttpRequest) -> HttpResponse:
    """Render the public pickup status board."""
    return render(
        request,
        "runtime/kds_customer/board.html",
        {
            "board": build_kds_customer_status(),
            "shop": Shop.load(),
        },
    )


@require_GET
def kds_customer_board_orders_view(request: HttpRequest) -> HttpResponse:
    """Render the polling partial for the public pickup status board."""
    return render(
        request,
        "runtime/kds_customer/partials/orders.html",
        {"board": build_kds_customer_status()},
    )
