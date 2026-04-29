"""Quick production registration + bulk create — operator backstage views.

GET views consume projections from ``shopman.shop.projections.production``.
POST actions mutate state, then redirect (PRG pattern).
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect, StreamingHttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import reverse

from shopman.backstage.projections.production import (
    build_production_dashboard,
    build_production_board,
    build_production_kds,
    build_production_reports,
    resolve_production_access,
)
from shopman.backstage.services import production as production_service
from shopman.backstage.services.production import ProductionOrderShortError, ProductionStockShortError

logger = logging.getLogger(__name__)

TEMPLATE = "gestor/producao/index.html"
DASHBOARD_TEMPLATE = "gestor/producao/dashboard.html"
KDS_TEMPLATE = "gestor/producao/kds.html"
KDS_PARTIAL_TEMPLATE = "gestor/producao/partials/kds_cards.html"
REPORTS_TEMPLATE = "gestor/producao/relatorios/index.html"
SHORTAGE_PARTIAL_TEMPLATE = "gestor/producao/partials/material_shortage.html"
ORDER_SHORT_PARTIAL_TEMPLATE = "gestor/producao/partials/order_shortage.html"
WO_COMMITMENTS_TEMPLATE = "gestor/producao/wo_commitments.html"


def production_view(request):
    """GET: form + today's WOs. POST: create + finish WO."""
    denied = _staff_required(request)
    if denied:
        return denied

    access = resolve_production_access(request.user)
    if not access.can_access_board:
        messages.error(request, "Sem permissão para acessar produção.")
        return HttpResponseRedirect(reverse("admin:index"))

    if request.method == "POST":
        return handle_production_post(request, access)

    return render_production_surface(request, access)


def production_dashboard_view(request):
    """GET: production dashboard for the selected day."""
    denied = _staff_required(request)
    if denied:
        return denied

    access = resolve_production_access(request.user)
    if not access.can_access_board:
        messages.error(request, "Sem permissão para acessar produção.")
        return HttpResponseRedirect(reverse("admin:index"))

    selected_date = _selected_date(request)
    position_ref = (request.GET.get("position_ref") or "").strip()
    dashboard = build_production_dashboard(
        selected_date=selected_date,
        position_ref=position_ref,
    )
    return TemplateResponse(request, DASHBOARD_TEMPLATE, {
        "title": "Dashboard de Produção",
        "dashboard": dashboard,
        "selected_date": selected_date,
        "selected_position_ref": position_ref,
    })


def production_kds_view(request):
    """GET: production KDS for started work orders."""
    denied = _staff_required(request)
    if denied:
        return denied

    access = resolve_production_access(request.user)
    if not (access.can_view_started or access.can_edit_started or access.can_edit_finished):
        messages.error(request, "Sem permissão para acessar produção em andamento.")
        return HttpResponseRedirect(reverse("admin:index"))

    selected_date = _selected_date(request)
    position_ref = (request.GET.get("position_ref") or "").strip()
    _check_late_started_orders(selected_date=selected_date)
    kds = build_production_kds(
        selected_date=selected_date,
        position_ref=position_ref,
        access=access,
    )
    return TemplateResponse(request, KDS_TEMPLATE, {
        "title": "KDS de Produção",
        "kds": kds,
        "selected_date": selected_date,
        "selected_position_ref": position_ref,
    })


def production_kds_cards_view(request):
    """HTMX partial: production KDS cards for polling updates."""
    denied = _staff_required(request)
    if denied:
        return denied

    access = resolve_production_access(request.user)
    if not (access.can_view_started or access.can_edit_started or access.can_edit_finished):
        return HttpResponse("", status=403)

    selected_date = _selected_date(request)
    position_ref = (request.GET.get("position_ref") or "").strip()
    _check_late_started_orders(selected_date=selected_date)
    kds = build_production_kds(
        selected_date=selected_date,
        position_ref=position_ref,
        access=access,
    )
    return TemplateResponse(request, KDS_PARTIAL_TEMPLATE, {
        "kds": kds,
        "selected_date": selected_date,
        "selected_position_ref": position_ref,
    })


