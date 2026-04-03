"""Quick production registration + bulk create — admin custom views."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse

from shopman.crafting.models import Recipe, WorkOrder
from shopman.crafting.services.execution import CraftExecution
from shopman.crafting.services.scheduling import CraftPlanning
from shopman.stocking.models.position import Position

logger = logging.getLogger(__name__)

TEMPLATE = "admin/shop/production.html"
PERMISSION = "crafting.add_workorder"


def production_view(request, admin_site):
    """GET: form + today's WOs. POST: create + close WO."""
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
        wo = WorkOrder.objects.get(pk=wo_id)
        CraftExecution.void(
            order=wo,
            reason="Estornado via produção rápida",
            actor=f"admin:{request.user}",
        )
        messages.success(request, f"Ordem {wo.code} estornada.")
    except WorkOrder.DoesNotExist:
        messages.error(request, "Ordem não encontrada.")
    except Exception as exc:
        messages.error(request, f"Erro ao estornar: {exc}")

    return HttpResponseRedirect(reverse("admin:shop_production"))


def _handle_post(request, admin_site):
    """Create WorkOrder + close immediately."""
    recipe_id = request.POST.get("recipe")
    quantity_raw = request.POST.get("quantity", "").strip()
    position_id = request.POST.get("position", "").strip()

    # Validate recipe
    try:
        recipe = Recipe.objects.get(pk=recipe_id, is_active=True)
    except (Recipe.DoesNotExist, ValueError, TypeError):
        messages.error(request, "Receita inválida.")
        return _render(request, admin_site)

    # Validate quantity
    try:
        quantity = Decimal(quantity_raw)
        if quantity <= 0:
            raise ValueError
    except (InvalidOperation, ValueError, TypeError):
        messages.error(request, "Quantidade inválida.")
        return _render(request, admin_site)

    # Resolve position
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
        # Plan (creates WO with status=open)
        wo = CraftPlanning.plan(
            recipe,
            quantity,
            date=date.today(),
            position_ref=position_ref,
            source_ref="quick_production",
        )

        # Close immediately (produced = quantity)
        CraftExecution.close(
            order=wo,
            produced=quantity,
            actor=actor,
        )

        messages.success(
            request,
            f"Produção registrada: {recipe.output_ref} × {quantity} ({wo.code})",
        )
    except Exception as exc:
        logger.exception("Quick production failed")
        messages.error(request, f"Erro ao registrar produção: {exc}")

    return HttpResponseRedirect(reverse("admin:shop_production"))


def _render(request, admin_site):
    """Render the production page with form + today's list."""
    today = date.today()

    recipes = Recipe.objects.filter(is_active=True).order_by("code")
    positions = Position.objects.all().order_by("name")
    default_position = Position.objects.filter(is_default=True).first()

    today_wos = (
        WorkOrder.objects
        .filter(scheduled_date=today)
        .select_related("recipe")
        .order_by("-created_at")
    )

    context = {
        **admin_site.each_context(request),
        "title": "Registro de Produção",
        "recipes": recipes,
        "positions": positions,
        "default_position_id": default_position.pk if default_position else None,
        "today_wos": today_wos,
        "today": today,
    }
    return TemplateResponse(request, TEMPLATE, context)


# ── Bulk Create (from dashboard suggestions) ────────────────────────


def bulk_create_work_orders(request: HttpRequest) -> HttpResponse:
    """POST /gestao/producao/criar/ — bulk create WorkOrders from suggestions.

    Expects JSON body: {"date": "YYYY-MM-DD", "orders": [{"recipe_code": "...", "quantity": N}, ...]}
    Returns HTMX partial with result summary.
    """
    if not request.user.is_staff:
        return HttpResponse("Unauthorized", status=403)

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

    # Parse target date (default: tomorrow)
    try:
        target_date = date.fromisoformat(target_date_str) if target_date_str else date.today() + timedelta(days=1)
    except (ValueError, TypeError):
        target_date = date.today() + timedelta(days=1)

    # Resolve default position
    default_pos = Position.objects.filter(is_default=True).first()
    position_ref = default_pos.ref if default_pos else ""

    created = []
    errors = []

    for entry in orders_data:
        recipe_code = entry.get("recipe_code", "")
        try:
            quantity = Decimal(str(entry.get("quantity", 0)))
            if quantity <= 0:
                continue
        except (InvalidOperation, TypeError):
            errors.append(f"{recipe_code}: quantidade inválida")
            continue

        try:
            recipe = Recipe.objects.get(code=recipe_code, is_active=True)
        except Recipe.DoesNotExist:
            errors.append(f"{recipe_code}: receita não encontrada")
            continue

        try:
            wo = CraftPlanning.plan(
                recipe,
                quantity,
                date=target_date,
                position_ref=position_ref,
                source_ref="dashboard_suggestion",
            )
            created.append(f"{recipe.output_ref} × {quantity} ({wo.code})")
        except Exception as exc:
            errors.append(f"{recipe_code}: {exc}")
            logger.exception("bulk_create_work_orders failed for %s", recipe_code)

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
