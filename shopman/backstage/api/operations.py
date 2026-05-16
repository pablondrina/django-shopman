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
    build_pos,
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
from shopman.backstage.services.exceptions import OrderError, ProductionError
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
    return {
        "id": shift.pk,
        "terminal_ref": shift.terminal.ref,
        "operator": shift.operator.get_username(),
        "status": shift.status,
        "opened_at": shift.opened_at.isoformat() if shift.opened_at else "",
        "closed_at": shift.closed_at.isoformat() if shift.closed_at else "",
        "opening_amount_q": shift.opening_amount_q,
        "blind_closing_amount_q": shift.blind_closing_amount_q,
        "expected_amount_q": shift.expected_amount_q,
        "difference_q": shift.difference_q,
    }


def _pos_payload_with_runtime(request, body: dict) -> dict:
    """Attach the active POS runtime context that browser surfaces should not invent."""
    payload = dict(body or {})
    try:
        from shopman.backstage.models import CashShift

        cash_shift = CashShift.get_open_for_operator(request.user)
    except Exception:
        logger.debug("pos_runtime_payload_enrichment_failed user=%s", _actor(request), exc_info=True)
        return payload
    if cash_shift:
        payload.setdefault("cash_shift_id", cash_shift.pk)
        payload.setdefault("pos_terminal_ref", cash_shift.terminal.ref)
    return payload


def _pos_sale_review_payload(review) -> dict:
    return {
        "intent_version": review.intent_version,
        "tab_code": review.tab_code,
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
        pos = build_pos()
        shift = build_pos_shift_summary()
        query = request.query_params.get("q", "")
        tabs = build_pos_tabs(query=query)
        return Response({
            "pos": projection_data(pos),
            "shift": projection_data(shift),
            "tabs": projection_data(tabs),
        })


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
        tab_code = (request.data.get("tab_code") or "").strip()
        label = (request.data.get("label") or "").strip()
        if not tab_code:
            return Response({"detail": "Código da comanda é obrigatório."}, status=400)
        try:
            tab = pos_tabs_service.register_pos_tab(tab_code=tab_code, label=label)
        except Exception as exc:
            logger.debug("pos_tab_create_failed tab_code=%s", tab_code, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao criar comanda."}, status=400)
        return Response({"ok": True, "tab": tab})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Open or load a POS tab",
        responses={200: OpenApiResponse(description="Tab payload (items + customer + tab_code).")},
    ),
)
class POSTabOpenView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request, tab_code: str):
        try:
            payload = pos_tabs_service.open_pos_tab(
                channel_ref=POS_CHANNEL_REF,
                tab_code=tab_code,
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except Exception as exc:
            logger.debug("pos_tab_open_failed tab_code=%s", tab_code, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao abrir comanda."}, status=400)
        return Response(payload)


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
            "tab_code": result.tab_code,
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
        customer = pos_tabs_service.resolve_customer(phone)
        if customer is None:
            return Response({"customer": None})
        return Response({
            "customer": {
                "ref": getattr(customer, "ref", ""),
                "name": getattr(customer, "name", "") or getattr(customer, "first_name", ""),
                "phone": getattr(customer, "phone", "") or phone,
                "loyalty_group": getattr(customer, "loyalty_group", "") or "",
                "is_staff": bool(getattr(customer, "is_staff", False)),
            }
        })


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
            "tab_code": getattr(result, "tab_code", None),
        })
