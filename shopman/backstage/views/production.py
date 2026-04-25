"""Quick production registration + bulk create — admin custom views.

GET views consume projections from ``shopman.shop.projections.production``.
POST actions mutate state, then redirect (PRG pattern).
"""

from __future__ import annotations

import json
import logging
from datetime import date

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import reverse

from shopman.backstage.projections.production import build_production_board
from shopman.shop.services import production as production_service

logger = logging.getLogger(__name__)

TEMPLATE = "gestor/producao/index.html"
PERMISSION = "shop.manage_production"


def production_view(request, admin_site):
    """GET: form + today's WOs. POST: create + finish WO."""
    if not request.user.has_perm(PERMISSION):
        messages.error(request, "Sem permissão para registrar produção.")
        return HttpResponseRedirect(reverse("admin:index"))

    if request.method == "POST":
        return _handle_post(request, admin_site)

    return _render(request, admin_site)


def production_void_view(request, admin_site):
    """POST: void a WorkOrder."""
    if not request.user.has_perm(PERMISSION):
        messages.error(request, "Sem permissão.")
        return HttpResponseRedirect(reverse("admin:index"))

    if request.method != "POST":
        return HttpResponseRedirect(reverse("admin:shop_production"))

    wo_id = request.POST.get("wo_id")
    if not wo_id:
        messages.error(request, "Ordem não informada.")
        return HttpResponseRedirect(reverse("admin:shop_production"))

    try:
        wo_ref = production_service.void_work_order(
            wo_id,
            actor=f"admin:{request.user}",
        )
        messages.success(request, f"Ordem {wo_ref} estornada.")
    except Exception as exc:
        logger.warning("production_void_failed wo_id=%s: %s", wo_id, exc, exc_info=True)
        messages.error(request, f"Erro ao estornar: {exc}")

    return HttpResponseRedirect(reverse("admin:shop_production"))


def _handle_post(request, admin_site):
    """Create WorkOrder + finish immediately."""
    recipe_id = request.POST.get("recipe")
    quantity_raw = request.POST.get("quantity", "").strip()
    position_id = request.POST.get("position", "").strip()

    actor = f"admin:{request.user}"

    try:
        output_sku, wo_ref, quantity = production_service.quick_finish(
            recipe_id=recipe_id,
            quantity=quantity_raw,
            position_id=position_id,
            actor=actor,
        )

        messages.success(
            request,
            f"Produção registrada: {output_sku} × {quantity} ({wo_ref})",
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        logger.exception("Quick production failed")
        messages.error(request, f"Erro ao registrar produção: {exc}")

    return HttpResponseRedirect(reverse("admin:shop_production"))


def _render(request, admin_site):
    """Render the production page using projection."""
    date_param = (request.GET.get("date") or "").strip()
    try:
        selected_date = date.fromisoformat(date_param) if date_param else date.today()
    except ValueError:
        selected_date = date.today()
    position_ref = (request.GET.get("position_ref") or "").strip()
    operator_ref = (request.GET.get("operator_ref") or "").strip()

    board = build_production_board(
        selected_date=selected_date,
        position_ref=position_ref,
        operator_ref=operator_ref,
    )

    context = {
        **admin_site.each_context(request),
        "title": "Registro de Produção",
        "board": board,
        "recipes": board.recipes,
        "positions": board.positions,
        "default_position_id": board.default_position_pk,
        "today_wos": board.work_orders,
        "craft_summary": board.counts,
        "planned_queue": board.planned_queue,
        "started_queue": board.started_queue,
        "selected_position_ref": board.selected_position_ref,
        "selected_operator_ref": board.selected_operator_ref,
        "selected_date": selected_date,
    }
    return TemplateResponse(request, TEMPLATE, context)


# ── Bulk Create (from dashboard suggestions) ────────────────────────


def bulk_create_work_orders(request: HttpRequest) -> HttpResponse:
    """POST /gestor/producao/criar/ — bulk create WorkOrders from suggestions.

    Expects JSON body: {"date": "YYYY-MM-DD", "orders": [{"recipe_ref": "...", "quantity": N}, ...]}
    Returns HTMX partial with result summary.
    """
    if not request.user.has_perm(PERMISSION):
        return HttpResponse("Você não tem permissão para esta ação.", status=403)

    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)

    _PARTIAL = "gestor/producao/partials/bulk_create_result.html"

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(
            render_to_string(_PARTIAL, {"error": "Dados inválidos"}, request=request),
            status=400,
        )

    target_date_str = body.get("date")
    orders_data = body.get("orders", [])

    if not orders_data:
        return HttpResponse(
            render_to_string(_PARTIAL, {"error": "Nenhuma ordem informada"}, request=request),
            status=422,
        )

    result = production_service.bulk_plan(
        target_date_value=target_date_str,
        entries=orders_data,
    )

    return HttpResponse(
        render_to_string(
            _PARTIAL,
            {
                "created": result.created,
                "errors": result.errors,
                "target_date": result.target_date,
            },
            request=request,
        ),
    )
