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
  POST /api/v1/backstage/orders/<ref>/settle-delivery-cash/ → settle COD cash
  POST /api/v1/backstage/orders/<ref>/requeue-fiscal/ → requeue NFC-e emission
  POST /api/v1/backstage/orders/<ref>/notes/    → save the operator's kitchen note
  POST /api/v1/backstage/production/plan/                 → plan/adjust matrix cell
  POST /api/v1/backstage/production/<wo_id>/start/        → start a planned WO
  POST /api/v1/backstage/production/<wo_id>/finish/       → finish a started WO
  POST /api/v1/backstage/production/<wo_id>/advance-step/ → next step
  POST /api/v1/backstage/production/quick-finish/         → plan + finish in one step
  POST /api/v1/backstage/production/<wo_id>/void/         → void work order
  POST /api/v1/backstage/closing/                    → finalize day closing
  POST /api/v1/backstage/pos/cash/open/              -> open cash shift
  POST /api/v1/backstage/pos/cash/close/             -> close cash shift
  POST /api/v1/backstage/pos/cash/movement/          → register cash movement
  POST /api/v1/backstage/pos/sale/review/            → validate POS checkout without commit
  POST /api/v1/backstage/pos/sale/recent/cancel/     → cancel recent POS sale
"""

from __future__ import annotations

import json
import logging
from datetime import date

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.permissions import AllowAny
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
    build_pos_customer_search,
    build_pos_shift_summary,
    build_pos_tabs,
)
from shopman.backstage.projections.production import (
    build_production_board,
    build_production_forecast,
    build_production_kds,
    build_production_mise_en_place,
    build_production_weighing,
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
from shopman.backstage.services.exceptions import OrderConflict, OrderError, POSError, ProductionError
from shopman.backstage.services.production import ProductionOrderShortError, ProductionStockShortError
from shopman.shop.services import pos as pos_tabs_service
from shopman.shop.services.pos import PosRecentSaleNotFound
from shopman.shop.services.pos_intent import PosIntentError

from .permissions import HasBackstagePermission, IsBackstageOperator
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
    # Attribute to the active operator (PIN/badge) when present (Opção C, flag ON);
    # otherwise the device session user. ``active_operator_user`` is set by the
    # authorization gate only when SHOPMAN_REQUIRE_ACTIVE_OPERATOR is on.
    operator = getattr(request, "active_operator_user", None)
    if operator is not None:
        return operator.get_username()
    user = getattr(request, "user", None)
    return getattr(user, "username", None) or "operator"


def _production_actor(request) -> str:
    """Audit attribution for production actions, matching the retired HTMX floor
    (``production:<username>``) so the event trail stays consistent post-cutover."""
    return f"production:{_actor(request)}"


def _shortage_response(exc: ProductionError) -> Response | None:
    """Structured error envelope for production shortage states.

    The floor app reproduces the material/order shortage modals from this
    payload (mirrors the POS error envelope shape ``{detail, error: {code,…}}``).
    Returns ``None`` for non-shortage errors so callers fall through to the
    generic 400 handling.
    """
    if isinstance(exc, ProductionStockShortError):
        return Response(
            {
                "detail": str(exc),
                "error": {
                    "code": "material_shortage",
                    "work_order_ref": exc.work_order_ref,
                    "missing": [
                        {
                            "sku": item.sku,
                            "needed": str(item.needed),
                            "available": str(item.available),
                            "shortage": str(item.shortage),
                        }
                        for item in exc.missing
                    ],
                },
            },
            status=409,
        )
    if isinstance(exc, ProductionOrderShortError):
        return Response(
            {
                "detail": str(exc),
                "error": {
                    "code": "order_shortage",
                    "work_order_ref": exc.work_order_ref,
                    "required": str(exc.required),
                    "requested": str(exc.requested),
                    "order_refs": list(exc.order_refs),
                },
            },
            status=409,
        )
    return None


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
        # O servidor CONHECE o turno do operador — o browser nunca decide a
        # atribuição de caixa (um id forjado/null desviaria a venda do turno).
        payload["cash_shift_id"] = cash_shift.pk
        payload["pos_terminal_ref"] = cash_shift.terminal.ref
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
        from shopman.backstage.services.operator import (
            active_operator,
            pin_must_change,
            resolve_active_operator_user,
        )

        pos = build_pos(operator=request.user)
        shift = build_pos_shift_summary()
        query = request.query_params.get("q", "")
        tabs = build_pos_tabs(query=query)
        operator = active_operator(request)
        operator_user = resolve_active_operator_user(request) if operator else None
        return Response({
            "pos": projection_data(pos),
            "shift": projection_data(shift),
            "tabs": projection_data(tabs),
            "operator": operator,
            "pin_must_change": pin_must_change(operator_user),
        })


class POSPaymentStatusView(APIView):
    """GET /pos/payment/<ref>/status/ — polling do estado de pagamento (PIX no PDV).

    O status endpoint do storefront é gateado pela sessão de checkout do CLIENTE
    (anônima) — o operador (staff) não se encaixa. Este é o equivalente operador,
    gateado por operate_pos, para o POS ver a confirmação do PIX chegar sem sair
    do balcão. Reusa build_payment_status (por-order, is_paid/is_cancelled/…).
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def get(self, request, ref: str):
        from django.http import Http404
        from shopman.orderman.models import Order

        from shopman.shop.projections.payment_status import build_payment_status
        from shopman.shop.services import customer_orders

        try:
            order = Order.objects.get(ref=ref)
        except Order.DoesNotExist as exc:
            raise Http404("Order not found") from exc

        # Resolve timers vencidos (auto-cancel de PIX / confirmação) antes de
        # reportar. Camada shop — backstage NUNCA importa storefront (CLAUDE.md).
        try:
            customer_orders.resolve_payment_timeout_if_due(order)
            customer_orders.resolve_confirmation_timeout_if_due(order)
        except Exception:
            logger.warning("pos.payment_status: resolve_timeouts falhou order=%s", ref, exc_info=True)

        return Response(projection_data(build_payment_status(order)))


