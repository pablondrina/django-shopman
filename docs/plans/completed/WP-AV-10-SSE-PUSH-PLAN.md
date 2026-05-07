# WP-AV-10 — SSE Push (Active Stock & Pause Updates)

**Status:** concluído e validado em 2026-05-05.

**Nota de execução 2026-05-05:** a implementação final está em `shopman/shop/handlers/_sse_emitters.py`, `shopman/storefront/urls.py`, templates do storefront e `shopman/shop/eventstream.py`. O runtime canônico usa Daphne/ASGI para desenvolvimento/CI e Redis fanout via `EVENTSTREAM_REDIS` quando `REDIS_URL` está configurado; não há pendência de trocar para Redis depois.

**Origem:** WP diferido do [AVAILABILITY-PLAN](AVAILABILITY-PLAN.md#wp-av-10--gap-a-push-ativo-via-htmx-sse). Esta é a expansão completa para execução standalone.

**Dependências do contexto:** STOCKMAN-SCOPE-UNIFICATION e WPs AV-01 a AV-09 + AV-11 + AV-12 já estão concluídos no `main`. Este plano não bloqueia nem é bloqueado por nenhum outro WP atualmente em execução.

**Não-objetivo:** este plano **não** implementa a UI de countdown da fermata (isso é WP-AV-13, plano separado). Apenas entrega o canal de push que o WP-AV-13 — e qualquer outra superfície futura — pode consumir.

---

## 1. Resumo executivo

Hoje toda mudança de disponibilidade no Shopman é descoberta **lazy**: cliente abre uma página, cliente vê o estado daquele momento. Se o operador dá baixa de estoque, pausa um produto, ou outro cliente reserva o último item, **clientes com a mesma página aberta continuam vendo o estado antigo até refresh manual**. Steppers podem permitir +1 num produto que já se esgotou; a primeira pista de problema vem ao tentar adicionar e levar 422.

Este plano introduz **push ativo** via Server-Sent Events: o servidor publica eventos curtos (`stock-update`, `product-paused`, `listing-changed`) e clientes inscritos refazem GET das partials afetadas (badge, stepper, cart line). HTMX já tem extensão SSE pronta. Operacionalmente é leve (uma conexão por aba aberta) e degrada graciosamente — se o cliente está offline ou a conexão quebra, comportamento volta ao lazy atual.

---

## 2. Decisão arquitetural — `django-eventstream`

Avaliei três caminhos antes de propor:

| Opção | Prós | Contras | Decisão |
|---|---|---|---|
| `django-eventstream` (Fanout/Justin Karneges) | Integração HTMX documentada, Redis fanout, encaixe simples na stack Django/ASGI atual | Dependência nova; modelo "rooms" é específico | **Adotar** |
| Django Channels (websockets/SSE) | Suportado oficial, escalável | Exige migração toda do projeto pra ASGI; mata o runserver síncrono atual; reescreve a stack | Rejeitar |
| Bare `StreamingHttpResponse` | Zero dep | Cada conexão pendura um worker; não escala além de 5–10 abas simultâneas; sem Redis fan-out | Rejeitar |

**Justificativa executada**: o projeto usa Daphne/ASGI e mantém `django-eventstream` como camada simples de SSE. Redis é infraestrutura canônica do runtime, então `send_event` funciona em multi-worker quando `REDIS_URL` está presente.

**Pacote**: `django-eventstream` (PyPI). **Adicionar** em `pyproject.toml` no grupo principal de deps.

---

## 3. Modelo de eventos

### 3.1 Topologia de canais (rooms)

Um channel SSE por **canal de venda** do shopman:
- `stock-web` — eventos do canal `web`
- `stock-balcao` — eventos do canal `balcao`
- `stock-delivery` — eventos do canal `delivery`
- `stock-whatsapp` — eventos do canal `whatsapp`

Clientes do storefront se conectam apenas ao canal correspondente (via `STOREFRONT_CHANNEL_REF`, default `web`). Operador no POS conecta ao `stock-balcao`. Push é per-channel — não há vazamento entre canais.

### 3.2 Tipos de evento

| Type | Payload | Quando dispara |
|---|---|---|
| `stock-update` | `{"sku": "BAGUETE"}` | `Hold` create/release; `Move` post_save em quant saleable |
| `product-paused` | `{"sku": "BAGUETE", "is_sellable": false}` | `Product.is_sellable` muda |
| `listing-changed` | `{"sku": "BAGUETE"}` | `ListingItem.is_published` ou `is_sellable` muda |

Payloads são **mínimos** — só o SKU. O cliente, ao receber, refaz GET da partial relevante (badge, stepper, item) que já tem todo o estado fresco do servidor. Isso evita serializar muito no servidor e preserva a fonte única de verdade do `availability.check()`.

### 3.3 Filtragem por SKU visível

O cliente recebe TODOS os eventos do seu canal. Mas só refaz GET para SKUs **visíveis na página atual**.

- HTMX SSE extension permite filtrar via `sse-swap="stock-update"` em elementos com `data-sku="BAGUETE"`. Eventos que não contêm o SKU do elemento são ignorados.
- Padrão: cada card/stepper/cart-line carrega `data-sku="<sku>"`. Listener verifica `event.data.sku === el.dataset.sku` antes de refetch.

Custo: cliente recebe stream por canal inteiro. Para Nelson (~50 SKUs ativos) e talvez 100 abas concorrentes = alguns kbps/aba — desprezível.

---

## 4. Sources de evento — onde plugar

### 4.1 Stockman `Hold` create/release/fulfill

Hoje `Hold` muda de status em `StockHolds.hold/confirm/release/fulfill` (em [packages/stockman/shopman/stockman/services/holds.py](../../packages/stockman/shopman/stockman/services/holds.py)).

**Onde plugar o emit**: post_save signal no model `Hold` (não no service — operador admin também muda holds e precisa disparar).

```python
# shopman/shop/handlers/_sse_emitters.py (NOVO arquivo)
@receiver(post_save, sender=Hold)
def emit_stock_update_on_hold(sender, instance, **kwargs):
    _emit_for_sku(instance.sku, event_type='stock-update')
```

Emit é fire-and-forget (não bloqueia a transação). Falha silencia em log.

### 4.2 Stockman `Move` post_save

Move atinge stock físico. Quando `delta != 0` em quant saleable, disponibilidade mudou. Plugar mesmo padrão.

```python
@receiver(post_save, sender=Move)
def emit_stock_update_on_move(sender, instance, **kwargs):
    if instance.quant_id:
        sku = instance.quant.sku
        _emit_for_sku(sku, event_type='stock-update')
```

### 4.3 Offerman `Product.is_sellable` change

Plugar via post_save com check do field changed. Ou via `pre_save` capturando old value:

```python
@receiver(pre_save, sender=Product)
def _track_sellable_change(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Product.objects.only('is_sellable').get(pk=instance.pk)
            instance._was_sellable = old.is_sellable
        except Product.DoesNotExist:
            instance._was_sellable = None

@receiver(post_save, sender=Product)
def emit_pause_change(sender, instance, **kwargs):
    if getattr(instance, '_was_sellable', None) != instance.is_sellable:
        _emit_for_sku(
            instance.sku,
            event_type='product-paused',
            extra={'is_sellable': instance.is_sellable},
        )
```

### 4.4 Offerman `ListingItem` change

Mesma pattern do Product. Foco nos fields `is_published` e `is_sellable`.

### 4.5 Helper canônico `_emit_for_sku`

```python
def _emit_for_sku(sku: str, *, event_type: str, extra: dict | None = None) -> None:
    """Publish an SSE event to every active channel that lists this SKU.

    Resolves channels via Listing membership (avoids spamming channels that
    don't sell this SKU). Falls back to every active channel when the SKU
    has no Listing (untracked products).
    """
    from django_eventstream import send_event
    payload = {'sku': sku, **(extra or {})}
    try:
        channels = _channels_for_sku(sku)
        for ch in channels:
            send_event(f'stock-{ch}', event_type, payload)
        # Invalidate cache so next /api/availability/ call sees fresh data.
        from django.core.cache import cache
        for ch in channels:
            cache.delete(f'availability:{sku}:{ch}')
    except Exception:
        logger.warning('SSE emit failed sku=%s type=%s', sku, event_type, exc_info=True)
```

---

## 5. Endpoint SSE

`django-eventstream` expõe via URL pattern. Adicionar em `shopman/shop/web/urls.py`:

```python
from django_eventstream.views import events as eventstream_view

path(
    'storefront/stock/events/',
    eventstream_view,
    {'channels': ['stock-{channel_ref}']},
    name='stock_events',
),
```

`{channel_ref}` é resolvido via querystring: o cliente passa `?channel_ref=web`.

**Auth**: público. Eventos são broadcast por canal — não há informação por usuário. Anônimos podem assinar livremente. Nada sensível trafega.

**Heartbeat**: `django-eventstream` envia keepalive a cada 30s automaticamente. CDNs e proxies que cortam conexões idle (>30s) não interferem.

---

## 6. Cliente HTMX

### 6.1 Habilitar a extensão SSE

Em [base.html](../../shopman/shop/templates/storefront/base.html), adicionar antes dos blocos:

```html
<script src="https://unpkg.com/htmx.org@1.9.10/dist/ext/sse.js"></script>

{# Wrapper que abre uma única conexão SSE para o canal atual. #}
<div hx-ext="sse"
     sse-connect="{% url 'storefront:stock_events' %}?channel_ref={{ channel_ref|default:'web' }}">
  {# Listeners individuais ficam dentro de cada card/stepper/line via sse-swap. #}
</div>
```

### 6.2 Pattern de refresh per-element

Cada elemento que precisa reagir a `stock-update` declara:

```html
<div hx-get="{% url 'api:availability' item.sku %}"
     hx-trigger="sse:stock-update[detail.sku=='{{ item.sku }}']"
     data-sku="{{ item.sku }}">
  ...
</div>
```

Note o filtro inline `[detail.sku=='SKU']` — HTMX SSE extension oferece esse `[expression]` syntax para validar antes de disparar o swap.

**Em produção, usar uma única partial** que serve o badge + stepper + qty inline; aí o swap atualiza tudo de uma vez. Reduz fan-out de queries.

### 6.3 Pages a instrumentar (mínimo)

- **PDP** ([product_detail.html](../../shopman/shop/templates/storefront/product_detail.html)): stepper + badge.
- **Menu/listing** ([_catalog_item_grid.html](../../shopman/shop/templates/storefront/partials/_catalog_item_grid.html)): cada card.
- **Cart drawer** + **cart page**: cada linha de item.
- **Availability preview** ("direto do forno"): cada card.

Cada um precisa de um partial GET-able no servidor que devolve o card/stepper/badge atualizado para um único SKU.

---

## 7. Cache invalidation

Hoje `/api/availability/<sku>/` ([api/availability.py](../../shopman/shop/api/availability.py)) cacheia por 10s. Sem invalidation, push perde sincronia com o cache.

**Solução**: o `_emit_for_sku` também invalida o cache (ver §4.5). Próxima leitura via `/api/availability/` ou via `availability_for_sku` reflete a mudança.

Se o agente preferir, pode também invalidar no signal antes do emit (mais defensivo).

---

## 8. Configuração

### 8.1 settings.py

```python
INSTALLED_APPS = [
    ...,
    'django_eventstream',
]

EVENTSTREAM_STORAGE_CLASS = 'django_eventstream.storage.DjangoModelStorage'
# REDIS_URL configura EVENTSTREAM_REDIS para fanout multi-worker.
```

Migrações: `python manage.py migrate django_eventstream` cria as tabelas.

### 8.2 Production: Redis fanout

Executado no runtime canônico: `REDIS_URL` deriva `EVENTSTREAM_REDIS`, e os checks de deploy falham se o fanout SSE multi-worker não estiver configurado em produção.

---

## 9. Testes

### 9.1 Unit — emit dispara para canais corretos

```python
# shopman/shop/tests/test_sse_emitters.py
@patch('shopman.shop.handlers._sse_emitters.send_event')
def test_emit_stock_update_on_hold_create(mock_send, db, hold_factory):
    hold = hold_factory(sku='BAGUETE')
    # Resolve canais que listam BAGUETE
    expected_channels = ['stock-web', 'stock-balcao']
    calls = [call(ch, 'stock-update', {'sku': 'BAGUETE'}) for ch in expected_channels]
    mock_send.assert_has_calls(calls, any_order=True)
```

### 9.2 Integration — endpoint SSE devolve frame

```python
def test_sse_endpoint_streams_event(client, db):
    resp = client.get('/storefront/stock/events/?channel_ref=web', HTTP_ACCEPT='text/event-stream')
    assert resp.status_code == 200
    assert resp['Content-Type'].startswith('text/event-stream')
    # Disparar emit em outra thread / outro request, verificar que o frame chega
    # (usar StreamingHttpResponse iterator ou django-eventstream's test mode)
```

### 9.3 E2E manual via preview

1. Abrir PDP de BAGUETE no preview (dev server).
2. Em outra janela, rodar `Hold.objects.create(...)` via `manage.py shell`.
3. Confirmar que o badge/stepper da PDP refresha sem reload manual.
4. Rodar `Product.objects.filter(sku='BAGUETE').update(is_sellable=False)`.
5. Confirmar que badge muda pra "Indisponível" sem reload.

---

## 10. Trabalho desmembrado (sub-WPs)

Ordem recomendada. Cada um é commitable de forma independente.

### WP-SSE-01 — Setup `django-eventstream`

- Adicionar `django-eventstream` em `pyproject.toml`.
- `INSTALLED_APPS` e `EVENTSTREAM_STORAGE_CLASS` em `config/settings.py`.
- `migrate` para criar tabelas.
- URL `storefront:stock_events` apontando pro view oficial.
- Smoke test: GET `/storefront/stock/events/?channel_ref=web` retorna 200 com `text/event-stream`.

### WP-SSE-02 — `_sse_emitters.py` + signals

- Criar `shopman/shop/handlers/_sse_emitters.py` com `_emit_for_sku` + `_channels_for_sku`.
- Conectar receivers para `Hold` post_save, `Move` post_save, `Product` pre/post_save, `ListingItem` pre/post_save.
- Testar via shell: `Hold.objects.create(...)` → log mostra emit; storage do `django-eventstream` tem o frame.
- Wire em `shopman/shop/handlers/__init__.py` no padrão existente.

### WP-SSE-03 — Cache invalidation no emit

- `_emit_for_sku` também faz `cache.delete('availability:<sku>:<channel>')`.
- Teste: setar valor no cache, disparar emit, verificar que cache foi limpo.

### WP-SSE-04 — Cliente HTMX em PDP + cards

- Adicionar `<script src="...sse.js">` em [base.html](../../shopman/shop/templates/storefront/base.html).
- Adicionar wrapper `hx-ext="sse" sse-connect=...` no body do storefront.
- Anotar `data-sku` + `sse-swap` em cada elemento de card/stepper.
- Confirmar via preview que mudanças propagam.

### WP-SSE-05 — Endpoint partial para refresh per-SKU

Hoje cada elemento precisa de um endpoint que devolve o card/stepper atualizado para um SKU. Ou criar um novo `/storefront/sku/<sku>/badge/` que devolve só o badge + stepper, ou reusar `/api/availability/<sku>/` (JSON) e atualizar Alpine localmente.

**Recomendação**: novo partial `storefront:sku_state` que devolve HTML com badge + price + stepper para um único SKU. Reusa o componente do card.

### WP-SSE-06 — Tests

- Unit: emit dispara nos signals certos.
- Integration: endpoint SSE devolve `text/event-stream`.
- E2E manual no preview, conforme §9.3.

---

## 11. Critério de saída

1. Mexer no estoque (criar Hold via shell) → cliente com PDP aberta vê badge/stepper atualizar em <2s, sem reload.
2. Pausar produto via admin → cliente vê badge "Indisponível" + CTA disabled em <2s.
3. Suítes verdes: framework, stockman, offerman.
4. Conexão SSE não pendura worker (verificar `htop` durante 5 abas abertas por 10min — workers mantêm livre).
5. Heartbeat SSE chegando a cada 30s no devtools network tab.

---

## 12. Perguntas abertas (Pablo)

1. **Qual storage do `django-eventstream` usar em produção?** Resolvido: Redis fanout via `EVENTSTREAM_REDIS`, com storage ORM mantido para persistência da lib.
2. **Operador via POS deve receber stock-update do canal `balcao` em tempo real?** Se sim, instrumentar templates do POS também (não cobrei aqui — escopo é storefront).
3. **`Move` post_save dispara MUITOS eventos** (cada baixa, cada produção). Para canais com volume alto, debounce? Hoje não — sigo simples.

---

## 13. Pre-flight para o agente cold-start

Antes de tocar código:

1. Ler [AVAILABILITY-PLAN.md](AVAILABILITY-PLAN.md) §6 ("Lifecycle — quando re-checar") e §3 (estado canônico).
2. Ler:
   - [shopman/shop/api/availability.py](../../shopman/shop/api/availability.py) — entender o cache atual de 10s.
   - [shopman/shop/handlers/__init__.py](../../shopman/shop/handlers/__init__.py) — entender pattern de wiring de signals.
   - [shopman/shop/handlers/_stock_receivers.py](../../shopman/shop/handlers/_stock_receivers.py) — pattern existente.
   - [base.html](../../shopman/shop/templates/storefront/base.html) — onde plugar o `<script>` e o `hx-ext="sse"`.
3. Conferir se `django-eventstream` é compatível com a versão de Django no `pyproject.toml`.
4. Responder Pablo §12.1 e §12.2 antes de prosseguir.

---

## 14. Memória ao concluir

Gravar:

- `project_sse_push_active.md` — "SSE push ativo via `django-eventstream` para mudanças de estoque/pause. Endpoint `/storefront/stock/events/?channel_ref=...`. Eventos: stock-update, product-paused, listing-changed."
- Atualizar `project_availability_plan_status.md`: WP-AV-10 deixa de "diferido" e vira "concluído".
