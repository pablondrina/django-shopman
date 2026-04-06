# DEBT-PLAN — Refatoração de Dívidas Técnicas

## Contexto

Análise crítica do codebase identificou 4 problemas concretos que afetam
confiabilidade, performance e observabilidade do sistema. Este plano resolve
cada um como work package independente, sem inventar features.

**Problemas:**
1. Stock fulfill silencia falhas → estoque inconsistente
2. N+1 queries no storefront → 120+ queries por page load
3. Checkout view duplica dados do CommitService → responsabilidade confusa
4. 23 `except Exception` silenciosos nas views → bugs invisíveis

**Ordem de execução recomendada:** D1 → D4 → D2 → D3 (risco decrescente).
Cada WP é independente — pode ser executado em qualquer ordem.

---

## WP-D1: Stock Fulfill — Retry em vez de Silenciar

**Status:** concluído

### Prompt

```
Execute o WP-D1 do DEBT-PLAN.md.

## Contexto

O sistema de Directives tem retry com backoff exponencial em
`shopman-core/omniman/shopman/ordering/dispatch.py`:
- Se um handler PROPAGA uma exceção, dispatch.py faz retry (até 5 tentativas,
  backoff 2^n segundos), depois seta status="failed" se esgotar.
- Se um handler CAPTURA a exceção e seta message.status = "failed" internamente,
  dispatch.py não retria — é estado terminal.

O problema: `StockCommitHandler` e `services/stock.py:fulfill()` capturam
exceções e não propagam, derrotando o mecanismo de retry.

Retry é seguro: `StockingBackend.fulfill_hold()` em
`shopman-app/shopman/backends/stock.py` já verifica
`hold.status == HoldStatus.FULFILLED → return` (idempotente).

## Alteração 1: shopman-app/shopman/handlers/stock.py

Na classe `StockCommitHandler.handle()`:

1. Remover a variável `errors: list[str] = []`

2. Remover o try/except que envolve `self.backend.fulfill_hold()` —
   a chamada deve ser feita diretamente, sem try/except

3. Remover o bloco `if errors:` que seta message.status = "failed"

4. Após o loop de holds, setar `message.status = "done"` e salvar.
   Se fulfill_hold falhar, a exceção propaga antes de chegar aqui.

5. Envolver o loop inteiro em try/except que:
   - Se `message.attempts >= 4` (será a 5a tentativa no dispatch),
     cria OperatorAlert tipo "stock_fulfill_failed" com severity="error"
   - Sempre re-raise a exceção (para dispatch.py fazer retry/fail)

6. Adicionar método `_create_fulfill_alert(self, order_ref, holds)` que cria
   OperatorAlert com:
   - type="stock_fulfill_failed"
   - severity="error"
   - message=f"Fulfillment falhou após 5 tentativas para pedido {order_ref}"
   - order_ref=order_ref

7. Manter `self._check_stock_alerts(fulfilled_skus)` DENTRO do try,
   APÓS `message.status = "done"` e `message.save()`.

## Alteração 2: shopman-app/shopman/services/stock.py

Na função `fulfill(order)`:

1. Remover a variável `errors = []`
2. Remover o try/except individual que envolve `StockService.fulfill(hold_id)`
3. Chamar `StockService.fulfill(hold_id)` diretamente
4. Remover o bloco `if errors:` que loga
5. Manter o log de sucesso: `logger.info(...)` no final

O caller desta função é `flows.py:on_paid()` via `dispatch()`.
O `dispatch()` em flows.py captura Exception e loga (catch de último recurso).
Isso é aceitável — o StockCommitHandler (via directive) é o caminho
primário com retry.

## Verificação
- `make test-shopman-app`
- Confirmar que nenhum teste depende do comportamento de acumular erros
```

---

## WP-D2: Checkout — Eliminar Duplicação com CommitService

**Status:** pendente → migrado para CORRECTIONS-PLAN WP-C8

### Prompt

