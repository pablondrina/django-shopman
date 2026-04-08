"""
Notificações em tempo real de novos pedidos no admin.

Usa polling via JSON endpoint (mais confiável com Django runserver).
O cliente JavaScript faz polling a cada 3 segundos.
"""
from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from shopman.omniman.models import Order


@require_GET
@staff_member_required
def order_stream_view(request):
    """
    Endpoint de polling para novos pedidos.

    Parâmetro: ?since=<order_id> retorna pedidos com ID maior que <since>.
    Se não passado, retorna apenas o último ID (para inicialização).
    """
    since_id = request.GET.get("since")

    if since_id:
        # Retorna novos pedidos desde o ID especificado
        try:
            since_id = int(since_id)
        except ValueError:
            return JsonResponse({"error": "Invalid since parameter"}, status=400)

        new_orders = list(
            Order.objects.filter(id__gt=since_id)
            .select_related("channel")
            .order_by("id")[:10]
        )

        orders_data = [
            {
                "id": order.id,
                "ref": order.ref,
                "channel": order.channel.name if order.channel else None,
                "status": order.status,
                "total": str(order.total_q / 100) if order.total_q else "0",
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "handle_ref": order.handle_ref,
            }
            for order in new_orders
        ]

        # Atualiza o last_id para o maior ID retornado
        last_id = new_orders[-1].id if new_orders else since_id

        return JsonResponse({
            "orders": orders_data,
            "last_id": last_id,
        })

    else:
        # Inicialização: retorna apenas o último ID
        last_order = Order.objects.order_by("-id").first()
        last_id = last_order.id if last_order else 0

        return JsonResponse({
            "orders": [],
            "last_id": last_id,
        })
