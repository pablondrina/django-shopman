"""Backstage API — POS, Production, Day Closing, Orders Queue.

GET endpoints (read views):
  GET  /api/v1/backstage/pos/                 → POS terminal projection
  GET  /api/v1/backstage/production/          → Production board for today
  GET  /api/v1/backstage/production/kds/      → Production KDS (started WOs)
  GET  /api/v1/backstage/closing/             → Day closing snapshot
  GET  /api/v1/backstage/orders/              → Operator order queue

POST endpoints (operator actions):
  POST /api/v1/backstage/orders/<ref>/advance/  → next status
  POST /api/v1/backstage/orders/<ref>/confirm/  → confirm pending order
  POST /api/v1/backstage/orders/<ref>/reject/   → reject pending order
  POST /api/v1/backstage/orders/<ref>/cancel/   → cancel order
  POST /api/v1/backstage/production/<wo_id>/advance-step/ → next step
  POST /api/v1/backstage/production/<wo_id>/finish/  → quick finish step (for KDS)
  POST /api/v1/backstage/production/<wo_id>/void/    → void work order
  POST /api/v1/backstage/closing/                    → finalize day closing
  POST /api/v1/backstage/pos/cash/open/              -> open cash shift
  POST /api/v1/backstage/pos/cash/close/             -> close cash shift
  POST /api/v1/backstage/pos/cash/movement/          → register cash movement
  POST /api/v1/backstage/pos/sale/review/            → validate POS checkout without commit
  POST /api/v1/backstage/pos/sale/recent/cancel/     → cancel recent POS sale
"""

from __future__ import annotations

import logging
from datetime import date

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView
from shopman.utils.monetary import format_money

from shopman.backstage.constants import POS_CHANNEL_REF
from shopman.backstage.projections.closing import build_day_closing
from shopman.backstage.projections.order_queue import build_operator_order, build_two_zone_queue
from shopman.backstage.projections.pos import (
    build_open_tab,
    build_pos,
    build_pos_customer_lookup,
    build_pos_shift_summary,
    build_pos_tabs,
)
from shopman.backstage.projections.production import (
    build_production_board,
    build_production_kds,
)
from shopman.backstage.services import (
    closing as closing_service,
)
from shopman.backstage.services import (
    orders as orders_service,
)
from shopman.backstage.services import (
    pos as pos_service,
)
from shopman.backstage.services import (
    production as production_service,
)
from shopman.backstage.services.exceptions import OrderError, POSError, ProductionError
from shopman.shop.services import pos as pos_tabs_service
from shopman.shop.services.pos_intent import PosIntentError

from .permissions import HasBackstagePermission
from .projections import projection_data

logger = logging.getLogger(__name__)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _actor(request) -> str:
    user = getattr(request, "user", None)
    return getattr(user, "username", None) or "operator"


def _cash_shift_result(shift) -> dict:
    # Blind close: the operator sees only what they counted, never the expected
    # amount or variance. ``expected_amount_q``/``difference_q`` are still
    # computed and stored on the shift; managers review them via Admin and the
    # day-closing reconciliation, never at the cashier terminal.
    return {
        "id": shift.pk,
        "terminal_ref": shift.terminal.ref,
        "operator": shift.operator.get_username(),
        "status": shift.status,
        "opened_at": shift.opened_at.isoformat() if shift.opened_at else "",
        "closed_at": shift.closed_at.isoformat() if shift.closed_at else "",
        "opening_amount_q": shift.opening_amount_q,
        "blind_closing_amount_q": shift.blind_closing_amount_q,
    }


def _pos_payload_with_runtime(request, body: dict) -> dict:
    """Attach the active POS runtime context that browser surfaces should not invent."""
    payload = dict(body or {})
    cash_shift = _open_cash_shift_for_request(request)
    if cash_shift:
        payload.setdefault("cash_shift_id", cash_shift.pk)
        payload.setdefault("pos_terminal_ref", cash_shift.terminal.ref)
    return payload


def _open_cash_shift_for_request(request):
    try:
        from shopman.backstage.models import CashShift

        return CashShift.get_open_for_operator(request.user)
    except Exception:
        logger.debug("pos_runtime_payload_enrichment_failed user=%s", _actor(request), exc_info=True)
        return None


