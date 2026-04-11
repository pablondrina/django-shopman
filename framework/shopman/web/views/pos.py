"""POS (Balcao) — point of sale view for counter operations."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from shopman.models import Channel
from shopman.offerman.models import Collection, Product
from shopman.orderman.ids import generate_idempotency_key, generate_session_key
from shopman.orderman.models import Session
from shopman.orderman.services.commit import CommitService
from shopman.orderman.services.modify import ModifyService
from shopman.utils.monetary import format_money
from shopman.web.constants import POS_CHANNEL_REF

logger = logging.getLogger(__name__)


def _staff_required(request):
    if not request.user.is_staff:
        return redirect(f"/admin/login/?next={request.path}")
    return None


def _resolve_customer(phone: str):
    """Look up customer by phone for modifier discounts."""
    try:
        from shopman.guestman.models import Customer
        from shopman.utils.phone import normalize_phone

        normalized = normalize_phone(phone)
        return Customer.objects.select_related("group").filter(phone=normalized).first()
    except Exception as e:
        logger.warning("pos_resolve_customer_failed phone=%s: %s", phone, e, exc_info=True)
        return None


def _load_products():
    """Load products with prices and D-1 flags for the POS grid."""
    products = []
    try:
        from shopman.offerman.models import ListingItem

        items = (
            ListingItem.objects.filter(
                listing__ref=POS_CHANNEL_REF,
                listing__is_active=True,
                is_published=True,
                is_available=True,
            )
            .select_related("product")
            .order_by("product__name")
        )
        for li in items:
            p = li.product
            price_q = li.price_q if li.price_q else p.base_price_q
            products.append(_product_dict(p, price_q))
    except Exception as e:
        logger.warning("pos_load_products_listing_failed: %s", e, exc_info=True)

    if not products:
        for p in Product.objects.filter(is_published=True, is_available=True).order_by("name"):
            products.append(_product_dict(p, p.base_price_q))

    return products


def _product_dict(product, price_q):
    from shopman.web.views._helpers import _line_item_is_d1

    ci = product.collection_items.filter(is_primary=True).select_related("collection").first()
    try:
        is_d1 = _line_item_is_d1(product, listing_ref=POS_CHANNEL_REF)
    except Exception as e:
        logger.debug("pos_d1_check_failed sku=%s: %s", product.sku, e)
        is_d1 = False
    return {
        "sku": product.sku,
        "name": product.name,
        "price_q": price_q,
        "price_display": f"R$ {format_money(price_q)}",
        "collection_ref": ci.collection.ref if ci else "",
        "is_d1": is_d1,
    }


# ── Views ───────────────────────────────────────────────────────────


_PAYMENT_METHODS = [
    ("cash", "Dinheiro"),
    ("pix", "PIX"),
    ("card", "Cartão"),
]


@require_GET
def pos_view(request: HttpRequest) -> HttpResponse:
    """GET /gestao/pos/ — main POS page."""
    denied = _staff_required(request)
    if denied:
        return denied

    from shopman.models import CashRegisterSession, Shop

    shop = Shop.load()
    cash_session = CashRegisterSession.get_open_for_operator(request.user)

    if not cash_session:
        return render(request, "pos/cash_open.html", {"shop": shop})

    products = _load_products()
    collections = list(
        Collection.objects.filter(is_active=True, parent__isnull=True)
        .order_by("sort_order", "name")
        .values("ref", "name")
    )

    return render(request, "pos/index.html", {
        "products": products,
        "collections": collections,
        "shop": shop,
        "payment_methods": _PAYMENT_METHODS,
        "cash_session": cash_session,
    })


@require_POST
def pos_customer_lookup(request: HttpRequest) -> HttpResponse:
    """POST /gestao/pos/customer-lookup/ — HTMX: return customer name partial."""
    denied = _staff_required(request)
    if denied:
        return HttpResponse("", status=403)

    phone = request.POST.get("phone", "").strip()
    if not phone:
        return HttpResponse('<span class="text-muted-foreground">Cliente avulso</span>')

    try:
        from shopman.guestman.models import Customer
        from shopman.utils.phone import normalize_phone

        normalized = normalize_phone(phone)
        customer = Customer.objects.select_related("group").filter(phone=normalized).first()
        if customer:
            name = f"{customer.first_name} {customer.last_name}".strip()
            group_ref = customer.group.ref if customer.group_id else ""
            staff_badge = ' &nbsp;<span class="text-xs text-info-foreground font-bold">(staff)</span>' if group_ref == "staff" else ""
            return HttpResponse(
                f'<span class="text-primary font-semibold" '
                f'data-customer-name="{name}" '
                f'data-customer-ref="{customer.ref}" '
                f'data-customer-group="{group_ref}">'
                f'{name}{staff_badge}'
                f'</span>'
            )
    except Exception:
        logger.exception("pos_customer_lookup failed")

    return HttpResponse('<span class="text-muted-foreground">Cliente n&atilde;o encontrado</span>')


@require_POST
def pos_close(request: HttpRequest) -> HttpResponse:
    """POST /gestao/pos/close/ — HTMX: create order, return result partial."""
    denied = _staff_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    # Parse payload from hx-vals
    payload_str = request.POST.get("payload", "")
    if not payload_str:
        return HttpResponse(
            '<div id="pos-result" class="pos-success" style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            'Carrinho vazio</div>',
            status=422,
        )

    try:
        body = json.loads(payload_str)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(
            '<div id="pos-result" class="pos-success" style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            'Dados inv&aacute;lidos</div>',
            status=400,
        )

    items = body.get("items", [])
    if not items:
        return HttpResponse(
            '<div id="pos-result" class="pos-success" style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            'Carrinho vazio</div>',
            status=422,
        )

    customer_name = body.get("customer_name", "").strip()
    customer_phone = body.get("customer_phone", "").strip()
    payment_method = body.get("payment_method", "cash")

    try:
        channel = Channel.objects.get(ref=POS_CHANNEL_REF)
    except Channel.DoesNotExist:
        return HttpResponse(
            f'<div id="pos-result">Canal {POS_CHANNEL_REF} n&atilde;o configurado</div>',
            status=500,
        )

    session_key = generate_session_key()
    from shopman.config import ChannelConfig

    config = ChannelConfig.for_channel(channel)
    Session.objects.create(
        session_key=session_key,
        channel_ref=channel.ref,
        state="open",
        pricing_policy=config.pricing.policy,
        edit_policy=config.editing.policy,
        handle_type="pos" if not customer_phone else "phone",
        handle_ref=customer_phone or f"pos:{request.user.username}",
    )

    manual_discount = body.get("manual_discount") or {}

    ops = []
    for item in items:
        op = {
            "op": "add_line",
            "sku": item["sku"],
            "qty": int(item.get("qty", 1)),
            "unit_price_q": int(item["unit_price_q"]),
        }
        note = str(item.get("note", "") or "").strip()
        if note:
            op["meta"] = {"note": note}
        ops.append(op)

    if customer_name:
        ops.append({"op": "set_data", "path": "customer.name", "value": customer_name})
    if customer_phone:
        ops.append({"op": "set_data", "path": "customer.phone", "value": customer_phone})

    # Resolve customer for modifier discounts (employee, loyalty)
    if customer_phone:
        customer_obj = _resolve_customer(customer_phone)
        if customer_obj:
            ops.append({"op": "set_data", "path": "customer.ref", "value": customer_obj.ref})
            if customer_obj.group_id:
                ops.append({"op": "set_data", "path": "customer.group", "value": customer_obj.group.ref})

    ops.append({"op": "set_data", "path": "payment.method", "value": payment_method})
    ops.append({"op": "set_data", "path": "origin_channel", "value": "pos"})
    ops.append({"op": "set_data", "path": "fulfillment_type", "value": "pickup"})

    # Manual discount (operator-applied, with reason)
    if manual_discount and int(manual_discount.get("discount_q", 0)) > 0:
        ops.append({"op": "set_data", "path": "manual_discount.type", "value": manual_discount.get("type", "percent")})
        ops.append({"op": "set_data", "path": "manual_discount.value", "value": manual_discount.get("value", 0)})
        ops.append({"op": "set_data", "path": "manual_discount.discount_q", "value": int(manual_discount.get("discount_q", 0))})
        ops.append({"op": "set_data", "path": "manual_discount.reason", "value": manual_discount.get("reason", "")})

    resolved_config = asdict(config)

    try:
        ModifyService.modify_session(
            session_key=session_key,
            channel_ref=channel.ref,
            ops=ops,
            ctx={"actor": f"pos:{request.user.username}"},
            channel_config=resolved_config,
        )
    except Exception as e:
        _msg = str(e).lower()
        if "insuficiente" in _msg or "estoque" in _msg or "stock" in _msg or "unavailable" in _msg:
            error_msg = f"Produto indispon&iacute;vel: {e}"
        else:
            error_msg = f"Erro ao montar pedido: {e}"
        logger.warning("pos_close modify_failed: %s", e, exc_info=True)
        return HttpResponse(
            f'<div id="pos-result" class="pos-error" '
            f'style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            f'{error_msg}</div>',
            status=422,
        )

    try:
        result = CommitService.commit(
            session_key=session_key,
            channel_ref=channel.ref,
            idempotency_key=generate_idempotency_key(),
            ctx={"actor": f"pos:{request.user.username}"},
            channel_config=resolved_config,
        )
    except Exception as e:
        logger.exception("pos_close commit_failed")
        return HttpResponse(
            f'<div id="pos-result" class="pos-error" '
            f'style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            f'Erro ao finalizar: {e}</div>',
            status=400,
        )

    logger.info("pos_close order=%s total=%s", result["order_ref"], result["total_q"])

    total_display = f"R$ {format_money(result['total_q'])}"

    # Return HTML partial with data attributes for Alpine to read
    response = HttpResponse(
        f'<div id="pos-result" '
        f'data-order-ref="{result["order_ref"]}" '
        f'data-total-display="{total_display}" '
        f'class="pos-success">'
        f'Pedido {result["order_ref"]} &mdash; {total_display}'
        f'</div>'
    )
    # Trigger shift summary refresh via HTMX event
    response["HX-Trigger"] = "posOrderCreated"
    return response


@require_GET
def pos_shift_summary(request: HttpRequest) -> HttpResponse:
    """GET /gestao/pos/shift-summary/ — HTMX partial: today's shift totals."""
    denied = _staff_required(request)
    if denied:
        return HttpResponse("", status=403)

    from django.db.models import Sum
    from django.utils import timezone

    from shopman.orderman.models import Order

    today = timezone.localdate()
    qs = Order.objects.filter(
        channel_ref=POS_CHANNEL_REF,
        created_at__date=today,
    ).exclude(status="cancelled")

    shift_count = qs.count()
    shift_total_q = qs.aggregate(t=Sum("total_q"))["t"] or 0

    last_order = qs.order_by("-created_at").first()
    last_ref = last_order.ref if last_order else ""
    last_total_display = format_money(last_order.total_q) if last_order else ""

    return render(request, "pos/partials/shift_summary.html", {
        "shift_count": shift_count,
        "shift_total_display": format_money(shift_total_q),
        "last_ref": last_ref,
        "last_total_display": last_total_display,
    })