def production_reports_view(request):
    """GET: production reports surface and CSV export."""
    denied = _staff_required(request)
    if denied:
        return denied
    if not _can_view_reports(request.user):
        return HttpResponseForbidden("Sem permissão para acessar relatórios de produção.")

    filters = _report_filters(request)
    report_kind = filters.get("report_kind", "history")
    if request.GET.get("format") == "csv":
        csv_bytes = production_service.export_reports_csv(report_kind, filters)
        response = StreamingHttpResponse(
            [csv_bytes],
            content_type="text/csv; charset=utf-8",
        )
        filename = f"producao_{report_kind}_{filters['date_from']}_{filters['date_to']}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    reports = build_production_reports(filters)
    return TemplateResponse(request, REPORTS_TEMPLATE, {
        "title": "Relatórios de Produção",
        "reports": reports,
        "filters": reports.filters,
        "report_kind": reports.filters.report_kind,
    })


def production_work_order_commitments_view(request, wo_ref: str):
    """GET: item quantities committed by linked orders for a work order."""
    denied = _staff_required(request)
    if denied:
        return denied

    access = resolve_production_access(request.user)
    if not access.can_access_board:
        return HttpResponseForbidden("Sem permissão para acessar produção.")

    try:
        work_order, refs, commitments, committed_qty = production_service.order_commitments_for_work_order(wo_ref)
    except ObjectDoesNotExist as exc:
        raise Http404("Ordem de produção não encontrada.") from exc
    return TemplateResponse(request, WO_COMMITMENTS_TEMPLATE, {
        "title": f"Compromissos de {wo_ref}",
        "work_order": work_order,
        "commitments": commitments,
        "order_refs": refs,
        "committed_qty": committed_qty,
    })


def production_advance_step_view(request, wo_id):
    """POST: advance the KDS step pointer of a STARTED work order by one."""
    denied = _staff_required(request)
    if denied:
        return denied
    if request.method != "POST":
        return HttpResponseRedirect(reverse("backstage:production_kds"))

    access = resolve_production_access(request.user)
    if not (access.can_manage_all or access.can_edit_started):
        return HttpResponseForbidden("Sem permissão para avançar passo.")

    try:
        production_service.apply_advance_step(
            work_order_id=wo_id,
            actor=f"production:{request.user.username}",
        )
    except production_service.ProductionError as exc:
        return HttpResponse(str(exc), status=422)
    except ObjectDoesNotExist:
        raise Http404("Ordem de produção não encontrada.")

    if request.headers.get("HX-Request"):
        return production_kds_cards_view(request)
    return HttpResponseRedirect(reverse("backstage:production_kds"))


def production_void_view(request):
    """POST: void a WorkOrder."""
    denied = _staff_required(request)
    if denied:
        return denied

    access = resolve_production_access(request.user)
    if not (access.can_manage_all or access.can_edit_planned or access.can_edit_started):
        messages.error(request, "Sem permissão.")
        return HttpResponseRedirect(reverse("admin:index"))

    if request.method != "POST":
        return HttpResponseRedirect(reverse("backstage:production"))

    wo_id = request.POST.get("wo_id")
    if not wo_id:
        messages.error(request, "Ordem não informada.")
        return HttpResponseRedirect(reverse("backstage:production"))

    try:
        wo_ref = production_service.apply_void(
            wo_id,
            actor=f"production:{request.user.username}",
        )
        messages.success(request, f"Ordem {wo_ref} estornada.")
    except Exception as exc:
        logger.warning("production_void_failed wo_id=%s: %s", wo_id, exc, exc_info=True)
        messages.error(request, f"Erro ao estornar: {exc}")

    return HttpResponseRedirect(reverse("backstage:production"))