# ── Generic operator identification (PIN / badge) — shared by all surfaces ──
# (The former POS-specific operator/unlock|lock views were folded into the generic
#  endpoints below; the POS surface now uses them with perm=operate_pos.)
# The device session is the station trust (IsBackstageOperator); these establish
# WHO is operating (active operator) for the Opção C authorization layer. They are
# gated on the device session only — never on an active operator (chicken-egg).

# Permissions a surface may ask the operator to satisfy at unlock (whitelist, so a
# client can only restrict — never widen — who may unlock there).
_OPERATOR_UNLOCK_PERMS = {
    "backstage.operate_pos",
    "backstage.operate_kds",
    "backstage.operate_production",
    "shop.manage_orders",
}


def _validated_unlock_perm(raw) -> tuple[str | None, bool]:
    perm = (str(raw or "").strip()) or None
    if perm is not None and perm not in _OPERATOR_UNLOCK_PERMS:
        return None, False
    return perm, True


class OperatorSessionView(APIView):
    """Terminal lock state: whether the gate is on and who (if anyone) is operating."""

    permission_classes = [IsBackstageOperator]

    def get(self, request):
        from django.conf import settings

        from shopman.backstage.services.operator import (
            active_operator,
            pin_must_change,
            resolve_active_operator_user,
        )

        operator = active_operator(request)
        operator_user = resolve_active_operator_user(request) if operator else None
        return Response({
            "require_operator": bool(getattr(settings, "SHOPMAN_REQUIRE_ACTIVE_OPERATOR", False)),
            "device_user": getattr(request.user, "username", ""),
            "operator": operator,
            "locked": operator is None,
            "pin_must_change": pin_must_change(operator_user),
        })


def _login_username_key(group, request):
    """Chave de rate-limit pela conta-alvo do login.

    O BFF envia JSON (onde `request.POST` fica vazio); o teste e forms enviam
    form-encoded. Lê os dois para que o limite por-username funcione em produção —
    sem isso, JSON colapsaria todas as contas num único bucket global.
    """
    username = request.POST.get("username")
    if not username and "json" in (request.content_type or ""):
        try:
            username = (json.loads(request.body or b"{}") or {}).get("username")
        except (ValueError, TypeError):
            username = None
    return (str(username or "").strip().lower()) or "anon"


