"""Quick production registration — admin custom view."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import HttpResponseRedirect
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
