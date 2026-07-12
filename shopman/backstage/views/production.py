"""Read-only helpers for the Admin/Unfold production console.

The live production floor migrated to the dedicated Nuxt app
(``surfaces/production-nuxt`` / ``fournil.``) over the headless API at
``api/v1/backstage/production/*`` (OPERATOR-APPS-PLAN Fase 4), and EXECUTION
(planejar, iniciar, concluir, entrada direta) is exclusive to it — split
canônico WP-PE4: Admin/Unfold = gestão (leitura, relatórios, pesagem,
compromissos, auditoria). What remains here are the SHARED read helpers
consumed by the Admin/Unfold production console
(``admin_console/production.py``): ``render_production_surface`` and its
filter parsing support. GET views consume projections from
``shopman.backstage.projections.production``.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.template.response import TemplateResponse
from django.utils import timezone

from shopman.backstage.projections.production import (
    build_production_board,
)


def _selected_date(request) -> date:
    date_param = (request.GET.get("date") or "").strip()
    try:
        return date.fromisoformat(date_param) if date_param else timezone.localdate()
    except ValueError:
        return timezone.localdate()


VALID_REPORT_KINDS = ("history", "operator_productivity", "recipe_waste")


def _report_filters(request) -> dict:
    today = timezone.localdate()
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


def render_production_surface(
    request,
    access,
    *,
    template_name: str,
    extra_context: dict | None = None,
    context_callback=None,
):
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
        "title": "Produção do dia",
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
    if context_callback:
        context.update(context_callback(request, board, context))
    return TemplateResponse(request, template_name, context)
