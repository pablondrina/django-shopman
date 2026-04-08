# CLEANUP2-PLAN — Fechamento de débitos pós WP-CLEAN1

> Plano de fechamento dos débitos identificados após o WP-CLEAN1 (que migrou
> stock para o pattern function-style adapter, criou `services/availability.py`
> como API canônica sync para checagem/reserva, e fixou `MarketplaceFlow` com
> rejeição pré-emptiva).
>
> Cada WP é auto-contido — o prompt de cada um é executável em uma sessão isolada
> do Claude Code. Prefixo `WP-CL2` (cleanup 2) para não colidir com `WP-CLEAN1`.
>
> **Status:** Aguardando aprovação
> **Criado:** 2026-04-08
> **Origem:** auditoria conversacional pós-CLEAN1, ver mensagem do usuário
> "algum débito? globalmente falando?"

---

## Sumário Executivo

WP-CLEAN1 deletou as infraestruturas mortas (`StockHoldHandler`, `StockCheck*`,
`handlers/payment.py`, `StockBackend` dataclass) e tornou `availability.check`/
`reserve` os pontos canônicos sync para "o cliente pode pedir isto?". Sobraram
8 débitos, ordenados por severidade:

| # | Débito | Severidade | Veredito WP-CL2-0 | WP |
|---|--------|------------|-------------------|----|
| D1 | `availability.check` não expande bundles → componente sem stock passa silenciosamente | **Crítica** | **confirmado** | WP-CL2-1 |
| D2 | `OperatorAlert.TYPE_CHOICES` desatualizado (vários tipos emitidos não registrados) | Média | **confirmado** (2 tipos órfãos) | WP-CL2-2 |
| D3 | `availability.check` ignora `ListingItem.min_qty` | Média | **confirmado** | WP-CL2-3 |
| D4 | POS path bypassa `availability.check` (assimetria com web/marketplace) | Baixa | **confirmado** | WP-CL2-4 |
| D5 | `ReorderView` engole `CartUnavailableError` silenciosamente (UX) | Baixa | **confirmado** | WP-CL2-5 |
| D6 | `backends/` ainda tem 8 arquivos não migrados para `adapters/` | Média | **confirmado** (8 arquivos) | WP-CL2-6, WP-CL2-7, WP-CL2-8 |
| D7 | WP-NAMESPACE pendente: pacotes em `shopman.stocking`/`ordering`/`offering`/`customers` em vez de stockman/omniman/offerman/guestman | Alta (estética + identidade) | **confirmado** (401 ocorrências) | WP-CL2-9, WP-CL2-10 |
| D8 | WP-AVAIL-LIVE: sem endpoint público de availability + sem polling HTMX em vitrine/PDP | Média (UX produção) | **confirmado** | WP-CL2-11, WP-CL2-12 |

**Não-débitos (verificados, NÃO entram no plano):**
- Pause global do Offerman → coberta via `_product_is_orderable` em `packages/stockman/.../availability.py:26`.
- `safety_margin` / `allowed_positions` por canal → cobertos via `availability_scope_for_channel`.
- Untracked SKUs → comportamento documentado e testado em `availability.py:79-88`.
- Race entre check e hold no marketplace → defense-in-depth com `held_skus vs ordered_skus` em `flows.py::MarketplaceFlow.on_commit`.

---

## Decisões de Design

### DD-1: Bundles em `availability.check`

`check(sku, qty, channel_ref=...)` deve, quando o SKU for um bundle:

1. Expandir via `CatalogService.expand(sku, qty)`.
2. Rodar a lógica completa de `check()` para cada componente (listing membership + Offerman pause + Stockman scope + qty).
3. Retornar `ok=False` no primeiro componente que falhar, com `error_code` indicando QUAL componente falhou (ex: `error_code: "insufficient_stock"`, `failed_sku: "FARINHA-001"`).
4. Se todos passarem, retornar `ok=True` com `available_qty` igual ao mínimo dos componentes (limitado pela quantidade de bundles construíveis).

**Por quê:** hoje um cliente pode adicionar bundle ao carrinho com `reserve()` retornando ok=True (porque o SKU do bundle não tem stock próprio em Stockman → cai no branch "untracked"), e só descobrirá o problema em `services.stock.hold(order)` no commit, que silenciosamente cria holds parciais e logga warning. Pedido fica inconsistente.