@require_POST
def pos_cancel_last(request: HttpRequest) -> HttpResponse:
    """POST /gestao/pos/cancel-last/ — HTMX: cancel the last POS order (within 5 min)."""
    denied = _staff_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    from datetime import timedelta

    from django.utils import timezone

    from shopman.orderman.models import Order
    from shopman.services.cancellation import cancel

    order_ref = request.POST.get("order_ref", "").strip()
    if not order_ref:
        return HttpResponse(
            '<div id="pos-cancel-result" class="pos-error" '
            'style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            'Refer&ecirc;ncia do pedido n&atilde;o informada</div>',
            status=422,
        )

    try:
        order = Order.objects.get(ref=order_ref)
    except Order.DoesNotExist:
        return HttpResponse(
            f'<div id="pos-cancel-result" class="pos-error" '
            f'style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            f'Pedido {order_ref} n&atilde;o encontrado</div>',
            status=404,
        )

    # Only allow cancellation within 5 minutes of creation
    age = timezone.now() - order.created_at
    if age > timedelta(minutes=5):
        return HttpResponse(
            f'<div id="pos-cancel-result" class="pos-error" '
            f'style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            f'Pedido {order_ref} criado h&aacute; mais de 5 minutos — cancelamento n&atilde;o permitido</div>',
            status=422,
        )

    if order.status not in ("new", "confirmed"):
        return HttpResponse(
            f'<div id="pos-cancel-result" class="pos-error" '
            f'style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            f'Pedido {order_ref} n&atilde;o pode ser cancelado (status: {order.status})</div>',
            status=422,
        )

    try:
        cancel(order, reason="pos_operator", actor=f"pos:{request.user.username}")
    except Exception as e:
        logger.exception("pos_cancel_last failed for order %s", order_ref)
        return HttpResponse(
            f'<div id="pos-cancel-result" class="pos-error" '
            f'style="background:var(--error-light);color:rgb(var(--error-foreground))">'
            f'Erro ao cancelar: {e}</div>',
            status=400,
        )

    logger.info("pos_cancel_last order=%s operator=%s", order_ref, request.user.username)

    return HttpResponse(
        f'<div id="pos-cancel-result" class="pos-success" '
        f'style="background:var(--success-light,#dcfce7);color:var(--success-foreground,#166534)">'
        f'Venda {order_ref} cancelada com sucesso</div>'
    )