```
Execute o WP-D2 do DEBT-PLAN.md.

## Contexto

O `CommitService._do_commit()` em
`shopman-core/omniman/shopman/ordering/services/commit.py`
copia keys específicas de `session.data` para `order.data` (linhas ~269-277):

    for key in (
        "customer", "fulfillment_type", "delivery_address",
        "delivery_date", "delivery_time_slot", "order_notes",
        "origin_channel",
    ):
        if key in session_data:
            order_data[key] = session_data[key]

O `CheckoutView.post()` em `shopman-app/shopman/web/views/checkout.py`
re-fetcha o Order DEPOIS do commit e reescreve os mesmos 5 campos.
Além disso, escreve 2 campos que o CommitService NÃO copia:
- `delivery_address_structured` (endereço estruturado)
- `payment` (com `{"method": chosen_method}`)

O `_build_ops_from_data()` em `shopman-app/shopman/services/checkout.py`
já inclui `payment` na lista de data_fields, mas NÃO inclui
`delivery_address_structured`.

## Alteração 1: shopman-core/omniman/shopman/ordering/services/commit.py

Na função `_do_commit()`, na tupla de keys copiadas de session_data
para order_data, adicionar `"delivery_address_structured"` e `"payment"`:

    for key in (
        "customer", "fulfillment_type", "delivery_address",
        "delivery_address_structured", "delivery_date",
        "delivery_time_slot", "order_notes",
        "origin_channel", "payment",
    ):

## Alteração 2: shopman-app/shopman/services/checkout.py

Na função `_build_ops_from_data()`, adicionar `"delivery_address_structured"`
à lista `data_fields`:

    data_fields = [
        "customer", "fulfillment_type", "delivery_address",
        "delivery_address_structured", "delivery_date",
        "delivery_time_slot", "order_notes", "payment",
    ]

## Alteração 3: shopman-app/shopman/web/views/checkout.py

No método `post()` da `CheckoutView`:

1. ANTES da chamada `checkout_process()`, adicionar ao dict `checkout_data`:
   - Se `addr_data.get("formatted_address")` é truthy, adicionar
     `checkout_data["delivery_address_structured"]` com o dict addr_data
     filtrado (somente values truthy)
   - Se `chosen_method in ("pix", "card")`, adicionar
     `checkout_data["payment"] = {"method": chosen_method}`

2. REMOVER o bloco post-commit que começa com o comentário
   `# ── Post-commit: enrich order data ──` e termina antes de
   `# ── Ensure customer exists ──`. É o trecho que faz
   `order = Order.objects.get(ref=order_ref)` e reescreve
   fulfillment_type, delivery_address, delivery_date, etc.
   Isso tudo já é feito pelo CommitService agora.

## Alteração 4: docs/reference/data-schemas.md

Adicionar `delivery_address_structured` à seção de Order.data.
Documentar que `payment` é propagado via CommitService (session.data → order.data).

## Verificação
- `make test-shopman-app`
- `make test-offering` e `make test-stocking` (core inalterado funcionalmente)
```

---

## WP-D3: Storefront N+1 — Batch Queries

**Status:** pendente → migrado para CORRECTIONS-PLAN WP-C5

### Prompt

```
Execute o WP-D3 do DEBT-PLAN.md.

## Contexto

`_annotate_products()` em `shopman-app/shopman/web/views/_helpers.py` recebe
uma lista de Product e, para cada um, chama:
- `_get_price_q(product)` → 1 query ListingItem por produto
- `_get_availability(product.sku)` → 3-5 queries por produto
  (Channel config ×2, Batch, Quant.exists, Quant.filter)

Para 30 produtos = ~150 queries por page load.

A função `_availability_for_sku()` em
`shopman-core/stockman/shopman/stocking/api/views.py` faz por SKU:
1. `_product_is_orderable(sku)` → 1 query Product
2. `Batch.objects.filter(sku=sku, expiry_date__lt=today)` → 1 query
3. `Quant.objects.filter(sku=sku, target_date__gt=today).exists()` → 1 query
4. `Quant.objects.filter(sku=sku).select_related("position")` → 1 query

Já existe `BulkAvailabilityView` que aceita múltiplos SKUs mas chama
`_availability_for_sku()` em loop — não resolve o N+1.

A função `availability_scope_for_channel()` no mesmo arquivo retorna
safety_margin e allowed_positions para um channel_ref. Faz 2 queries
(Channel ×2) mas é constante para todos os produtos do mesmo canal.

## Alteração 1: shopman-core/stockman/shopman/stocking/api/views.py

Adicionar nova função `_availability_for_skus()` LOGO APÓS
`_availability_for_sku()`. Mesma lógica, mas batch:

Assinatura:
    def _availability_for_skus(
        skus: list[str],
        safety_margin: int = 0,
        *,
        allowed_positions: list[str] | None = None,
    ) -> dict[str, dict]:

Implementação — 4 queries independente do N:
1. `Product.objects.filter(sku__in=skus, is_published=True, is_available=True)`
   → `orderable_skus: set[str]`
2. `Batch.objects.filter(sku__in=skus, expiry_date__lt=today)`
   → `expired_refs: dict[str, set[str]]` (por SKU)
3. `Quant.objects.filter(sku__in=skus, target_date__gt=today, _quantity__gt=0)`
   → `planned_skus: set[str]` (SKUs com quants futuros)
4. `Quant.objects.filter(sku__in=skus).filter(Q(target_date__isnull=True) | Q(target_date__lte=today)).filter(_quantity__gt=0).select_related("position")`
   → todos os quants, filtrados por allowed_positions se não None

Agrupar quants por SKU em Python. Para cada SKU, calcular breakdown
(ready, in_production, d1) e totais com a mesma lógica de
`_availability_for_sku()`. Para SKUs não orderáveis, retornar zeros
com is_paused=True.

Retornar `{sku: availability_dict}` para todos os SKUs pedidos.

Também atualizar `BulkAvailabilityView.get()` para usar
`_availability_for_skus()` em vez do loop com `_availability_for_sku()`.