### DD-2: `OperatorAlert.TYPE_CHOICES` é a fonte da verdade

Toda chamada `_create_alert(order, type)` no código deve corresponder a um tipo registrado. WP-CL2-2 audita e adiciona os tipos faltantes. Tipos não usados ficam (não há custo).

### DD-3: `min_qty` é validação, não pricing

`ListingItem.min_qty` hoje só é usado pelo CatalogService para escolher o tier de preço. Mas semanticamente é "quantidade mínima vendável neste canal". `availability.check` deve rejeitar pedidos abaixo desse mínimo com `error_code: "below_min_qty"`.

### DD-4: POS usa `availability.check` antes de `stock.hold`

Hoje `services.stock.hold(order)` no path POS vai direto pro `adapter.create_hold` sem upstream check. WP-CL2-4 adiciona o check em `LocalFlow.on_commit` (antes de `stock.hold`), simétrico ao `MarketplaceFlow`. Em caso de falha, cria alerta + transição para CANCELLED (operador vê na fila e refaz o pedido).

### DD-5: Backends classes-based — migrar OU deletar, sem meio-termo

WP-CL2-6/7/8 atacam os 8 arquivos de `backends/`. Cada arquivo cai em uma de duas categorias:

- **Migrar para adapters/**: notification_console, notification_manychat, notification_email, notification_sms, pricing → viram módulos function-style igual aos adapters de payment/stock.
- **Deletar**: fiscal_mock, accounting_mock, checkout_defaults → ou não têm consumidor real ou são duplicatas de services/handlers existentes (verificar grep).

### DD-6: Persona names são definitivos

WP-CL2-9 e WP-CL2-10 fazem o rename físico:
- `shopman.stocking` → `shopman.stockman`
- `shopman.ordering` → `shopman.omniman`
- `shopman.offering` → `shopman.offerman`
- `shopman.customers` → `shopman.guestman`

`shopman.crafting`, `shopman.payments`, `shopman.identification` (doorman) — verificar nomes atuais e renomear para personas. WP-CL2-9 prepara o mapa completo + script idempotente; WP-CL2-10 executa.

### DD-7: Availability live é HTMX puro, não JavaScript imperativo

Endpoint `/api/availability/<sku>/?channel=web` retorna JSON minimal (`{ok, available_qty, badge_text, badge_class}`). Vitrine usa `hx-get` + `hx-trigger="every 30s"` no badge — sem store Alpine global, sem service worker, sem WebSocket.

---

## Pacotes de Trabalho

### WP-CL2-0 — Validação dos débitos & quebra final do escopo

**Objetivo:** Re-verificar cada um dos 8 débitos contra o código atual (alguns
podem ter sido resolvidos entre a auditoria e a execução), produzir o ADR
correspondente e congelar o escopo de cada WP. Zero código.

**Saídas:**
- `docs/decisions/adr-010-cleanup2-debts.md` — para cada D1..D8: vereditodo
  (`confirmado`, `parcialmente resolvido`, `já resolvido`), citações
  `arquivo:linha`, e WP responsável.
- Atualizar a tabela do sumário deste plano com os vereditos.
- Atualizar `MEMORY.md` com link para o novo ADR e este plano.

**Veto explícito:** Nenhum item pode ser classificado como "aceitável".
Cada débito é fechado por código ou removido do plano por já estar resolvido
(com grep provando).

**DoD:**
- ADR-010 commitado.
- Plano atualizado com vereditos.
- Aprovação explícita do usuário antes de iniciar WP-CL2-1.

---

### WP-CL2-1 — Bundle expansion em `availability.check` (CRÍTICO)

**Depende de:** WP-CL2-0 aprovado.
**Severidade:** Crítica (pode causar pedido inconsistente em produção).

**Objetivo:** Fechar D1. `availability.check` passa a expandir bundles e validar
cada componente.

**Prompt auto-contido:**

> Edite `framework/shopman/services/availability.py`:
>
> 1. No início de `check()`, antes do gate de listing, tente
>    `CatalogService.expand(sku, qty)`. Se retornar mais de um componente
>    (i.e., é bundle), itere chamando `check()` recursivamente para cada
>    componente com a qty calculada. Se qualquer componente falhar, retorne
>    `{ok: False, error_code: <do componente>, failed_sku: <sku do componente>,
>    available_qty: <do componente>, ...}`.
> 2. Se todos os componentes passarem, calcule `available_qty` como
>    `min(componente.available_qty / componente.qty_per_bundle for ...)` —
>    quantos bundles inteiros são construíveis. Retorne ok=True com esse
>    valor. Mantenha `is_bundle=True` no dict para o caller saber.
> 3. Cuidado com loop infinito: se `expand()` retornar uma lista de 1 elemento
>    com o mesmo SKU, é um produto simples, prossiga normalmente.
> 4. `reserve()` continua chamando `check()` no SKU original; o branch que
>    cria o hold (`adapter.create_hold(sku=sku, ...)`) precisa também ser
>    atualizado para criar UM hold por componente quando is_bundle=True
>    (cada um com `reference=session_key` para adoção posterior). Veja como
>    `services.stock.hold(order)` faz expand+iterate em
>    `framework/shopman/services/stock.py:54-91` — espelhar essa lógica.
>
> **Testes obrigatórios:**
> - `tests/test_services.py::TestAvailabilityBundles` (novo):
>   - bundle com todos componentes disponíveis → ok=True, available_qty correto.
>   - bundle com 1 componente sem stock → ok=False, failed_sku correto.
>   - bundle com 1 componente fora do listing do canal → ok=False,
>     error_code=not_in_listing.
>   - bundle com 1 componente pausado → ok=False, error_code=paused.
> - `tests/test_services.py::TestAvailabilityReserveBundles` (novo):
>   - reserve(bundle) com sucesso → cria N holds (um por componente), todos
>     com `reference=session_key`.
>   - reserve(bundle) com falha → nenhum hold criado, alternatives populadas.
> - Verificar que `cart.add_item(bundle_sku, qty)` no storefront passa pelo
>   path correto (rodar `tests/web/test_*` que envolvam bundle, se existir;
>   senão, criar fixture).
>
> **Não modificar:** `services/stock.py::hold(order)` continua como está
> (já expande bundles corretamente; agora só vai encontrar holds prontos
> para adopção em vez de criar fresh).
>
> **Pegadinha:** `CatalogService.expand` pode lançar exceção quando o SKU
> não é bundle. Use try/except como em `_expand_if_bundle` em
> `services/stock.py:178-183`.

**DoD:**
- Todos testes novos passam.
- `make test` verde (591+ no framework).
- Manualmente verificado: `python manage.py shell -c "from shopman.services.availability import check; print(check('<bundle-sku>', 1, channel_ref='web'))"` retorna `is_bundle=True`.

---

### WP-CL2-2 — `OperatorAlert.TYPE_CHOICES` sync

**Depende de:** WP-CL2-0.
**Severidade:** Média (admin filter, não enforcement).

**Objetivo:** Toda chamada `_create_alert(order, "<type>")` no código corresponde
a um item de `TYPE_CHOICES` em `framework/shopman/models/alerts.py`.

**Prompt auto-contido:**

> 1. Faça `grep -rn "_create_alert(" framework/shopman/` e
>    `grep -rn "OperatorAlert.objects.create" framework/shopman/`.
>    Liste todos os tipos emitidos.
> 2. Compare com `OperatorAlert.TYPE_CHOICES` em
>    `framework/shopman/models/alerts.py:11-17`.
> 3. Adicione os tipos faltantes em TYPE_CHOICES com label PT-BR claro.
>    Tipos confirmados emitidos atualmente (verificar grep para ter
>    certeza, podem ter mais):
>    - `marketplace_rejected_oos` → "Marketplace rejeitado: sem estoque"
>    - `marketplace_rejected_unavailable` → "Marketplace rejeitado: indisponível"
> 4. Crie migration: `python manage.py makemigrations shopman -n
>    sync_alert_types`. Verifique que a migration só altera o `choices`
>    (não muda DB schema — Django registra mas não migra column).
> 5. Atualize o admin em `framework/shopman/admin/alerts.py` se houver
>    list_filter por type — garantir que os novos tipos aparecem.
>
> **Não criar tipos novos especulativos.** Só os emitidos hoje.

**DoD:**
- Grep confirma 0 tipos órfãos.
- Migration criada e aplicada.
- `make test-framework` verde.

---

### WP-CL2-3 — `ListingItem.min_qty` validation em `availability.check`

**Depende de:** WP-CL2-1 (precisa do bundle expansion para min_qty fazer sentido em componentes).
**Severidade:** Média.

**Objetivo:** Fechar D3. `availability.check` rejeita qty abaixo de
`ListingItem.min_qty` do canal.

**Prompt auto-contido:**

> 1. Edite `framework/shopman/services/availability.py::_sku_in_channel_listing`:
>    em vez de retornar `bool`, retornar a `ListingItem` (ou None) — assim
>    `check()` tem acesso ao `min_qty`.
> 2. Em `check()`, depois do gate de listing, se `qty < listing_item.min_qty`,
>    retornar `{ok: False, error_code: "below_min_qty",
>    available_qty: listing_item.min_qty, ...}`.
> 3. `reserve()` propaga o `error_code` (já feito no WP-CLEAN1).
> 4. Storefront: `templates/storefront/partials/stock_error_modal.html`
>    deve ter um branch `{% elif error_code == "below_min_qty" %}` com
>    mensagem "Quantidade mínima: X unidades para este produto".
>
> **Testes:**
> - `TestAvailabilityListingMembership::test_rejects_below_min_qty` (DB-backed,
>   `tests/test_services.py`).
> - `TestCart::test_add_below_min_qty_returns_modal` em
>   `tests/web/test_web_cart.py` (se não existir, criar).

**DoD:**
- Testes novos verdes.
- `make test` verde.
- Verificado manualmente: cart_add com qty < min_qty mostra modal correto.

---

### WP-CL2-4 — POS path symmetry

**Depende de:** WP-CL2-1.
**Severidade:** Baixa (operador vê o estoque visualmente).

**Objetivo:** Fechar D4. `LocalFlow.on_commit` roda `availability.check` por
item antes de `stock.hold`, simétrico ao `MarketplaceFlow.on_commit`.

**Prompt auto-contido:**

> 1. Edite `framework/shopman/flows.py::LocalFlow.on_commit`. Antes de
>    `stock.hold(order)`, iterar `order.snapshot["items"]` e chamar
>    `availability.check(sku, qty, channel_ref=order.channel.ref)` para
>    cada um. Se algum falhar:
>    - log info com SKU + error_code.
>    - `_create_alert(order, "pos_rejected_unavailable")`.
>    - `order.transition_status(Order.Status.CANCELLED, actor="auto_reject_unavailable")`.
>    - return.
> 2. Adicione `pos_rejected_unavailable` em `OperatorAlert.TYPE_CHOICES`
>    (provavelmente já feito em WP-CL2-2 — confirmar).
> 3. Teste em `tests/test_flows.py::TestLocalFlow`:
>    - `test_on_commit_rejects_when_item_unavailable` (mock availability,
>      verifica alerta + status).
>    - `test_on_commit_proceeds_when_all_available` (caminho feliz, espelho
>      do que existe para MarketplaceFlow).
>
> **Cuidado:** o POS hoje confirma imediatamente após on_commit
> (`order.transition_status(CONFIRMED)`). Se rejeitarmos no on_commit,
> o transition para CANCELLED já fecha o pedido. Verificar que não há
> double-transition.

**DoD:**
- Testes verdes.
- `make test` verde.

---

### WP-CL2-5 — Reorder UX: feedback de items OOS

**Depende de:** WP-CL2-0.
**Severidade:** Baixa.

**Objetivo:** Fechar D5. `ReorderView` em
`framework/shopman/web/views/tracking.py` mostra ao cliente quais items foram
pulados por indisponibilidade.

**Prompt auto-contido:**

> 1. Edite `framework/shopman/web/views/tracking.py::ReorderView`. Hoje
>    captura `CartUnavailableError` e dá `pass` silencioso. Em vez disso,
>    coletar a lista de SKUs pulados e seus motivos.
> 2. Após o loop, se houver pulados, salvar a lista em
>    `request.session["reorder_skipped"]` e redirecionar para o cart com
>    `?reorder_skipped=1`.
> 3. `templates/storefront/cart.html` (ou template equivalente) renderiza
>    um banner Alpine `x-show` no topo: "X item(s) do pedido anterior
>    indisponíveis foram pulados: [lista de nomes]". Banner é dispensável
>    com `@click="show=false"`. Limpar a session key após renderizar (no
>    view do cart).
> 4. Teste em `tests/web/test_web_tracking.py`:
>    - `test_reorder_skips_oos_items_with_banner` — usar fixture com 2
>      items, 1 com stock zero. Verificar que cart tem 1 item e session
>      tem `reorder_skipped`.
>
> **Nada de toast/JS imperativo.** Banner Alpine + HTMX no padrão do projeto.

**DoD:**
- Teste novo verde.
- `make test` verde.

---

### WP-CL2-6 — Migrar notification backends → adapters

**Depende de:** WP-CL2-0.
**Severidade:** Média (refactor sem comportamento novo).

**Objetivo:** Mover `framework/shopman/backends/notification_console.py`,
`notification_manychat.py`, `notification_email.py`, `notification_sms.py`
para `framework/shopman/adapters/`, convertendo de class-based para
function-style (igual `adapters/payment_efi.py`).

**Prompt auto-contido:**

> 1. Inspecione `framework/shopman/protocols.py::NotificationBackend` (linhas
>    117-127). É um Protocol com método `send(*, event, recipient, context) ->
>    NotificationResult`.
> 2. Para cada um dos 4 arquivos em `backends/notification_*.py`:
>    - Criar `adapters/notification_<provider>.py` com função módulo-level
>      `send(*, event, recipient, context) -> NotificationResult`.
>    - Manter exatamente o comportamento atual (não tocar lógica).
>    - Atualizar `services/notification.py` (ou o handler que chama o
>      backend) para usar `get_adapter("notification", method=<provider>)`
>      em vez de instanciar a classe.
> 3. Atualizar `setup.py::register_all` removendo o registro do backend
>    class-based.
> 4. Atualizar `settings.py::SHOPMAN_NOTIFICATION_ADAPTERS` para apontar
>    para os novos módulos.
> 5. Deletar os arquivos antigos em `backends/`.
> 6. Atualizar `framework/shopman/protocols.py`: `NotificationBackend`
>    Protocol pode ser deletado (assim como foi com StockBackend) se
>    nada mais o referencia. Verificar com grep.
>
> **Testes:** `tests/test_handlers.py::TestNotificationHandler` deve continuar
> passando sem mudanças (ele testa o handler, não o backend).

**DoD:**
- 4 arquivos migrados, antigos deletados.
- `make test` verde.
- `ls framework/shopman/backends/notification_*` retorna nada.

---

### WP-CL2-7 — Migrar pricing & checkout_defaults backends

**Depende de:** WP-CL2-6 (estabelecer o pattern).
**Severidade:** Média.

**Objetivo:** Mover `backends/pricing.py` e `backends/checkout_defaults.py`
para o local apropriado.

**Prompt auto-contido:**

> 1. `pricing.py`:
>    - Inspecionar `protocols.py::PricingBackend` (linhas 134-142).
>    - Verificar quem chama: `grep -rn "PricingBackend\|backends.pricing"
>      framework/`. Provavelmente `services/pricing.py`.
>    - Se for um único caller (services/pricing.py), inline a lógica no
>      service e delete o backend. Pricing já é um service — não precisa
>      de adapter intermediário.
>    - Deletar `protocols.py::PricingBackend` se ninguém mais referencia.
> 2. `checkout_defaults.py`:
>    - Verificar quem chama: `grep -rn "checkout_defaults" framework/`.
>    - Provavelmente o handler `CheckoutInferDefaultsHandler` em
>      `handlers/checkout_defaults.py`.
>    - Inline no handler ou no `services/checkout_defaults.py`. Deletar
>      o backend.
>
> **Princípio:** se o backend tem 1 implementação real e nenhum plano de
> ter alternativas swappable, é over-engineering — inline e delete.

**DoD:**
- 2 arquivos deletados.
- Protocols correspondentes deletados se órfãos.
- `make test` verde.

---

### WP-CL2-8 — Deletar mocks: fiscal_mock & accounting_mock

**Depende de:** WP-CL2-0.
**Severidade:** Baixa.

**Objetivo:** Decidir destino de `backends/fiscal_mock.py` e
`backends/accounting_mock.py`.

**Prompt auto-contido:**

> 1. `grep -rn "fiscal_mock\|FiscalMock\|accounting_mock\|AccountingMock"
>    framework/`.
> 2. Se forem usados apenas em testes ou settings de dev:
>    - Mover para `framework/shopman/tests/_mocks/` ou similar (fora de
>      backends/).
>    - Atualizar imports.
> 3. Se forem usados em produção como fallback (improvável):
>    - Migrar para `adapters/fiscal_mock.py` / `adapters/accounting_mock.py`
>      no padrão function-style.
> 4. Atualizar `settings.py` se aponta para o caminho antigo.
> 5. Atualizar `protocols.py` deletando `FiscalBackend`/`AccountingBackend`
>    se órfãos (provavelmente vivem em `shopman.ordering.protocols`,
>    re-exportados — verificar).
>
> **Critério:** ao final, `framework/shopman/backends/` está vazio
> (ou só tem `__init__.py` vazio para deletar em seguida).

**DoD:**
- `framework/shopman/backends/` vazio.
- `rmdir framework/shopman/backends/` executável.
- `make test` verde.

---

### WP-CL2-9 — WP-NAMESPACE-A: prep do rename

**Depende de:** WP-CL2-0.
**Severidade:** Alta (identidade do projeto).

**Objetivo:** Mapear todos os pontos de touch e gerar script idempotente
de rename. Zero código de produção alterado neste WP — só documentação +
script reversível.

**Prompt auto-contido:**

> 1. Mapa de renames (verificar nomes atuais reais com `ls packages/`):
>    - `shopman.stocking` → `shopman.stockman`
>    - `shopman.ordering` → `shopman.omniman`
>    - `shopman.offering` → `shopman.offerman`
>    - `shopman.customers` → `shopman.guestman`
>    - `shopman.crafting` → `shopman.craftsman` (verificar nome atual)
>    - `shopman.payments` → `shopman.payman` (verificar nome atual)
>    - `shopman.identification` → `shopman.doorman` (verificar nome atual)
> 2. Para cada package, contar `grep -rn "from shopman\.<old>"` em
>    `packages/`, `framework/`, `instances/`.
> 3. Verificar `app_label` em cada `apps.py` — provavelmente precisa
>    renomear também (e migrations vão precisar de
>    `Migration.replaces`).
> 4. Verificar `INSTALLED_APPS` em todos os settings.
> 5. Verificar nomes de tabelas (`db_table` em Meta) — se hardcoded,
>    listar.
> 6. Gerar `docs/plans/CLEANUP2-RENAME-MAP.md` com:
>    - Tabela completa old → new para cada package.
>    - Inventário de touch points (arquivos + linhas).
>    - Script bash idempotente para fazer o rename físico (mv) e o
>      sed nos imports.
>    - Plano de migration: como o Django vai lidar com app_label
>      mudando (Migration.replaces ou squash + new initial).
>
> **Não executar nada.** Só inventário + script no formato dry-run.

**DoD:**
- `CLEANUP2-RENAME-MAP.md` commitado.
- Aprovação do usuário antes de WP-CL2-10.

---

### WP-CL2-10 — WP-NAMESPACE-B: executar rename

**Depende de:** WP-CL2-9 aprovado.
**Severidade:** Alta.

**Objetivo:** Executar o rename físico em uma sessão isolada, validando com
`make test` ao final.

**Prompt auto-contido:**

> 1. Ler `docs/plans/CLEANUP2-RENAME-MAP.md`.
> 2. Executar o script em um worktree isolado (use `isolation: worktree`
>    no Agent tool ou crie branch dedicado).
> 3. Após cada package renomeado, rodar `make test-<package>`. Se quebrar,
>    parar e diagnosticar.
> 4. Quando todos os packages estiverem renomeados, rodar `make test`
>    completo.
> 5. Atualizar `CLAUDE.md` (estrutura do projeto) com os novos nomes.
> 6. Atualizar `docs/guides/flows.md` e qualquer outra doc que use os
>    nomes antigos.
> 7. Atualizar `MEMORY.md` removendo as entries que viraram obsoletas
>    (ex: `feedback_persona_names_only` ainda é válida, mas outras
>    podem ter ficado).
> 8. **Migrations:** seguir o plano definido no WP-CL2-9. Provavelmente
>    `Migration.replaces` apontando para os módulos antigos.
>
> **NÃO mudar lógica nenhuma neste WP.** Só rename mecânico.

**DoD:**
- `make test` verde.
- `grep -rn "shopman\.stocking\|shopman\.ordering\|shopman\.offering\|shopman\.customers" packages/ framework/ instances/`
  retorna 0 ocorrências.
- CLAUDE.md atualizado.

---

### WP-CL2-11 — WP-AVAIL-LIVE-A: API de availability

**Depende de:** WP-CL2-1 (bundle support).
**Severidade:** Média.

**Objetivo:** Endpoint público minimal para o frontend consultar
disponibilidade live de um SKU em um canal.

**Prompt auto-contido:**

> 1. Criar `framework/shopman/api/views/availability.py`:
>    - View `AvailabilityView` (DRF APIView, não ViewSet).
>    - GET `/api/availability/<sku>/?channel=<ref>`.
>    - Response: `{ok, available_qty, badge_text, badge_class, is_bundle}`.
>    - `badge_text` / `badge_class` são derivados em PT-BR ("Disponível",
>      "Esgotado", "Indisponível", "Quantidade mínima X") seguindo as
>      regras já definidas em `AVAILABILITY-PLAN.md::DD-1`.
>    - Sem autenticação (público read-only).
>    - Rate limit: 60 req/min por IP (usar django-ratelimit ou middleware
>      existente — verificar).
> 2. Adicionar URL em `framework/shopman/api/urls.py`.
> 3. Cache: cachear por 10 segundos no Django cache (chave
>    `availability:<sku>:<channel>`). Invalidar via signal de Hold/Quant
>    (verificar se já existe sinal de stock_changed; se não, deferir
>    invalidação para o TTL).
> 4. Testes em `tests/api/test_availability.py`:
>    - 200 com SKU disponível.
>    - 200 com SKU esgotado (ok=False, badge_text="Esgotado").
>    - 200 com SKU não-listado (ok=False, badge_text="Indisponível").
>    - 200 com bundle (is_bundle=True).
>    - 404 com SKU inexistente.
>    - Cache hit não chama `availability.check` 2x.

**DoD:**
- Endpoint funcional, testes verdes.
- `curl localhost:8000/api/availability/<sku>/?channel=web` retorna JSON
  bem formado.

---

### WP-CL2-12 — WP-AVAIL-LIVE-B: HTMX polling no storefront

**Depende de:** WP-CL2-11.
**Severidade:** Média.

**Objetivo:** Vitrine, PDP e listagens consomem o endpoint via HTMX para
manter badges sempre frescos.

**Prompt auto-contido:**

> 1. Criar partial `templates/storefront/partials/availability_badge.html`:
>    - Renderiza badge com `hx-get="{% url 'api:availability' sku %}"
>      hx-trigger="every 30s" hx-swap="outerHTML"
>      hx-target="this"`.
>    - Inicial vem do SSR (chamar `availability.check()` no view e passar
>      o dict como context).
> 2. Substituir os badges atuais em:
>    - `templates/storefront/catalog.html` (cards de produto).
>    - `templates/storefront/product_detail.html` (PDP).
>    - `templates/storefront/partials/cart_item.html` (linha do cart —
>      mostrar "Esgotado" se item ficou indisponível enquanto está no
>      cart).
> 3. Para o cart, usar HTMX trigger `availability:changed` no body
>    quando badge atualiza para `is_paused/insufficient_stock`. Outro
>    HTMX listener re-renderiza o resumo do cart (recalcula total).
> 4. Testes:
>    - `tests/web/test_storefront_availability_badge.py`:
>      - SSR renderiza badge inicial correto.
>      - URL do partial está presente nos atributos hx-*.
> 5. **Não usar Alpine `$store` global para availability.** Cada badge é
>    auto-suficiente via HTMX. Único Alpine envolvido é estado de
>    abertura/fechamento de modais.

**DoD:**
- Vitrine atualiza badges sem reload (verificar manualmente).
- Testes verdes.
- `make test` verde.

---

## Ordem de Execução Recomendada

```
WP-CL2-0  [Validação + ADR-010]                       — gate inicial
   │
   ├── WP-CL2-1  [Bundle expansion — CRÍTICO]         — bloqueia 3, 4, 11
   │      │
   │      ├── WP-CL2-3  [min_qty]
   │      ├── WP-CL2-4  [POS symmetry]
   │      └── WP-CL2-11 [API availability]
   │             │
   │             └── WP-CL2-12 [HTMX badges]
   │
   ├── WP-CL2-2  [Alert types sync]                   — independente
   ├── WP-CL2-5  [Reorder UX]                         — independente
   │
   ├── WP-CL2-6  [Migrar notification backends]       — pattern setup
   │      │
   │      ├── WP-CL2-7  [Migrar pricing/checkout]
   │      └── WP-CL2-8  [Mocks: mover ou deletar]
   │             │
   │             └── (backends/ vazio)
   │
   └── WP-CL2-9  [Rename map + dry-run]               — independente
          │
          └── WP-CL2-10 [Executar rename]             — exige aprovação
```

**Prioridade real para a próxima sessão:** começar por **WP-CL2-0** (gate)
e logo em seguida **WP-CL2-1** (único débito que pode causar pedido
inconsistente em produção).

---

## Princípios Aplicáveis

- **Cada WP é mergeable isoladamente** — nada de WPs que dependem de outros
  WPs do mesmo plano além das dependências declaradas.
- **Zero gambiarras** — soluções corretas, sem workarounds (`feedback_zero_gambiarras`).
- **Zero residuals em renames** — quando WP-CL2-10 rodar, não pode ficar
  nenhum `# formerly shopman.stocking` (`feedback_zero_residuals`).
- **Core é Sagrado** — se um WP precisa mexer em `packages/`, parar e validar
  com o usuário antes (CLAUDE.md, seção "Core é Sagrado").
- **Testes acompanham** — WP sem teste é WP incompleto (`feedback_engineer_mindset`).
- **Cada WP atualiza o memory** se descobrir algo durável.

---

## Não-objetivos (explícitos)

Estes itens NÃO entram neste plano e ficam para futuras iterações:

- Refatorar `services/checkout.py` (não há débito identificado).
- Adicionar novos canais/flows (escopo = consolidação, não expansão).
- Mexer em `packages/` além do necessário para o rename.
- Substituir Alpine.js / HTMX / Tailwind por outro stack.
- Adicionar libs externas de componentes (`feedback_no_external_component_lib`).
- Implementar features de loyalty/dashboard/notification adicionais — esses
  têm planos próprios em `EVOLUTION-PLAN.md` (arquivado).

---

## Apêndice: glossário rápido

- **Untracked SKU**: SKU que existe no Offerman mas não tem nenhum `Quant`
  no Stockman (drop-shipped, fixture de teste, gestão externa). `availability.check`
  retorna `ok=True` com flag `untracked: True` e bypassa hold creation. Ver
  `services/availability.py:79-88`.
- **OOS**: out of stock. Item cuja `available_qty` foi a zero.
- **Adopção de hold**: holds criados por `availability.reserve()` no cart-add
  ficam tagged com `metadata.reference = session_key`. Ao commit do pedido,
  `services.stock.hold(order)` localiza esses holds via `_load_session_holds`
  e re-tagga para `order:<ref>` em vez de criar novos. Fluxo completo em
  `services/stock.py:31-101`.
- **Listing membership**: produto está publicado+disponível no `Listing`
  vinculado ao canal (via `Channel.listing_ref`). Gate adicionado ao
  `availability.check` no WP-CLEAN1 (após a auditoria conversacional).
