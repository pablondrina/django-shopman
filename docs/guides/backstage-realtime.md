# Backstage Realtime

Backstage usa `django-eventstream` para atualizar superfícies operacionais sem polling agressivo.

## Canais

| Kind | Evento principal | Escopo | Origem |
|---|---|---|---|
| `orders` | `backstage-orders-update` | `main` e `shop-<id>` | `order_changed` |
| `production` | `backstage-production-update` | `main` e `shop-<id>` | `production_changed` |
| `kds` | `backstage-kds-update` | `main` e `<kds_instance.ref>` | `KDSTicket.save()` |
| `alerts` | `backstage-alerts-update` | `main` e `shop-<id>` | `OperatorAlert.save()` |

## KDS

`/gestor/kds/<ref>/` assina `/gestor/events/kds/<ref>/` e mantém fallback `every 30s`.
Eventos específicos (`created`, `status-changed`, `station-changed`) também disparam refresh.

O som do KDS é local ao navegador:

- `localStorage["kds_sound_<ref>"]`
- `localStorage["kds_volume_<ref>"]`
- atalho `Alt+S` alterna som

## Produção

`/gestor/producao/` e `/gestor/producao/kds/` assinam `production`.
O payload contém `ref`, `status`, `action` e `output_sku`; a UI refaz o partial canônico.

## Produção ↔ Pedidos

O vínculo operacional é contextual:

- `Order.data["awaiting_wo_refs"]`
- `WorkOrder.meta["serves_order_refs"]`

Essas refs são preenchidas pelos receivers em `shopman/shop/handlers/production_order_sync.py`.

## Produção em Multi-worker

Em produção com mais de um worker, configure Redis para o channel manager do `django-eventstream`:

```python
EVENTSTREAM_CHANNELMANAGER_CLASS = "django_eventstream.channelmanager.RedisChannelManager"
EVENTSTREAM_REDIS = {"host": "localhost", "port": 6379, "db": 0}
```

## Debug

1. Abra DevTools em Network e filtre por `event-stream`.
2. Confirme que `/gestor/events/<kind>/...` fica aberto.
3. Execute a ação operacional e verifique o evento.
4. Se o evento chega e a UI não muda, confira o `hx-trigger`.
5. Se o evento não chega, confira logs do receiver e se `django_eventstream` está instalado.