def _cash_shift_required_response() -> Response:
    return Response(
        {
            "detail": "Abra o caixa antes de revisar ou finalizar uma venda.",
            "error": {
                "code": "cash_shift_required",
                "message": "Abra o caixa antes de revisar ou finalizar uma venda.",
                "field": "cash_shift_id",
                "focus": "cash",
                "recovery": "Abra um turno de caixa neste terminal e tente novamente.",
            },
        },
        status=409,
    )


def _pos_sale_review_payload(review) -> dict:
    return {
        "intent_version": review.intent_version,
        "tab_ref": review.tab_ref,
        "subtotal_q": review.subtotal_q,
        "subtotal_display": f"R$ {format_money(review.subtotal_q)}",
        "discount_q": review.discount_q,
        "discount_display": f"R$ {format_money(review.discount_q)}",
        "delivery_fee_q": review.delivery_fee_q,
        "delivery_fee_display": f"R$ {format_money(review.delivery_fee_q)}",
        "total_q": review.total_q,
        "total_display": f"R$ {format_money(review.total_q)}",
        "payment_method": review.payment_method,
        "payment_collection": review.payment_collection,
        "tender_total_q": review.tender_total_q,
        "tender_total_display": f"R$ {format_money(review.tender_total_q)}",
        "tender_count": review.tender_count,
        "tendered_amount_q": review.tendered_amount_q,
        "tendered_amount_display": f"R$ {format_money(review.tendered_amount_q)}",
        "change_q": review.change_q,
        "change_display": f"R$ {format_money(review.change_q)}",
        "requires_manager_approval": review.requires_manager_approval,
        "manager_approval_threshold_q": review.manager_approval_threshold_q,
        "receipt_mode": review.receipt_mode,
        "issue_fiscal_document": review.issue_fiscal_document,
        "warnings": list(review.warnings),
    }


# ── Read endpoints ────────────────────────────────────────────────────


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="POS terminal projection",
        responses={200: OpenApiResponse(description="Products, tabs, payment methods, shift summary.")},
    ),
)
class POSView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def get(self, request):
        from shopman.backstage.services.operator import active_operator

        pos = build_pos(operator=request.user)
        shift = build_pos_shift_summary()
        query = request.query_params.get("q", "")
        tabs = build_pos_tabs(query=query)
        return Response({
            "pos": projection_data(pos),
            "shift": projection_data(shift),
            "tabs": projection_data(tabs),
            "operator": active_operator(request),
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="POS operator unlock (PIN)",
        responses={200: OpenApiResponse(description="Active operator bound to the terminal session.")},
    ),
)
class POSOperatorUnlockView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        from django.contrib.auth import get_user_model

        from shopman.backstage.services import operator as operator_service

        operator_id = str(request.data.get("operator_id", "")).strip()
        pin = str(request.data.get("pin", ""))
        operator = (
            get_user_model().objects.filter(pk=operator_id, is_active=True).first()
            if operator_id else None
        )
        if operator is None or not operator_service.verify_operator_pin(operator, pin):
            return Response(
                {"ok": False, "error": {"code": "operator_pin_invalid", "message": "PIN inválido."}},
                status=403,
            )
        card = operator_service.set_active_operator(request, operator)
        return Response({"ok": True, "operator": card})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="POS operator lock",
        responses={200: OpenApiResponse(description="Terminal locked (active operator cleared).")},
    ),
)
class POSOperatorLockView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        from shopman.backstage.services import operator as operator_service

        operator_service.clear_active_operator(request)
        return Response({"ok": True})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Production board",
        responses={200: OpenApiResponse(description="Work orders for the selected date.")},
    ),
)
class ProductionBoardView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "craftsman.view_workorder"

    def get(self, request):
        selected = _parse_date(request.query_params.get("date"))
        position_ref = request.query_params.get("position", "")
        board = build_production_board(
            selected_date=selected,
            position_ref=position_ref,
        )
        return Response({"board": projection_data(board)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Production KDS (started work orders)",
        responses={200: OpenApiResponse(description="Live KDS board for production.")},
    ),
)
class ProductionKDSView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "craftsman.view_workorder"

    def get(self, request):
        selected = _parse_date(request.query_params.get("date"))
        position_ref = request.query_params.get("position", "")
        kds = build_production_kds(
            selected_date=selected,
            position_ref=position_ref,
        )
        return Response({"kds": projection_data(kds)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Day closing snapshot",
        responses={200: OpenApiResponse(description="Items pending closing decision.")},
    ),
)
class DayClosingView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.perform_closing"

    def get(self, request):
        closing = build_day_closing()
        return Response({"closing": projection_data(closing)})

    def post(self, request):
        """Finalize the day closing.

        Body: { "quantities": { "<sku>": "<qty>", ... } }
        """
        quantities = request.data.get("quantities", {}) if hasattr(request, "data") else {}
        if not isinstance(quantities, dict):
            return Response({"detail": "quantities must be an object."}, status=400)

        closing = build_day_closing()
        if closing.already_closed:
            return Response({"detail": "Fechamento de hoje já foi realizado."}, status=409)

        try:
            closing_date = closing_service.perform_day_closing(
                user=request.user,
                items=list(closing.items),
                quantities_by_sku={str(k): str(v) for k, v in quantities.items()},
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("day_closing_perform_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha no fechamento."}, status=400)

        return Response({"ok": True, "closing_date": closing_date.isoformat()})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Operator order detail",
        responses={200: OpenApiResponse(description="Full operator order projection.")},
    ),
)
class OrderDetailView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_orders"

    def get(self, request, ref: str):
        order = orders_service.find_order(ref)
        if order is None:
            return Response({"detail": "Pedido não encontrado."}, status=404)
        proj = build_operator_order(order)
        return Response({"order": projection_data(proj)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Operator order queue (two-zone view)",
        responses={200: OpenApiResponse(description="Active and recent orders for operator.")},
    ),
)
class OrderQueueView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_orders"

    def get(self, request):
        queue = build_two_zone_queue()
        return Response({"queue": projection_data(queue)})


