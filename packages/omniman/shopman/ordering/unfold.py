from __future__ import annotations

from django.apps import apps


def _order_items_by_channel():
    """Itens do grupo 'Pedidos' (dinâmico por Channel ativo)."""
    from shopman.ordering.models import Channel

    items = [
        # Default operacional: cair em "Novos"
        {
            "title": "Todos os Pedidos",
            "icon": "receipt_long",
            "link": "/admin/ordering/order/?status__exact=new",
        },
    ]

    for channel in Channel.objects.filter(is_active=True).order_by(
        "display_order", "id"
    ):
        items.append(
            {
                "title": channel.name or channel.ref,
                "icon": (channel.config or {}).get("icon", "storefront"),
                # Use o mesmo parâmetro do filtro de FK do Django Admin: channel__id__exact
                "link": f"/admin/ordering/order/?channel__id__exact={channel.id}&status__exact=new",
            }
        )

    return items


def get_sidebar_navigation(request):
    """
    Core (Admin/Unfold): retorna `UNFOLD['SIDEBAR']['navigation']`.

    Compatibilidade:
    - Nesta versão do Unfold, `SIDEBAR.navigation` pode ser callable (resolvido por `_get_value`)
    - Mas `group['items']` NÃO pode ser callable (precisa ser lista)
    """
    navigation = []

    # Central Omnicanal (Core)
    navigation.append(
        {
            "title": "Central Omnicanal",
            "icon": "hub",
            "items": [
                # Default operacional: cair em "Abertas"
                {
                    "title": "Sessões",
                    "icon": "shopping_bag",
                    "link": "/admin/ordering/session/?state__exact=open",
                },
                {
                    "title": "Pedidos",
                    "icon": "receipt_long",
                    # Link do item "pai" (clicável) + subitens por canal
                    "link": "/admin/ordering/order/?status__exact=new",
                    "items": _order_items_by_channel(),
                },
            ],
        }
    )

    config_items = [
        {
            "title": "Canais de Venda",
            "icon": "storefront",
            "link": "/admin/ordering/channel/",
        },
        {
            "title": "Diretivas",
            "icon": "playlist_add_check",
            "link": "/admin/ordering/directive/?status__exact=queued",
        },
    ]

    # Constance (se instalado)
    if apps.is_installed("constance"):
        config_items.append(
            {
                "title": "Configurações",
                "icon": "tune",
                "link": "/admin/constance/config/",
            }
        )

    navigation.append(
        {
            "title": "Configuração",
            "icon": "settings",
            "items": config_items,
        }
    )

    return navigation
