"""Quick production registration + bulk create — admin custom views.

GET views consume projections from ``shopman.shop.projections.production``.
POST actions mutate state, then redirect (PRG pattern).
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from shopman.craftsman.models import Recipe
from shopman.craftsman.services.execution import CraftExecution
from shopman.craftsman.services.scheduling import CraftPlanning
from shopman.stockman import Position

from shopman.backstage.projections.production import build_production_board

logger = logging.getLogger(__name__)

TEMPLATE = "gestao/producao/index.html"
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
        from shopman.craftsman.models import WorkOrder
        wo = WorkOrder.objects.get(pk=wo_id)
        CraftExecution.void(
            order=wo,
            reason="Estornado via produção rápida",
            actor=f"admin:{request.user}",
        )
        messages.success(request, f"Ordem {wo.ref} estornada.")
    except Exception as exc:
        logger.warning("production_void_failed wo_id=%s: %s", wo_id, exc, exc_info=True)
        messages.error(request, f"Erro ao estornar: {exc}")

    return HttpResponseRedirect(reverse("admin:shop_production"))


def _handle_post(request, admin_site):
    """Create WorkOrder + finish immediately."""
    recipe_id = request.POST.get("recipe")
    quantity_raw = request.POST.get("quantity", "").strip()
    position_id = request.POST.get("position", "").strip()

    try:
        recipe = Recipe.objects.get(pk=recipe_id, is_active=True)
    except (Recipe.DoesNotExist, ValueError, TypeError):
        messages.error(request, "Receita inválida.")
        return _render(request, admin_site)

    try:
        quantity = Decimal(quantity_raw)
        if quantity <= 0:
            raise ValueError
    except (InvalidOperation, ValueError, TypeError):
        messages.error(request, "Quantidade inválida.")
        return _render(request, admin_site)

    position_ref = ""
    if position_id:
        try:
            pos = Position.objects.get(pk=position_id)
            position_ref = pos.ref
        except Position.DoesNotExist:
            pass

    if not position_ref:
        default_pos = Position.objects.filter(is_default=True).first()
        if default_pos:
            position_ref = default_pos.ref

    actor = f"admin:{request.user}"

    try:
        wo = CraftPlanning.plan(
            recipe,
            quantity,
            date=date.today(),
            position_ref=position_ref,
            source_ref="quick_production",
        )

        CraftExecution.finish(
            order=wo,
            finished=quantity,
            actor=actor,
        )

        messages.success(
            request,
            f"Produção registrada: {recipe.output_sku} × {quantity} ({wo.ref})",
        )
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
    """POST /gestao/producao/criar/ — bulk create WorkOrders from suggestions.

    Expects JSON body: {"date": "YYYY-MM-DD", "orders": [{"recipe_ref": "...", "quantity": N}, ...]}
    Returns HTMX partial with result summary.
    """
    if not request.user.has_perm(PERMISSION):
        return HttpResponse("Você não tem permissão para esta ação.", status=403)

    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(
            '<div class="text-red-600">Dados inválidos</div>',
            status=400,
        )

    target_date_str = body.get("date")
    orders_data = body.get("orders", [])

    if not orders_data:
        return HttpResponse(
            '<div class="text-red-600">Nenhuma ordem informada</div>',
            status=422,
        )

    try:
        target_date = date.fromisoformat(target_date_str) if target_date_str else date.today() + timedelta(days=1)
    except (ValueError, TypeError):
        target_date = date.today() + timedelta(days=1)

    default_pos = Position.objects.filter(is_default=True).first()
    position_ref = default_pos.ref if default_pos else ""

    created = []
    errors = []

    for entry in orders_data:
        recipe_ref = entry.get("recipe_ref", "")
        try:
            quantity = Decimal(str(entry.get("quantity", 0)))
            if quantity <= 0:
                continue
        except (InvalidOperation, TypeError):
            errors.append(f"{recipe_ref}: quantidade inválida")
            continue

        try:
            recipe = Recipe.objects.get(ref=recipe_ref, is_active=True)
        except Recipe.DoesNotExist:
            errors.append(f"{recipe_ref}: receita não encontrada")
            continue

        try:
            wo = CraftPlanning.plan(
                recipe,
                quantity,
                date=target_date,
                position_ref=position_ref,
                source_ref="dashboard_suggestion",
            )
            created.append(f"{recipe.output_sku} × {quantity} ({wo.ref})")
        except Exception as exc:
            errors.append(f"{recipe_ref}: {exc}")
            logger.exception("bulk_create_work_orders failed for %s", recipe_ref)

    parts = []
    if created:
        items_html = "".join(f"<li>{c}</li>" for c in created)
        parts.append(
            f'<div class="text-green-700 mb-2">'
            f'{len(created)} ordem(ns) criada(s) para {target_date}:'
            f'<ul class="list-disc ml-4 mt-1">{items_html}</ul></div>'
        )
    if errors:
        items_html = "".join(f"<li>{e}</li>" for e in errors)
        parts.append(
            f'<div class="text-red-600">'
            f'Erros:<ul class="list-disc ml-4 mt-1">{items_html}</ul></div>'
        )

    return HttpResponse("".join(parts))