# ── Order action endpoints ────────────────────────────────────────────


class _OrderActionBase(APIView):
    """Shared base for order action endpoints (advance/confirm/reject/cancel)."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_orders"

    def _get_order(self, ref: str):
        order = orders_service.find_order(ref)
        if order is None:
            return None, Response({"detail": "Pedido não encontrado."}, status=404)
        return order, None


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Advance order to next status",
        responses={200: OpenApiResponse(description="Order advanced.")},
    ),
)
class OrderAdvanceView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        try:
            orders_service.advance_order(order, actor=_actor(request))
        except OrderError as exc:
            return Response({"detail": str(exc) or "Ação inválida."}, status=400)
        return Response({"ok": True, "ref": ref})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Confirm pending order",
        responses={200: OpenApiResponse(description="Order confirmed.")},
    ),
)
class OrderConfirmView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        try:
            orders_service.confirm_order(order, actor=_actor(request))
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao confirmar."}, status=400)
        return Response({"ok": True, "ref": ref})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Reject pending order",
        responses={200: OpenApiResponse(description="Order rejected.")},
    ),
)
class OrderRejectView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        reason = (request.data.get("reason") or "").strip() if hasattr(request, "data") else ""
        if not reason:
            return Response({"detail": "Motivo da recusa é obrigatório."}, status=400)
        try:
            orders_service.reject_order(
                order,
                reason=reason,
                actor=_actor(request),
                rejected_by="operator",
            )
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao recusar."}, status=400)
        return Response({"ok": True, "ref": ref})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Cancel order",
        responses={200: OpenApiResponse(description="Order cancelled.")},
    ),
)
class OrderCancelView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        reason = (request.data.get("reason") or "Cancelado pelo operador").strip()
        try:
            orders_service.cancel_order(order, reason=reason, actor=_actor(request))
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao cancelar."}, status=400)
        return Response({"ok": True, "ref": ref})


# ── Production action endpoints ───────────────────────────────────────


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Advance work order step",
        responses={200: OpenApiResponse(description="Step advanced.")},
    ),
)
class WorkOrderAdvanceStepView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "craftsman.change_workorder"

    def post(self, request, wo_id: int):
        try:
            new_index = production_service.apply_advance_step(
                work_order_id=wo_id,
                actor=_actor(request),
            )
        except ProductionError as exc:
            return Response({"detail": str(exc) or "Falha ao avançar passo."}, status=400)
        return Response({"ok": True, "wo_id": wo_id, "step_index": new_index})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Quick-finish a recipe (plan + finish in one step)",
        responses={200: OpenApiResponse(description="Work order finished.")},
    ),
)
class WorkOrderQuickFinishView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "craftsman.change_workorder"

    def post(self, request):
        recipe_id = request.data.get("recipe_id")
        quantity = request.data.get("quantity")
        position_id = request.data.get("position_id")
        if not (recipe_id and quantity and position_id):
            return Response(
                {"detail": "recipe_id, quantity e position_id são obrigatórios."},
                status=400,
            )
        try:
            wo = production_service.apply_quick_finish(
                recipe_id=recipe_id,
                quantity=quantity,
                position_id=position_id,
                actor=_actor(request),
            )
        except ProductionError as exc:
            return Response({"detail": str(exc) or "Falha ao finalizar."}, status=400)
        return Response({"ok": True, "wo_ref": getattr(wo, "ref", None)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Void (cancel) a work order",
        responses={200: OpenApiResponse(description="Work order voided.")},
    ),
)
class WorkOrderVoidView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "craftsman.change_workorder"

    def post(self, request, wo_id: int):
        reason = (request.data.get("reason") or "Estornado pelo operador").strip()
        try:
            ref = production_service.apply_void(
                wo_id, actor=_actor(request), reason=reason,
            )
        except ProductionError as exc:
            return Response({"detail": str(exc) or "Falha ao estornar."}, status=400)
        return Response({"ok": True, "wo_ref": ref})


# ── POS cash shift endpoints ──────────────────────────────────────────


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Open cash shift",
        responses={200: OpenApiResponse(description="Cash shift opened.")},
    ),
)
class POSCashOpenView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        amount = request.data.get("opening_amount", "0")
        try:
            session = pos_service.open_cash_shift(
                operator=request.user,
                opening_amount_raw=str(amount),
                terminal_ref=str(request.data.get("terminal_ref") or ""),
            )
        except POSError as exc:
            message = str(exc) or "Falha ao abrir caixa."
            terminal_occupied = "Terminal POS" in message and "turno aberto" in message
            return Response(
                {
                    "detail": message,
                    "error": {
                        "code": "cash_terminal_occupied" if terminal_occupied else "cash_shift_open_failed",
                        "message": message,
                        "field": "terminal_ref" if terminal_occupied else "opening_amount",
                        "focus": "cash",
                        "recovery": (
                            "Use o operador correto, feche o turno atual no gestor ou selecione outro terminal antes de vender."
                            if terminal_occupied
                            else "Corrija os dados de abertura do caixa e tente novamente."
                        ),
                    },
                },
                status=409 if terminal_occupied else 400,
            )
        except Exception as exc:
            logger.debug("pos_cash_shift_open_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao abrir caixa."}, status=400)
        return Response({"ok": True, "shift_id": session.pk, "terminal_ref": session.terminal.ref})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Close cash shift",
        responses={200: OpenApiResponse(description="Cash shift closed.")},
    ),
)
class POSCashCloseView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        amount = request.data.get("closing_amount", "0")
        notes = (request.data.get("notes") or "").strip()
        try:
            result = pos_service.close_cash_shift(
                operator=request.user,
                closing_amount_raw=str(amount),
                notes=notes,
            )
        except Exception as exc:
            logger.debug("pos_cash_shift_close_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao fechar caixa."}, status=400)
        return Response({"ok": True, "result": _cash_shift_result(result) if result else None})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Register cash movement (sangria/suprimento/ajuste)",
        responses={200: OpenApiResponse(description="Movement registered.")},
    ),
)
class POSCashMovementView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        kind = (request.data.get("kind") or "").strip()
        amount = request.data.get("amount", "0")
        reason = (request.data.get("reason") or "").strip()
        if kind not in {"sangria", "suprimento", "ajuste"}:
            return Response({"detail": "kind deve ser 'sangria', 'suprimento' ou 'ajuste'."}, status=400)
        try:
            mov = pos_service.register_cash_movement(
                operator=request.user,
                movement_type=kind,
                amount_raw=str(amount),
                reason=reason,
            )
        except Exception as exc:
            logger.debug("pos_cash_movement_failed user=%s kind=%s", _actor(request), kind, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao registrar movimento."}, status=400)
        return Response({"ok": True, "movement_id": getattr(mov, "pk", None)})


# ── POS tab (comanda) endpoints ───────────────────────────────────────


def _actor_pos(request) -> str:
    return f"pos:{getattr(request.user, 'username', None) or 'operator'}"


def _username (request) -> str:
    return getattr(request.user, "username", None) or "operator"


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Register a new POS tab (comanda)",
        responses={200: OpenApiResponse(description="Tab created.")},
    ),
)
class POSTabCreateView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        tab_ref = (request.data.get("tab_ref") or "").strip()
        label = (request.data.get("label") or "").strip()
        if not tab_ref:
            return Response({"detail": "Referência da comanda é obrigatória."}, status=400)
        try:
            tab = pos_tabs_service.register_pos_tab(tab_ref=tab_ref, label=label)
        except Exception as exc:
            logger.debug("pos_tab_create_failed tab_ref=%s", tab_ref, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao criar comanda."}, status=400)
        return Response({"ok": True, "tab": tab})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Open or load a POS tab",
        responses={200: OpenApiResponse(description="Tab payload (items + customer + tab_ref).")},
    ),
)
class POSTabOpenView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request, tab_ref: str):
        try:
            session = pos_tabs_service.open_pos_tab(
                channel_ref=POS_CHANNEL_REF,
                tab_ref=tab_ref,
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except Exception as exc:
            logger.debug("pos_tab_open_failed tab_ref=%s", tab_ref, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao abrir comanda."}, status=400)
        return Response(build_open_tab(session))


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Save the POS cart on its tab",
        responses={200: OpenApiResponse(description="Tab saved.")},
    ),
)
class POSTabSaveView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        body = request.data if hasattr(request, "data") else {}
        try:
            result = pos_tabs_service.save_pos_tab(
                channel_ref=POS_CHANNEL_REF,
                payload=body,
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except Exception as exc:
            logger.debug("pos_tab_save_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao salvar comanda."}, status=400)
        return Response({
            "ok": True,
            "tab_ref": result.tab_ref,
            "tab_display": result.tab_display,
            "session_key": result.session_key,
        })


@extend_schema_view(
    delete=extend_schema(
        tags=["backstage"],
        summary="Clear a POS tab (abandon session)",
        responses={200: OpenApiResponse(description="Tab cleared.")},
    ),
)
class POSTabClearView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def delete(self, request, session_key: str):
        try:
            cleared = pos_tabs_service.clear_pos_tab(
                channel_ref=POS_CHANNEL_REF,
                session_key=session_key,
                operator_username=_username(request),
            )
        except Exception as exc:
            logger.debug("pos_tab_clear_failed session_key=%s", session_key, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao liberar comanda."}, status=400)
        if not cleared:
            return Response({"detail": "Comanda não encontrada."}, status=404)
        return Response({"ok": True})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Move lines between POS tabs (transfer/split/merge)",
        responses={200: OpenApiResponse(description="Lines moved.")},
    ),
)
class POSTabMoveLinesView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        body = request.data if hasattr(request, "data") else {}
        try:
            result = pos_tabs_service.move_pos_tab_lines(
                channel_ref=POS_CHANNEL_REF,
                from_session_key=str(body.get("from_session_key") or "").strip(),
                to_session_key=str(body.get("to_session_key") or "").strip(),
                to_tab_ref=str(body.get("to_tab_ref") or "").strip(),
                line_ids=body.get("line_ids") or [],
                close_source_when_empty=bool(body.get("close_source_when_empty")),
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_tab_move_lines_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao mover itens entre comandas."}, status=400)
        return Response({
            "ok": True,
            "source_closed": result.source_closed,
            "source": None if result.source is None else build_open_tab(result.source),
            "target": build_open_tab(result.target),
        })


class POSTabRenameView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        body = request.data if hasattr(request, "data") else {}
        try:
            session = pos_tabs_service.rename_pos_tab(
                channel_ref=POS_CHANNEL_REF,
                session_key=str(body.get("session_key") or "").strip(),
                new_tab_ref=str(body.get("new_tab_ref") or "").strip(),
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_tab_rename_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao renomear comanda."}, status=400)
        return Response({"ok": True, "tab": build_open_tab(session)})


class POSTabFireView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        body = request.data if hasattr(request, "data") else {}
        try:
            result = pos_tabs_service.fire_pos_tab(
                channel_ref=POS_CHANNEL_REF,
                session_key=str(body.get("session_key") or "").strip(),
                line_ids=body.get("line_ids") or [],
                client_request_id=str(body.get("client_request_id") or "").strip(),
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_tab_fire_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao enviar à cozinha."}, status=400)
        return Response({
            "ok": True,
            "fired_count": result.fired_count,
            "fired_lines": list(result.fired_lines),
            "tab": build_open_tab(result.session),
        })


class POSTabUnfireView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        body = request.data if hasattr(request, "data") else {}
        try:
            result = pos_tabs_service.cancel_fired_pos_tab_lines(
                channel_ref=POS_CHANNEL_REF,
                session_key=str(body.get("session_key") or "").strip(),
                line_ids=body.get("line_ids") or [],
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_tab_unfire_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao cancelar envio à cozinha."}, status=400)
        return Response({
            "ok": True,
            "cancelled": result.cancelled,
            "trimmed": result.trimmed,
            "fired_lines": list(result.fired_lines),
            "tab": build_open_tab(result.session),
        })


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Look up customer by phone",
        responses={200: OpenApiResponse(description="Customer projection or null.")},
    ),
)
class POSCustomerLookupView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def get(self, request):
        phone = (request.query_params.get("phone") or "").strip()
        if not phone:
            return Response({"customer": None})
        customer = build_pos_customer_lookup(phone)
        if customer is None:
            return Response({"customer": None})
        return Response({"customer": projection_data(customer)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Review POS sale intent without committing",
        responses={200: OpenApiResponse(description="Checkout review and normalized totals.")},
    ),
)
class POSReviewSaleView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        body = request.data if hasattr(request, "data") else {}
        if _open_cash_shift_for_request(request) is None:
            return _cash_shift_required_response()
        try:
            review = pos_tabs_service.review_sale(
                channel_ref=POS_CHANNEL_REF,
                payload=_pos_payload_with_runtime(request, body),
                operator_username=_username(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=422)
        except Exception as exc:
            logger.debug("pos_review_sale_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao revisar checkout."}, status=400)
        return Response({"ok": True, "review": _pos_sale_review_payload(review)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Close POS sale (commit cart as order)",
        responses={200: OpenApiResponse(description="Order created.")},
    ),
)
class POSCloseSaleView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        body = request.data if hasattr(request, "data") else {}
        if _open_cash_shift_for_request(request) is None:
            return _cash_shift_required_response()
        try:
            result = pos_tabs_service.close_sale(
                channel_ref=POS_CHANNEL_REF,
                payload=_pos_payload_with_runtime(request, body),
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_close_sale_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao finalizar venda."}, status=400)
        return Response({
            "ok": True,
            "order_ref": getattr(result, "order_ref", None),
            "tab_ref": getattr(result, "tab_ref", None),
            "payment": getattr(result, "payment", None) or {},
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Cancel a recent POS sale",
        responses={200: OpenApiResponse(description="Recent POS sale cancelled.")},
    ),
)
class POSCancelRecentSaleView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        order_ref = (request.data.get("order_ref") or "").strip()
        reason = (request.data.get("reason") or "").strip()
        if not order_ref:
            return Response({"detail": "Referência do pedido não informada."}, status=422)
        try:
            if reason:
                pos_tabs_service.reopen_recent_order_for_correction(
                    order_ref=order_ref,
                    actor=_actor_pos(request),
                    reason=reason,
                )
            else:
                pos_tabs_service.cancel_recent_order(
                    order_ref=order_ref,
                    actor=_actor_pos(request),
                )
        except ValueError as exc:
            status_code = 404 if "não encontrado" in str(exc) else 422
            return Response({"detail": str(exc)}, status=status_code)
        except Exception as exc:
            logger.debug("pos_cancel_recent_sale_failed order=%s user=%s", order_ref, _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao cancelar venda."}, status=400)
        return Response({"ok": True, "order_ref": order_ref})