# ── Cash Register Views ──────────────────────────────────────────────


@require_POST
def pos_cash_open(request: HttpRequest) -> HttpResponse:
    """POST /gestao/pos/caixa/abrir/ — open a new cash register session."""
    denied = _staff_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    from shopman.models import CashRegisterSession

    existing = CashRegisterSession.get_open_for_operator(request.user)
    if existing:
        return redirect("/gestao/pos/")

    try:
        opening_raw = request.POST.get("opening_amount", "0").strip().replace(",", ".")
        opening_amount_q = round(float(opening_raw) * 100)
    except (ValueError, TypeError):
        opening_amount_q = 0

    CashRegisterSession.objects.create(
        operator=request.user,
        opening_amount_q=max(0, opening_amount_q),
    )
    logger.info("pos_cash_open operator=%s opening_q=%s", request.user.username, opening_amount_q)
    return redirect("/gestao/pos/")


@require_POST
def pos_cash_sangria(request: HttpRequest) -> HttpResponse:
    """POST /gestao/pos/caixa/sangria/ — HTMX: register a cash movement."""
    denied = _staff_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    from shopman.models import CashMovement, CashRegisterSession

    session = CashRegisterSession.get_open_for_operator(request.user)
    if not session:
        return HttpResponse(
            '<div class="text-destructive text-sm font-semibold">Caixa não aberto.</div>',
            status=422,
        )

    movement_type = request.POST.get("movement_type", "sangria")
    if movement_type not in ("sangria", "suprimento", "ajuste"):
        movement_type = "sangria"

    try:
        amount_raw = request.POST.get("amount", "0").strip().replace(",", ".")
        amount_q = round(float(amount_raw) * 100)
    except (ValueError, TypeError):
        amount_q = 0

    if amount_q <= 0:
        return HttpResponse(
            '<div class="text-destructive text-sm font-semibold">Valor inválido.</div>',
            status=422,
        )

    reason = request.POST.get("reason", "").strip()
    CashMovement.objects.create(
        session=session,
        movement_type=movement_type,
        amount_q=amount_q,
        reason=reason,
        created_by=request.user.username,
    )
    logger.info(
        "pos_cash_movement type=%s amount_q=%s operator=%s",
        movement_type, amount_q, request.user.username,
    )

    from shopman.utils.monetary import format_money as _fm
    label = {"sangria": "Sangria", "suprimento": "Suprimento", "ajuste": "Ajuste"}.get(movement_type, movement_type)
    return HttpResponse(
        f'<div class="text-success-foreground text-sm font-semibold">'
        f'{label} de R$ {_fm(amount_q)} registrada.</div>'
    )


@require_POST
def pos_cash_close(request: HttpRequest) -> HttpResponse:
    """POST /gestao/pos/caixa/fechar/ — close the current cash register session."""
    denied = _staff_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    from shopman.models import CashRegisterSession

    session = CashRegisterSession.get_open_for_operator(request.user)
    if not session:
        return HttpResponse(
            '<div class="text-destructive font-semibold">Caixa não aberto.</div>',
            status=422,
        )

    try:
        closing_raw = request.POST.get("closing_amount", "0").strip().replace(",", ".")
        closing_amount_q = round(float(closing_raw) * 100)
    except (ValueError, TypeError):
        closing_amount_q = 0

    notes = request.POST.get("notes", "").strip()
    session.close(closing_amount_q=closing_amount_q, notes=notes)
    logger.info("pos_cash_close operator=%s closing_q=%s diff_q=%s", request.user.username, closing_amount_q, session.difference_q)

    return render(request, "pos/cash_close_report.html", {"session": session})