def _staff_required(request):
    """Redirect to login if not authenticated+staff."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect(f"/admin/login/?next={request.path}")
    return None


def _selected_date(request) -> date:
    date_param = (request.GET.get("date") or "").strip()
    try:
        return date.fromisoformat(date_param) if date_param else date.today()
    except ValueError:
        return date.today()


VALID_REPORT_KINDS = ("history", "operator_productivity", "recipe_waste")


def _report_filters(request) -> dict:
    today = date.today()
    raw_from = (request.GET.get("date_from") or (today - timedelta(days=6)).isoformat()).strip()
    raw_to = (request.GET.get("date_to") or today.isoformat()).strip()
    raw_kind = (request.GET.get("report_kind") or request.GET.get("kind") or "history").strip()

    date_from = _coerce_iso_date(raw_from, fallback=today - timedelta(days=6))
    date_to = _coerce_iso_date(raw_to, fallback=today)
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "recipe_ref": (request.GET.get("recipe_ref") or "").strip(),
        "position_ref": (request.GET.get("position_ref") or "").strip(),
        "operator_ref": (request.GET.get("operator_ref") or "").strip(),
        "status": (request.GET.get("status") or "").strip(),
        "report_kind": raw_kind if raw_kind in VALID_REPORT_KINDS else "history",
    }


def _coerce_iso_date(raw: str, *, fallback: date) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return fallback


def _can_view_reports(user) -> bool:
    return (
        getattr(user, "is_superuser", False)
        or user.has_perm("backstage.view_production_reports")
        or user.has_perm("shop.manage_production")
    )


def _check_late_started_orders(*, selected_date: date) -> None:
    try:
        from shopman.shop.handlers.production_alerts import check_late_started_orders

        check_late_started_orders(selected_date=selected_date)
    except Exception:
        logger.exception("production_late_check_failed date=%s", selected_date)


def handle_production_post(request, access, *, redirect_url_name: str = "backstage:production"):
    """Mutate production through the canonical Craftsman lifecycle."""
    action = (request.POST.get("action") or "quick_finish").strip()
    actor = f"production:{request.user.username}"

    try:
        if action == "set_planned":
            is_suggestion = request.POST.get("source") == "suggested"
            can_set_planned = access.can_edit_planned or (is_suggestion and access.can_edit_suggested)
            if not can_set_planned:
                messages.error(request, "Sem permissão para planejar produção.")
            else:
                output_sku, wo_ref, quantity, result = production_service.apply_planned(
                    recipe_id=request.POST.get("recipe"),
                    quantity=request.POST.get("quantity", "").strip(),
                    target_date_value=request.POST.get("target_date", "").strip(),
                    position_ref=request.POST.get("position_ref", "").strip(),
                    operator_ref=request.POST.get("operator_ref", "").strip(),
                    actor=actor,
                    force=request.POST.get("force") == "1",
                )
                if result == "cleared":
                    messages.success(request, f"Planejamento zerado: {output_sku}")
                elif result == "unchanged":
                    messages.info(request, f"Planejamento mantido: {output_sku} × {quantity}")
                else:
                    messages.success(request, f"Planejado: {output_sku} × {quantity} ({wo_ref})")
        elif action == "start":
            if not access.can_edit_started:
                messages.error(request, "Sem permissão para iniciar produção.")
            else:
                wo_ref, quantity = production_service.apply_start(
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
                wo_ref, quantity = production_service.apply_finish(
                    work_order_id=request.POST.get("wo_id"),
                    quantity=request.POST.get("quantity", "").strip(),
                    actor=actor,
                    force=request.POST.get("force") == "1",
                )
                if request.POST.get("force") == "1":
                    messages.warning(request, f"Produção concluída com alerta de insumos: {wo_ref} × {quantity}")
                else:
                    messages.success(request, f"Produção concluída: {wo_ref} × {quantity}")
        elif action == "quick_finish":
            if not access.can_edit_finished:
                messages.error(request, "Sem permissão para informar produção concluída.")
            else:
                output_sku, wo_ref, quantity = production_service.apply_quick_finish(
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
    except ProductionStockShortError as exc:
        if request.headers.get("HX-Request"):
            return HttpResponse(
                render_to_string(
                    SHORTAGE_PARTIAL_TEMPLATE,
                    {
                        "missing": exc.missing,
                        "post": request.POST,
                    },
                    request=request,
                ),
            )
        messages.error(request, str(exc))
    except ProductionOrderShortError as exc:
        if request.headers.get("HX-Request"):
            return HttpResponse(
                render_to_string(
                    ORDER_SHORT_PARTIAL_TEMPLATE,
                    {
                        "error": exc,
                        "post": request.POST,
                    },
                    request=request,
                ),
            )
        messages.error(request, str(exc))
    except ValueError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        logger.exception("Production action failed action=%s", action)
        messages.error(request, f"Erro ao registrar produção: {exc}")

    return HttpResponseRedirect(production_redirect(request, redirect_url_name=redirect_url_name))


def render_production_surface(request, access, *, template_name: str = TEMPLATE, extra_context: dict | None = None):
    """Render the production page using projection."""
    selected_date = _selected_date(request)
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
    if extra_context:
        context.update(extra_context)
    return TemplateResponse(request, template_name, context)


def production_redirect(request, *, redirect_url_name: str = "backstage:production") -> str:
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
    base = reverse(redirect_url_name)
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

    if request.content_type == "application/json":
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return HttpResponse(
                render_to_string(_PARTIAL, {"error": "Dados inválidos"}, request=request),
                status=400,
            )
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
        return HttpResponse(
            render_to_string(_PARTIAL, {"error": "Nenhuma ordem informada"}, request=request),
            status=422,
        )

    result = production_service.apply_suggestions(
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
