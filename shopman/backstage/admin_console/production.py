"""Production pilot page rendered inside the Unfold Admin shell."""

from __future__ import annotations

import json

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.template.loader import render_to_string
from django.urls import reverse

from shopman.backstage.projections.production import resolve_production_access
from shopman.backstage.services import production as production_service
from shopman.backstage.views.production import (
    handle_production_post,
    render_production_surface,
)

TEMPLATE = "admin_console/production/index.html"
BULK_RESULT_TEMPLATE = "admin_console/production/partials/bulk_create_result.html"


def production_console_view(request: HttpRequest) -> HttpResponse:
    """Render the production board as an Admin/Unfold custom operational page."""
    request.current_app = admin.site.name

    access = resolve_production_access(request.user)
    if not access.can_access_board:
        messages.error(request, "Sem permissao para acessar producao.")
        return HttpResponseRedirect(reverse("admin:index"))

    if request.method == "POST":
        return handle_production_post(
            request,
            access,
            redirect_url_name="admin_console_production",
        )

    context = {
        **admin.site.each_context(request),
        "title": "Producao",
        "subtitle": "Piloto Admin/Unfold",
        "pilot_mode": True,
        "legacy_production_url": reverse("backstage:production"),
        "work_orders_url": reverse("admin:craftsman_workorder_changelist"),
        "reports_url": reverse("backstage:production_reports"),
        "dashboard_url": reverse("backstage:production_dashboard"),
        "bulk_create_url": reverse("admin_console_production_bulk_create"),
    }
    return render_production_surface(
        request,
        access,
        template_name=TEMPLATE,
        extra_context=context,
    )


def production_console_bulk_create_view(request: HttpRequest) -> HttpResponse:
    """Create suggested work orders from the Admin/Unfold pilot page."""
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)

    access = resolve_production_access(request.user)
    if not (access.can_manage_all or access.can_edit_planned):
        return HttpResponseForbidden("Voce nao tem permissao para esta acao.")

    if request.content_type == "application/json":
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return _bulk_result(request, error="Dados invalidos", status=400)
        target_date_str = body.get("date")
        orders_data = body.get("orders", [])
    else:
        target_date_str = request.POST.get("date")
        recipe_refs = request.POST.getlist("recipe_ref")
        quantities = request.POST.getlist("quantity")
        orders_data = [
            {"recipe_ref": recipe_ref, "quantity": quantity}
            for recipe_ref, quantity in zip(recipe_refs, quantities, strict=False)
        ]

    if not orders_data:
        return _bulk_result(request, error="Nenhuma ordem informada", status=422)

    result = production_service.apply_suggestions(
        target_date_value=target_date_str,
        entries=orders_data,
    )
    return _bulk_result(
        request,
        created=result.created,
        errors=result.errors,
        target_date=result.target_date,
    )


def _bulk_result(
    request: HttpRequest,
    *,
    created=None,
    errors=None,
    target_date=None,
    error: str | None = None,
    status: int = 200,
) -> HttpResponse:
    return HttpResponse(
        render_to_string(
            BULK_RESULT_TEMPLATE,
            {
                "created": created or [],
                "errors": errors or [],
                "target_date": target_date,
                "error": error,
            },
            request=request,
        ),
        status=status,
    )