@method_decorator(
    ratelimit(key="ip", rate="30/m", method="POST", block=False), name="dispatch"
)
@method_decorator(
    ratelimit(key=_login_username_key, rate="5/m", method="POST", block=False), name="dispatch"
)
class OperatorLoginView(APIView):
    """Login de operador NO PRÓPRIO app (sem bounce pro Django admin).

    Reusa a auth do Django (mesma credencial do admin): valida usuário+senha e abre a
    sessão de dispositivo (o cookie é escopado ao domínio de operador pelo middleware).
    O front mostra um formulário e já entra — uma tela, um submit, sem sair do app. Só
    concede sessão a staff.

    Freio contra brute-force de senha staff: limite por-username (ataque a uma conta)
    de 5/min e teto por-IP de 30/min — generoso porque os dispositivos da loja
    compartilham o IP (NAT). Ambos `block=False`: o handler devolve 429 amigável.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        from django.contrib.auth import authenticate, login

        if getattr(request, "limited", False):
            return Response(
                {
                    "detail": "Muitas tentativas de login. Aguarde um minuto e tente de novo.",
                    "error": {"code": "operator_login_rate_limited"},
                },
                status=429,
            )

        body = request.data or {}
        username = str(body.get("username") or "").strip()
        password = str(body.get("password") or "")
        if not username or not password:
            return Response({"detail": "Informe usuário e senha."}, status=400)

        user = authenticate(request, username=username, password=password)
        if user is None or not user.is_staff:
            return Response(
                {"detail": "Usuário ou senha inválidos.", "error": {"code": "operator_login_invalid"}},
                status=403,
            )
        login(request, user)
        return Response({"ok": True, "device_user": user.get_username()})


class OperatorEligibleView(APIView):
    """Operators who may unlock this surface (the lock-screen picker)."""

    permission_classes = [IsBackstageOperator]

    def get(self, request):
        from shopman.backstage.services.operator import eligible_operators, operator_card

        perm, ok = _validated_unlock_perm(request.query_params.get("perm"))
        if not ok:
            return Response({"detail": "Permissão de operador inválida."}, status=400)
        return Response({"operators": [operator_card(u) for u in eligible_operators(perm=perm)]})


class OperatorUnlockView(APIView):
    """Establish the active operator by PIN (operator_id + pin) or badge (token).

    Optional ``perm`` (the surface's capability) restricts who may unlock here.
    """

    permission_classes = [IsBackstageOperator]

    def post(self, request):
        from django.contrib.auth import get_user_model

        from shopman.backstage.services import operator as operator_service

        body = request.data or {}
        perm, ok = _validated_unlock_perm(body.get("perm"))
        if not ok:
            return Response({"detail": "Permissão de operador inválida."}, status=400)

        badge = str(body.get("badge") or "").strip()
        if badge:
            operator = operator_service.resolve_operator_by_badge(badge, required_perm=perm)
        else:
            operator_id = str(body.get("operator_id") or "").strip()
            pin = str(body.get("pin") or "")
            operator = (
                get_user_model().objects.filter(pk=operator_id, is_active=True).first()
                if operator_id else None
            )
            if operator is not None and not operator_service.verify_operator_pin(operator, pin, required_perm=perm):
                operator = None

        if operator is None:
            return Response(
                {"detail": "Identificação inválida.", "error": {"code": "operator_unlock_invalid"}},
                status=403,
            )
        card = operator_service.set_active_operator(request, operator)
        return Response({"ok": True, "operator": card})


class OperatorLockView(APIView):
    """Lock the terminal (drop the active operator)."""

    permission_classes = [IsBackstageOperator]

    def post(self, request):
        from shopman.backstage.services import operator as operator_service

        operator_service.clear_active_operator(request)
        return Response({"ok": True})


class OperatorPinChangeView(APIView):
    """Operator changes their OWN PIN, proving the current one.

    Knowing the current PIN *is* the authorization: you can only rotate a PIN you
    already hold. Target is the active operator (post-unlock), or an explicit
    ``operator_id`` (the lock-screen forced-change flow, where the temp PIN is the
    "current"). A wrong current PIN counts toward lockout.
    """

    permission_classes = [IsBackstageOperator]

    def post(self, request):
        from shopman.doorman.models import PinCredentialError

        from shopman.backstage.services import operator as operator_service

        body = request.data or {}
        current_pin = str(body.get("current_pin") or "")
        new_pin = str(body.get("new_pin") or "")
        if not current_pin or not new_pin:
            return Response({"detail": "Informe o PIN atual e o novo PIN."}, status=400)

        target = operator_service.resolve_target_for_pin_change(request, body.get("operator_id"))
        if target is None:
            return Response(
                {"detail": "Operador não identificado.", "error": {"code": "no_credential"}},
                status=400,
            )

        try:
            operator_service.change_own_pin(target, current_pin, new_pin)
        except operator_service.PinChangeError as exc:
            status = 423 if exc.code == "locked" else 400
            return Response({"detail": str(exc), "error": {"code": exc.code}}, status=status)
        except PinCredentialError as exc:
            return Response({"detail": str(exc), "error": {"code": "pin_policy"}}, status=400)
        return Response({"ok": True})


class OperatorPinResetView(APIView):
    """Manager resets an operator's PIN → temp PIN + forced change on first use.

    Gated by ``backstage.manage_operators`` (against the active operator when the
    Opção C flag is on, else the device user). The temp PIN is returned once — the
    manager reads it to the operator; only its HMAC digest is stored.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.manage_operators"

    def post(self, request):
        from django.contrib.auth import get_user_model
        from shopman.doorman.models import PinCredentialError

        from shopman.backstage.services import operator as operator_service

        body = request.data or {}
        user_model = get_user_model()
        target = None
        raw_id = str(body.get("user_id") or body.get("operator_id") or "").strip()
        username = str(body.get("username") or "").strip()
        if raw_id:
            target = user_model.objects.filter(pk=raw_id, is_staff=True).first()
        elif username:
            target = user_model.objects.filter(username=username, is_staff=True).first()

        try:
            temp_pin = operator_service.reset_operator_pin(target, temp_pin=body.get("temp_pin"))
        except operator_service.PinChangeError as exc:
            status = 404 if exc.code == "no_target" else 400
            return Response({"detail": str(exc), "error": {"code": exc.code}}, status=status)
        except PinCredentialError as exc:
            return Response({"detail": str(exc), "error": {"code": "pin_policy"}}, status=400)
        return Response({"ok": True, "temp_pin": temp_pin, "must_change": True})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Production board",
        responses={200: OpenApiResponse(description="Work orders for the selected date.")},
    ),
)
class ProductionBoardView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_production"

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
        summary="Production forecast board (airport-style panel for the store team)",
        responses={200: OpenApiResponse(description="Per-batch forecast: quantities, ETA and status.")},
    ),
)
class ProductionForecastView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_production"

    def get(self, request):
        selected = _parse_date(request.query_params.get("date"))
        forecast = build_production_forecast(selected_date=selected)
        return Response({"forecast": projection_data(forecast)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Production KDS (started work orders)",
        responses={200: OpenApiResponse(description="Live KDS board for production.")},
    ),
)
class ProductionKDSView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_production"

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
        summary="Mise en place (aggregated material needs for the day)",
        responses={200: OpenApiResponse(description="Aggregated ingredient list for open work orders.")},
    ),
)
class ProductionMiseEnPlaceView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_production"

    def get(self, request):
        selected = _parse_date(request.query_params.get("date"))
        expand = str(request.query_params.get("expand", "")).lower() in ("1", "true", "yes")
        mise_en_place = build_production_mise_en_place(
            selected_date=selected,
            expand=expand,
        )
        return Response({"mise_en_place": projection_data(mise_en_place)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Weighing tickets (per-prep scaled ingredients + blind codes)",
        responses={200: OpenApiResponse(description="Per-prep weighing tickets for the day.")},
    ),
)
class ProductionWeighingView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_production"

    def get(self, request):
        selected = _parse_date(request.query_params.get("date"))
        weighing = build_production_weighing(
            selected_date=selected,
            position_ref=request.query_params.get("position", ""),
            base_recipe=request.query_params.get("base_recipe", ""),
        )
        return Response({"weighing": projection_data(weighing)})


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
    required_permission = "shop.manage_orders"

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
    required_permission = "shop.manage_orders"

    def get(self, request):
        queue = build_two_zone_queue()
        return Response({"queue": projection_data(queue)})


