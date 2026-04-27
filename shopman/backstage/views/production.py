"""Quick production registration + bulk create — admin custom views.

GET views consume projections from ``shopman.shop.projections.production``.
POST actions mutate state, then redirect (PRG pattern).
"""

from __future__ import annotations

import json
import logging
from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import reverse

from shopman.backstage.projections.production import (
    build_production_board,
    resolve_production_access,
)
from shopman.shop.services import production as production_service

logger = logging.getLogger(__name__)

TEMPLATE = "gestor/producao/index.html"


def production_view(request, admin_site):
    """GET: form + today's WOs. POST: create + finish WO."""
    access = resolve_production_access(request.user)
    if not access.can_access_board:
        messages.error(request, "Sem permissão para acessar produção.")
        return HttpResponseRedirect(reverse("admin:index"))

    if request.method == "POST":
        return _handle_post(request, admin_site, access)

    return _render(request, admin_site, access)


def production_void_view(request, admin_site):
    """POST: void a WorkOrder."""
    access = resolve_production_access(request.user)
    if not (access.can_manage_all or access.can_edit_planned or access.can_edit_started):
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


def _handle_post(request, admin_site, access):
    """Mutate production through the canonical Craftsman lifecycle."""
    action = (request.POST.get("action") or "quick_finish").strip()
    actor = f"admin:{request.user}"

    try:
        if action == "plan":
            is_suggestion = request.POST.get("source") == "suggested"
            can_plan = access.can_edit_planned or (is_suggestion and access.can_edit_suggested)
            if not can_plan:
                messages.error(request, "Sem permissão para planejar produção.")
            else:
                output_sku, wo_ref, quantity = production_service.plan_work_order(
                    recipe_id=request.POST.get("recipe"),
                    quantity=request.POST.get("quantity", "").strip(),
                    target_date_value=request.POST.get("target_date", "").strip(),
                    position_id=request.POST.get("position", "").strip(),
                    operator_ref=request.POST.get("operator_ref", "").strip(),
                    actor=actor,
                )
                messages.success(request, f"Planejado: {output_sku} × {quantity} ({wo_ref})")
        elif action == "adjust":
            if not access.can_edit_planned:
                messages.error(request, "Sem permissão para ajustar planejamento.")
            else:
                wo_ref, quantity = production_service.adjust_work_order(
                    work_order_id=request.POST.get("wo_id"),
                    quantity=request.POST.get("quantity", "").strip(),
                    reason=request.POST.get("reason", "").strip(),
                    actor=actor,
                )
                messages.success(request, f"Planejamento ajustado: {wo_ref} × {quantity}")
        elif action == "start":
            if not access.can_edit_started:
                messages.error(request, "Sem permissão para iniciar produção.")
            else:
                wo_ref, quantity = production_service.start_work_order(
                    work_order_id=request.POST.get("wo_id"),
                    quantity=request.POST.get("quantity", "").strip(),
                    position_id=request.POST.get("position", "").strip(),
                    operator_ref=request.POST.get("operator_ref", "").strip(),
                    note=request.POST.get("note", "").strip(),
                    actor=actor,
                )
                messages.success(request, f"Produção iniciada: {wo_ref} × {quantity}")
        elif action == "finish":
            if not access.can_edit_finished:
                messages.error(request, "Sem permissão para concluir produção.")
            else:
                wo_ref, quantity = production_service.finish_work_order(
                    work_order_id=request.POST.get("wo_id"),
                    quantity=request.POST.get("quantity", "").strip(),
                    actor=actor,
                )
                messages.success(request, f"Produção concluída: {wo_ref} × {quantity}")
        elif action == "quick_finish":
            if not access.can_edit_finished:
                messages.error(request, "Sem permissão para informar produção concluída.")
            else:
                output_sku, wo_ref, quantity = production_service.quick_finish(
                    recipe_id=request.POST.get("recipe"),
                    quantity=request.POST.get("quantity", "").strip(),
                    position_id=request.POST.get("position", "").strip(),
                    actor=actor,
                )
                messages.success(
                    request,
                    f"Entrada direta registrada: {output_sku} × {quantity} ({wo_ref})",
                )
        else:
            messages.error(request, "Ação de produção inválida.")
    except ValueError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        logger.exception("Production action failed action=%s", action)
        messages.error(request, f"Erro ao registrar produção: {exc}")

    return HttpResponseRedirect(_production_redirect(request))


def _render(request, admin_site, access):
    """Render the production page using projection."""
    date_param = (request.GET.get("date") or "").strip()
    try:
        selected_date = date.fromisoformat(date_param) if date_param else date.today()
    except ValueError:
        selected_date = date.today()
    position_ref = (request.GET.get("position_ref") or "").strip()
    operator_ref = (request.GET.get("operator_ref") or "").strip()
    base_recipe = (request.GET.get("base_recipe") or "").strip()

    board = build_production_board(
        selected_date=selected_date,
        position_ref=position_ref,
        operator_ref=operator_ref,
        base_recipe=base_recipe,
        access=access,
    )

    context = {
        **admin_site.each_context(request),
        "title": "Registro de Produção",
        "board": board,
        "recipes": board.recipes,
        "base_recipes": board.base_recipes,
        "positions": board.positions,
        "default_position_id": board.default_position_pk,
        "production_access": board.access,
        "today_wos": board.work_orders,
        "craft_summary": board.counts,
        "planned_queue": board.planned_queue,
        "started_queue": board.started_queue,
        "finished_queue": board.finished_queue,
        "suggestions": board.suggestions,
        "matrix_rows": board.matrix_rows,
        "matrix_groups": board.matrix_groups,
        "selected_position_ref": board.selected_position_ref,
        "selected_operator_ref": board.selected_operator_ref,
        "selected_base_recipe": board.selected_base_recipe,
        "selected_date": selected_date,
    }
    return TemplateResponse(request, TEMPLATE, context)


def _production_redirect(request) -> str:
    params = {}
    date_value = (request.POST.get("target_date") or request.POST.get("date") or "").strip()
    if date_value:
        params["date"] = date_value
    position_ref = (request.POST.get("position_ref") or "").strip()
    operator_ref = (request.POST.get("operator_ref_filter") or "").strip()
    base_recipe = (request.POST.get("base_recipe") or "").strip()
    if position_ref:
        params["position_ref"] = position_ref
    if operator_ref:
        params["operator_ref"] = operator_ref
    if base_recipe:
        params["base_recipe"] = base_recipe
    base = reverse("admin:shop_production")
    return f"{base}?{urlencode(params)}" if params else base


# ── Bulk Create (from dashboard suggestions) ────────────────────────


def bulk_create_work_orders(request: HttpRequest) -> HttpResponse:
    """POST /gestor/producao/criar/ — bulk create WorkOrders from suggestions.

    Expects JSON body: {"date": "YYYY-MM-DD", "orders": [{"recipe_ref": "...", "quantity": N}, ...]}
    Returns HTMX partial with result summary.
    """
    access = resolve_production_access(request.user)
    if not (access.can_manage_all or access.can_edit_planned):
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