## Alteração 2: shopman-app/shopman/web/views/_helpers.py

Refatorar `_annotate_products()`:

1. No início da função, coletar `skus = [p.sku for p in products]`

2. Batch de preços — substituir chamadas individuais a `_get_price_q()`:
   Fazer uma query:
       ListingItem.objects.filter(
           listing__ref=listing_ref,
           listing__is_active=True,
           product__sku__in=skus,
           is_published=True,
           is_available=True,
       ).select_related("product").order_by("-min_qty")
   Montar dict `price_map: dict[str, int]` com `setdefault` (primeiro
   match por SKU = maior min_qty, que é o comportamento atual do `.first()`
   com `order_by("-min_qty")`).

3. Batch de disponibilidade — substituir chamadas individuais a
   `_get_availability()`:
   - Buscar scope UMA vez: `availability_scope_for_channel(STOREFRONT_CHANNEL_REF)`
   - Se HAS_STOCKING: chamar `_availability_for_skus(skus, ...)`
   - Montar dict `avail_map: dict[str, dict | None]`

4. No loop de produtos, usar lookups:
       base_q = price_map.get(p.sku, p.base_price_q)
       avail = avail_map.get(p.sku)

5. Manter `_get_price_q()` e `_get_availability()` como funções públicas
   (são usadas individualmente em outros locais como `_line_item_is_d1()`
   e cart views). Não remover.

## Verificação
- `make test-shopman-app`
- `make test-stocking`
- `make lint`
```

---

## WP-D4: Views — Logging nos except Exception

**Status:** pendente → migrado para CORRECTIONS-PLAN WP-C1

### Prompt

```
Execute o WP-D4 do DEBT-PLAN.md.

## Contexto

23 blocos `except Exception` silenciosos nas views — falhas viram dados
faltando sem nenhum log. O padrão correto já existe em
`shopman-app/shopman/web/views/auth.py` (5 blocos, todos com
`logger.warning(...)`).

## Regras

- NÃO mudar o comportamento: cada bloco deve continuar retornando o mesmo
  fallback (None, [], set(), etc.)
- APENAS adicionar `logger.warning("descrição_curta", exc_info=True)` ou
  `logger.exception("descrição_curta")` em cada bloco
- Para blocos que fazem `pass`, substituir `pass` pelo logger call
- Para blocos que fazem `return X`, adicionar o logger call ANTES do return

## Alteração 1: shopman-app/shopman/web/views/_helpers.py

O arquivo NÃO tem logger no topo. Adicionar após os imports existentes:

    import logging
    logger = logging.getLogger(__name__)

9 blocos silenciosos a corrigir. Buscar cada `except Exception:` que faz
`return None`, `return set()`, `return []`, ou `pass` sem logging.
Adicionar `logger.warning("descrição", exc_info=True)` em cada um.
As descrições devem ser curtas e identificar a operação:
- "_get_channel_listing_ref failed"
- "_get_availability failed for sku=%s" (passando o sku se disponível)
- "_storefront_session_pricing_hints failed"
- "_d1_discount_percent failed"
- "_popular_skus failed"
- "_hero_data failed"
- "_min_order_progress failed"
- "_cross_sell_products failed"
- etc. (adaptar ao contexto de cada bloco)

## Alteração 2: shopman-app/shopman/web/views/account.py

O arquivo NÃO tem logger no topo do módulo (só dentro de uma função).
Adicionar após os imports:

    import logging
    logger = logging.getLogger(__name__)

7 blocos silenciosos. Buscar cada `except Exception:` que faz `pass` ou
`return (None, [])` sem logging. Adicionar logger.warning em cada um.
Remover o logger local criado dentro de AccountDeleteView.post() que
duplicaria.

## Alteração 3: shopman-app/shopman/web/views/catalog.py

O arquivo NÃO tem logger. Adicionar após os imports:

    import logging
    logger = logging.getLogger(__name__)

5 blocos silenciosos. Mesma lógica.

## Alteração 4: shopman-app/shopman/web/views/pos.py

O arquivo JÁ TEM logger no topo (`logger = logging.getLogger(__name__)`).

2 blocos silenciosos: buscar `except Exception:` que faz `return None` ou
similar sem logging. Adicionar logger.warning.

1 bloco perigoso que expõe exceção ao usuário: buscar
`f'Erro: {e}'` ou `f"Erro: {e}"` no HTML retornado ao usuário.
Substituir por mensagem estática:
    "Erro ao fechar pedido. Tente novamente."
O bloco já tem `logger.exception()`, então manter o log existente.

## Verificação
- `make test-shopman-app`
- `make lint`
```

---

## Ordem de Execução Recomendada

1. **WP-D1** (stock fulfill) — risco mais alto, fix mais simples
2. **WP-D4** (logging) — zero risco, ganho imediato de observabilidade
3. **WP-D2** (checkout duplication) — risco médio, requer cuidado com testes
4. **WP-D3** (N+1 queries) — maior escopo, mais código, mas sem risco funcional