# ── Order action endpoints ────────────────────────────────────────────


class _OrderActionBase(APIView):
    """Shared base for order action endpoints (advance/confirm/reject/cancel)."""

    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

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
        responses={
            200: OpenApiResponse(description="Order confirmed."),
            409: OpenApiResponse(description="Order already left the pending state."),
        },
    ),
)
class OrderConfirmView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        try:
            orders_service.confirm_order(order, actor=_actor(request))
        except OrderConflict as exc:
            return Response({"detail": str(exc)}, status=409)
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao confirmar."}, status=400)
        return Response({"ok": True, "ref": ref})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Reject pending order",
        responses={
            200: OpenApiResponse(description="Order rejected."),
            409: OpenApiResponse(description="Order already left the pending state."),
        },
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
        cancellation_code = (request.data.get("cancellation_code") or "").strip()
        try:
            orders_service.reject_order(
                order,
                reason=reason,
                actor=_actor(request),
                rejected_by="operator",
                cancellation_code=cancellation_code,
            )
        except OrderConflict as exc:
            return Response({"detail": str(exc)}, status=409)
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
        # The operator's typed/preset text (may be blank). It rides through as the
        # customer-facing note; the audit reason falls back to a generic label.
        operator_reason = (request.data.get("reason") or "").strip()
        reason = operator_reason or "Cancelado pelo operador"
        cancellation_code = (request.data.get("cancellation_code") or "").strip()
        try:
            orders_service.cancel_order(
                order,
                reason=reason,
                actor=_actor(request),
                cancellation_code=cancellation_code,
                customer_note=operator_reason,
            )
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao cancelar."}, status=400)
        return Response({"ok": True, "ref": ref})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Valid cancellation reasons for an order (marketplace-aware)",
        responses={200: OpenApiResponse(description="Reason list.")},
    ),
)
class OrderCancellationReasonsView(_OrderActionBase):
    def get(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        return Response({"reasons": orders_service.cancellation_reasons(order)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Settle delivery cash-on-delivery into the operator's open shift",
        responses={200: OpenApiResponse(description="Cash settled.")},
    ),
)
class OrderSettleDeliveryCashView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        try:
            amount_q = orders_service.settle_delivery_cash(
                order,
                operator=request.user,
                amount_raw=str(request.data.get("amount", "")),
                actor=_actor(request),
            )
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha no acerto de dinheiro."}, status=400)
        return Response({"ok": True, "ref": ref, "amount_q": amount_q})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Requeue fiscal (NFC-e) emission for an order",
        responses={200: OpenApiResponse(description="Fiscal emission requeued.")},
    ),
)
class OrderRequeueFiscalView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        try:
            orders_service.requeue_fiscal_emission(order, actor=_actor(request))
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao reprocessar fiscal."}, status=400)
        return Response({"ok": True, "ref": ref})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Dispatch (or re-dispatch) the external courier ride",
        responses={200: OpenApiResponse(description="Courier dispatch queued.")},
    ),
)
class OrderCourierDispatchView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        try:
            orders_service.courier_dispatch(order, actor=_actor(request))
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao despachar."}, status=400)
        return Response({"ok": True, "ref": ref})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Cancel the active external courier ride",
        responses={200: OpenApiResponse(description="Courier ride cancelled.")},
    ),
)
class OrderCourierCancelView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        reason_id = request.data.get("reason_id")
        try:
            orders_service.courier_cancel(
                order,
                actor=_actor(request),
                reason_id=int(reason_id) if reason_id is not None else None,
            )
        except (TypeError, ValueError):
            return Response({"detail": "reason_id inválido."}, status=400)
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao cancelar a corrida."}, status=400)
        return Response({"ok": True, "ref": ref})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Quote the external courier ride without dispatching",
        responses={200: OpenApiResponse(description="Courier quote.")},
    ),
)
class OrderCourierQuoteView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        try:
            quote = orders_service.courier_quote(order)
        except OrderError as exc:
            return Response({"detail": str(exc) or "Cotação indisponível."}, status=400)
        return Response({"ok": True, "ref": ref, "quote": quote})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Save the operator's kitchen note on an order",
        responses={200: OpenApiResponse(description="Note saved.")},
    ),
)
class OrderNotesView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        notes = str(request.data.get("notes", "") or "")
        orders_service.save_kitchen_note(order, notes=notes)
        return Response({"ok": True, "ref": ref})


