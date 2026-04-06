"""POS (Balcao) — point of sale view for counter operations."""

from __future__ import annotations

import json
import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from shopman.offering.models import Collection, Product
from shopman.ordering.ids import generate_idempotency_key, generate_session_key
from shopman.ordering.models import Channel, Session
from shopman.ordering.services.commit import CommitService
from shopman.ordering.services.modify import ModifyService
from shopman.utils.monetary import format_money

logger = logging.getLogger(__name__)


def _staff_required(request):
    if not request.user.is_staff:
        return redirect(f"/admin/login/?next={request.path}")
    return None


def _resolve_customer(phone: str):
    """Look up customer by phone for modifier discounts."""
    try:
        from shopman.customers.models import Customer
        from shopman.utils.phone import normalize_phone

        normalized = normalize_phone(phone)
        return Customer.objects.select_related("group").filter(phone=normalized).first()
    except Exception as e:
        logger.warning("pos_resolve_customer_failed phone=%s: %s", phone, e, exc_info=True)
        return None


def _load_products():
    """Load products with prices for the POS grid."""
    products = []
    try:
        from shopman.offering.models import ListingItem

        items = (
            ListingItem.objects.filter(
                listing__ref="balcao",
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
    ci = product.collection_items.filter(is_primary=True).select_related("collection").first()
    return {
        "sku": product.sku,
        "name": product.name,
        "price_q": price_q,
        "price_display": f"R$ {format_money(price_q)}",
        "collection_slug": ci.collection.slug if ci else "",
    }


# ── Views ───────────────────────────────────────────────────────────


_PAYMENT_METHODS = [
    ("dinheiro", "Dinheiro"),
    ("pix", "PIX"),
    ("cartao", "Cartão"),
]


@require_GET
def pos_view(request: HttpRequest) -> HttpResponse:
    """GET /gestao/pos/ — main POS page."""
    denied = _staff_required(request)
    if denied:
        return denied

    from shopman.models import Shop

    products = _load_products()
    collections = list(
        Collection.objects.filter(is_active=True, parent__isnull=True)
        .order_by("sort_order", "name")
        .values("slug", "name")
    )
    shop = Shop.load()

    return render(request, "pos/index.html", {
        "products": products,
        "collections": collections,
        "shop": shop,
        "payment_methods": _PAYMENT_METHODS,
    })


@require_POST
def pos_customer_lookup(request: HttpRequest) -> HttpResponse:
    """POST /gestao/pos/customer-lookup/ — HTMX: return customer name partial."""
    denied = _staff_required(request)
    if denied:
        return HttpResponse("", status=403)

    phone = request.POST.get("phone", "").strip()
    if not phone:
        return HttpResponse('<span style="opacity:0.5">Cliente avulso</span>')

    try:
        from shopman.customers.models import Customer
        from shopman.utils.phone import normalize_phone

        normalized = normalize_phone(phone)
        customer = Customer.objects.filter(phone=normalized).first()
        if customer:
            name = f"{customer.first_name} {customer.last_name}".strip()
            return HttpResponse(
                f'<span data-customer-name="{name}" '
                f'data-customer-ref="{customer.ref}">'
                f'{name} ({customer.ref})</span>'
            )
    except Exception:
        logger.exception("pos_customer_lookup failed")

    return HttpResponse('<span style="opacity:0.5">Cliente n&atilde;o encontrado</span>')


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
    payment_method = body.get("payment_method", "dinheiro")

    try:
        channel = Channel.objects.get(ref="balcao")
    except Channel.DoesNotExist:
        return HttpResponse(
            '<div id="pos-result">Canal balc&atilde;o n&atilde;o configurado</div>',
            status=500,
        )

    session_key = generate_session_key()
    Session.objects.create(
        session_key=session_key,
        channel=channel,
        state="open",
        pricing_policy=channel.pricing_policy,
        edit_policy=channel.edit_policy,
        handle_type="pos" if not customer_phone else "phone",
        handle_ref=customer_phone or f"pos:{request.user.username}",
    )

    ops = []
    for item in items:
        ops.append({
            "op": "add_line",
            "sku": item["sku"],
            "qty": int(item.get("qty", 1)),
            "unit_price_q": int(item["unit_price_q"]),
        })

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

    try:
        ModifyService.modify_session(
            session_key=session_key,
            channel_ref="balcao",
            ops=ops,
            ctx={"actor": f"pos:{request.user.username}"},
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
            channel_ref="balcao",
            idempotency_key=generate_idempotency_key(),
            ctx={"actor": f"pos:{request.user.username}"},
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
    return HttpResponse(
        f'<div id="pos-result" '
        f'data-order-ref="{result["order_ref"]}" '
        f'data-total-display="{total_display}" '
        f'class="pos-success">'
        f'Pedido {result["order_ref"]} &mdash; {total_display}'
        f'</div>'
    )


@require_POST
def pos_cancel_last(request: HttpRequest) -> HttpResponse:
    """POST /gestao/pos/cancel-last/ — HTMX: cancel the last POS order (within 5 min)."""
    denied = _staff_required(request)
    if denied:
        return HttpResponse("Unauthorized", status=403)

    from datetime import timedelta

    from django.utils import timezone

    from shopman.ordering.models import Order
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
