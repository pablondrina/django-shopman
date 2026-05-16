"""KDS station runtime for kitchen and expedition operators."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from shopman.backstage.models import KDSInstance
from shopman.backstage.projections.kds import build_kds_board
from shopman.backstage.services import kds as kds_service
from shopman.backstage.services.exceptions import KDSError

INDEX_TEMPLATE = "runtime/kds_station/index.html"
CARDS_TEMPLATE = "runtime/kds_station/partials/cards.html"
PERM = "backstage.operate_kds"


@require_GET
def kds_station_runtime_view(request: HttpRequest, ref: str) -> HttpResponse:
    """Render the touch-first KDS runtime station."""
    denied = _operator_required(request)
    if denied:
        return denied
    return render(request, INDEX_TEMPLATE, _station_context(ref))


@require_GET
def kds_station_runtime_cards_view(request: HttpRequest, ref: str) -> HttpResponse:
    """Render the cards partial used by SSE and polling refreshes."""
    denied = _operator_required(request)
    if denied:
        return denied
    return _render_cards(request, ref)


@require_POST
def kds_station_runtime_check_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Set one KDS item to the desired checked state."""
    denied = _operator_required(request)
    if denied:
        return denied

    try:
        ticket = kds_service.set_ticket_item_checked(
            ticket_pk=pk,
            index=int(request.POST.get("index", 0)),
            checked=_truthy(request.POST.get("checked")),
            actor=_actor(request.user),
        )
    except (KDSError, ValueError) as exc:
        return HttpResponse(str(exc), status=422)

    return _action_response(request, ticket.kds_instance.ref)


@require_POST
def kds_station_runtime_done_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark a ticket done from the runtime station."""
    denied = _operator_required(request)
    if denied:
        return denied

    try:
        ticket = kds_service.mark_ticket_done(ticket_pk=pk, actor=_actor(request.user))
    except KDSError as exc:
        return HttpResponse(str(exc), status=404)

    return _action_response(request, ticket.kds_instance.ref)


@require_POST
def kds_station_runtime_expedition_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Apply an expedition action from the runtime station."""
    denied = _operator_required(request)
    if denied:
        return denied

    action = (request.POST.get("action") or "").strip()
    station_ref = (request.POST.get("station_ref") or "").strip()
    try:
        kds_service.expedition_action_idempotent(order_id=pk, action=action, actor=_actor(request.user))
    except KDSError as exc:
        return HttpResponse(str(exc), status=422)

    return _action_response(request, station_ref or _default_expedition_ref())


def _station_context(ref: str) -> dict:
    station = get_object_or_404(KDSInstance, ref=ref, is_active=True)
    board = build_kds_board(station.ref)
    return {
        "kds_station": station,
        "kds_board": board,
        "kds_cards_url": reverse("backstage:kds_station_runtime_cards", args=[station.ref]),
        "kds_admin_url": reverse("admin_console_kds_display", args=[station.ref]),
        "kds_customer_board_url": reverse("backstage:kds_customer_board"),
    }


def _render_cards(request: HttpRequest, ref: str) -> HttpResponse:
    context = _station_context(ref)
    return render(request, CARDS_TEMPLATE, context)


def _operator_required(request: HttpRequest) -> HttpResponse | None:
    user = request.user
    if not user.is_authenticated or not user.is_staff:
        return redirect(f"/admin/login/?next={request.path}")
    if not _can_operate_kds(user):
        return HttpResponseForbidden("Voce nao tem permissao para operar o KDS.")
    return None


def _can_operate_kds(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or user.has_perm(PERM))


def _truthy(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "on", "yes"}


def _actor(user) -> str:
    username = getattr(user, "username", "") or "operator"
    return f"kds:{username}"


def _action_response(request: HttpRequest, ref: str) -> HttpResponse:
    if request.headers.get("HX-Request"):
        response = _render_cards(request, ref)
        response["HX-Trigger"] = "kdsStationChanged"
        return response
    return HttpResponseRedirect(reverse("backstage:kds_station_runtime", args=[ref]))


def _default_expedition_ref() -> str:
    station = KDSInstance.objects.filter(type="expedition", is_active=True).order_by("name").first()
    return station.ref if station else ""