def _operator_identity(request) -> tuple[int, str]:
    """The operator to credit a claim to: the active operator (PIN/badge) when
    present, else the device session user."""
    from shopman.backstage.services.operator import active_operator

    card = active_operator(request)
    if card and card.get("id"):
        return int(card["id"]), str(card.get("name") or card.get("username") or "operador")
    user = getattr(request, "user", None)
    name = (user.get_full_name().strip() or user.get_username()) if user else "operador"
    return (user.pk if user else 0), name


class OrderAssignView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        operator_id, operator_name = _operator_identity(request)
        orders_service.assign_order(
            order, operator_id=operator_id, operator_name=operator_name, actor=_actor(request)
        )
        return Response({"ok": True, "ref": ref, "assigned_operator": operator_name})


class OrderUnassignView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        orders_service.unassign_order(order, actor=_actor(request))
        return Response({"ok": True, "ref": ref})


class OrderCommentView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        note = str(request.data.get("note", "") or "")
        try:
            orders_service.add_comment(order, note=note, actor=_actor(request))
        except OrderError as exc:
            return Response({"detail": str(exc) or "Comentário inválido."}, status=400)
        return Response({"ok": True, "ref": ref})


# ── Production action endpoints ───────────────────────────────────────


class _ProductionActionBase(APIView):
    """Shared gate for production action endpoints."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_production"


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Plan (or adjust) production for a recipe/date (matrix cell)",
        responses={200: OpenApiResponse(description="Planned quantity set.")},
    ),
)
class WorkOrderPlanView(_ProductionActionBase):
    def post(self, request):
        recipe_id = request.data.get("recipe_id") or request.data.get("recipe")
        quantity = request.data.get("quantity")
        target_date = request.data.get("target_date")
        if not (recipe_id and target_date and quantity is not None):
            return Response(
                {"detail": "recipe_id, target_date e quantity são obrigatórios."},
                status=400,
            )
        source = (request.data.get("source") or "").strip()
        try:
            output_sku, wo_ref, qty, result = production_service.apply_planned(
                recipe_id=recipe_id,
                quantity=str(quantity).strip(),
                target_date_value=str(target_date).strip(),
                position_ref=str(request.data.get("position_ref") or "").strip(),
                operator_ref=str(request.data.get("operator_ref") or "").strip(),
                reason=str(request.data.get("reason") or "").strip(),
                actor=_production_actor(request),
                force=bool(request.data.get("force")),
                source_ref="formula:suggestion" if source == "suggested" else "production_matrix",
            )
        except ProductionError as exc:
            shortage = _shortage_response(exc)
            if shortage is not None:
                return shortage
            return Response({"detail": str(exc) or "Falha ao planejar produção."}, status=400)
        except ValueError as exc:
            return Response({"detail": str(exc) or "Dados de planejamento inválidos."}, status=400)
        return Response({
            "ok": True,
            "result": result,
            "output_sku": output_sku,
            "wo_ref": wo_ref,
            "quantity": str(qty),
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Start a planned work order",
        responses={200: OpenApiResponse(description="Work order started.")},
    ),
)
class WorkOrderStartView(_ProductionActionBase):
    def post(self, request, wo_id: int):
        try:
            wo_ref, quantity = production_service.apply_start(
                work_order_id=wo_id,
                quantity=str(request.data.get("quantity") or "").strip(),
                position_id=str(request.data.get("position_id") or "").strip(),
                operator_ref=str(request.data.get("operator_ref") or "").strip(),
                note=str(request.data.get("note") or "").strip(),
                actor=_production_actor(request),
            )
        except ProductionError as exc:
            return Response({"detail": str(exc) or "Falha ao iniciar produção."}, status=400)
        except ValueError as exc:
            return Response({"detail": str(exc) or "Dados inválidos."}, status=400)
        return Response({"ok": True, "wo_ref": wo_ref, "quantity": str(quantity)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Finish a started work order (force overrides material shortage)",
        responses={200: OpenApiResponse(description="Work order finished.")},
    ),
)
class WorkOrderFinishView(_ProductionActionBase):
    def post(self, request, wo_id: int):
        try:
            wo_ref, quantity = production_service.apply_finish(
                work_order_id=wo_id,
                quantity=str(request.data.get("quantity") or "").strip(),
                actor=_production_actor(request),
                force=bool(request.data.get("force")),
            )
        except ProductionError as exc:
            shortage = _shortage_response(exc)
            if shortage is not None:
                return shortage
            return Response({"detail": str(exc) or "Falha ao concluir produção."}, status=400)
        except ValueError as exc:
            return Response({"detail": str(exc) or "Dados inválidos."}, status=400)
        return Response({"ok": True, "wo_ref": wo_ref, "quantity": str(quantity)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Advance work order step",
        responses={200: OpenApiResponse(description="Step advanced.")},
    ),
)
class WorkOrderAdvanceStepView(_ProductionActionBase):
    def post(self, request, wo_id: int):
        try:
            new_index = production_service.apply_advance_step(
                work_order_id=wo_id,
                actor=_production_actor(request),
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
class WorkOrderQuickFinishView(_ProductionActionBase):
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
                actor=_production_actor(request),
            )
        except ProductionError as exc:
            shortage = _shortage_response(exc)
            if shortage is not None:
                return shortage
            return Response({"detail": str(exc) or "Falha ao finalizar."}, status=400)
        return Response({"ok": True, "wo_ref": getattr(wo, "ref", None)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Void (cancel) a work order",
        responses={200: OpenApiResponse(description="Work order voided.")},
    ),
)
class WorkOrderVoidView(_ProductionActionBase):
    def post(self, request, wo_id: int):
        reason = (request.data.get("reason") or "Estornado pelo operador").strip()
        try:
            ref = production_service.apply_void(
                wo_id, actor=_production_actor(request), reason=reason,
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


class POSCashCloseBlockingView(APIView):
    """Fecha (contagem cega) o turno que bloqueia o terminal — supervisório.

    Destrava o beco: terminal com turno aberto que não é do operador atual.
    Gerente (perform_closing) ou o dono do turno fecham daqui; operador comum
    não (anti-fraude) → 403.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        from shopman.backstage.services.exceptions import POSPermissionError

        shift_id = request.data.get("shift_id")
        amount = request.data.get("closing_amount", "0")
        notes = (request.data.get("notes") or "").strip()
        if not shift_id:
            return Response({"detail": "shift_id é obrigatório."}, status=400)
        # O subsistema de caixa usa request.user (abrir grava operator=request.user;
        # a projection checa request.user). Mantém a mesma identidade aqui.
        try:
            result = pos_service.close_blocking_shift(
                actor_user=request.user,
                shift_id=shift_id,
                closing_amount_raw=str(amount),
                notes=notes,
            )
        except POSPermissionError as exc:
            return Response(
                {"detail": str(exc), "error": {"code": "cash_close_forbidden", "message": str(exc)}},
                status=403,
            )
        except Exception as exc:
            logger.debug("pos_cash_close_blocking_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao fechar o turno."}, status=400)
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
    return _actor(request)


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
    get=extend_schema(
        tags=["backstage"],
        summary="Search customers by any unique key (name/phone/CPF/email)",
        responses={200: OpenApiResponse(description="List of matching customers.")},
    ),
)
class POSCustomerSearchView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        results = build_pos_customer_search(query)
        return Response({"results": [projection_data(result) for result in results]})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Resolve or create a customer just-in-time (get-or-create)",
        responses={200: OpenApiResponse(description="The resolved/created customer lookup.")},
    ),
)
class POSCustomerResolveView(APIView):
    """Just-in-time get-or-create: when the operator defines a customer on the
    counter, resolve them (phone/CPF/email) or create the record NOW, returning
    the same lookup projection as customer_lookup (ref + memory + addresses)."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_pos"

    def post(self, request):
        body = request.data or {}
        try:
            customer = pos_tabs_service.resolve_or_create_customer(
                name=str(body.get("customer_name") or "").strip(),
                phone=str(body.get("customer_phone") or "").strip(),
                tax_id=str(body.get("customer_tax_id") or "").strip(),
                email=str(body.get("customer_email") or "").strip(),
                operator_username=_username(request),
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc) or "Cadastro conflitante.", "error": {"code": "customer_conflict"}},
                status=422,
            )
        if not customer:
            return Response({"customer": None})
        phone = customer.get("phone") or ""
        lookup = build_pos_customer_lookup(phone) if phone else None
        return Response({"customer": projection_data(lookup) if lookup else None})


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
        except ValueError as exc:
            return Response({"detail": str(exc) or "Falha ao finalizar venda."}, status=422)
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
            # Cancelar venda fechada é exceção auditada: sempre sob PIN de gerente,
            # mesmo dentro da janela otimista do operador.
            pos_tabs_service.validate_manager_override(
                request.data.get("manager_approval"),
                operator_username=_username(request),
                action="cancel_recent_sale",
            )
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
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except PosRecentSaleNotFound as exc:
            return Response({"detail": str(exc)}, status=404)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=422)
        return Response({"ok": True, "order_ref": order_ref})
