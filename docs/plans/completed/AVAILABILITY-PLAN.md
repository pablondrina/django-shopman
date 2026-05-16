# AVAILABILITY-PLAN

**Status:** concluído e validado em 2026-05-05. Todos os WPs WP-AV-01..14 têm implementação e cobertura rastreável; WP-AV-08, WP-AV-09 e WP-AV-12 receberam correções adicionais de robustez na mesma data. Sucessor operativo do [STOCK-UX-PLAN.md](../STOCK-UX-PLAN.md) para o sistema de verificação de disponibilidade e sugestão de substituição no storefront.

**Escopo:** unificar vocabulário, regras de derivação, fluxos canônicos (Ajuste × Substituição), stepper clamp, modal de erro de estoque, fermata (hold indefinido + materialização com notificação ativa), timeouts transparentes, correções dos 7 gaps mapeados, e rename global `alternatives → substitutes`.

**Fora de escopo (futuro, anotado em memória):** "Me avise quando chegar" como feature de subscrição avulsa. "Veja também" na PDP como descoberta lateral por keywords. Cross-sell ("vai bem com").

---

## 1. Princípio invariável

> Uma única fonte de verdade por SKU × canal × sessão. Toda superfície do storefront que responde "posso pedir isto, e quanto?" devolve a mesma resposta no mesmo instante. Divergência entre PDP, menu, card, carrinho, drawer, modal ou API = bug.

---

## 2. Vocabulário canônico

Quatro estados únicos. Nenhum sinônimo solto. Nenhuma variante criativa.

| Estado | Copy canônico | Semântica |
|---|---|---|
| **Disponível** | _(sem badge — default)_ | Pode pedir agora, até `max_orderable`. |
| **Últimas unidades** | Badge amarelo `Últimas unidades` | Disponível, mas `max_orderable ≤ low_stock_threshold` do canal. |
| **Lista de espera** | Badge + CTA "Me avise quando chegar" (futuro) ou "Entrar na lista" | Sem ready stock agora, mas produto aceita pré-venda: `availability_policy ∈ {demand_ok, planned_ok}`. |
| **Indisponível** | Badge cinza `Indisponível` | Esgotado, pausado, ou fora do canal. Um único texto. |

**Proibidos** (residuais a eliminar): "Acabou no momento", "Pausado no momento", "Não disponível aqui", "Temos só N agora", "Restam apenas N".

**Copy por contexto**:
- Modal com shortage parcial: `Apenas N unidades disponíveis`.
- Inline na linha do cart: `Apenas N unidades disponíveis` + CTA "Aceitar N" / "Remover".
- Toast após ação: `Adicionamos [Nome] ao carrinho`.
- Stepper em max: `máx. N`.

**Estados da linha do cart com planned hold** (reservados contra produção planejada / demand-only; ver §8):

| Estado da linha | Copy canônico | CTA |
|---|---|---|
| **Aguardando confirmação** (planned hold pré-materialização) | Badge info `Aguardando confirmação` + secondary `Avisamos quando chegar.` | Stepper só decrementa / remove (aumentar bloqueado). |
| **Tudo pronto** (planned hold pós-materialização) | Badge success `Tudo pronto! Confirme até HH:MM` + `Tempo restante: Xm YYs` (countdown Alpine ao vivo) | CTA de checkout troca para `Confirmar agora — tudo pronto` (ícone `priority_high`, sem animação). |

**Proibidos nesta família**: nenhuma variante informal — nada de `Tá vindo!`, `Já já sai!`, `Quase pronto!`, `Saiu do forno!`, `Chegou!`. O vocabulário é exatamente o acima.

---

## 3. Derivação do estado (pipeline short-circuit)

Ordem fixa, primeiro `false` define o estado. Aplicada em toda superfície:

1. `Product.is_published == False` → **404** (produto não existe para o público).
2. `ListingItem` ausente, `not is_published`, ou `not is_sellable` no canal → **404** (Gap F — ver seção 13).
3. `Product.is_sellable == False` → **Indisponível** (pausado globalmente).
4. `availability_policy == "demand_ok"` → **Lista de espera** (sem ceiling de qty).
5. `max_orderable ≥ 1` → **Disponível** (ou **Últimas unidades** se `max_orderable ≤ low_stock_threshold`).
6. `availability_policy == "planned_ok" && planned > 0` → **Lista de espera**.
7. Caso contrário → **Indisponível**.

Onde:
```
max_orderable = max(0, ready_physical − (held_ready − own_hold) − safety_margin)
```

- `own_hold = 0` quando não há sessão (anônimo, PDP inicial) → degenera para o que qualquer outro cliente veria.
- Para sessão com carrinho, `own_hold` vem de `_own_holds_for_session(session_key, [sku])`.

---

## 4. Fluxos canônicos do sistema

Duas ações de primeira classe. Nomeadas, distintas no retorno.

### 4.1 Ajuste

**Gatilho:** mesmo SKU, cliente aceita quantidade disponível menor que a pedida.  
**Exemplo:** pediu 10, tem 3 → CTA "Adicionar 3 disponíveis".  
**Efeito:** cria/atualiza hold para 3.  
**Retorno:** fica na superfície de origem + toast + stepper daquele SKU reflete a nova qty.

### 4.2 Substituição

**Gatilho:** cliente escolhe um SKU diferente da lista de substitutos do modal.  
**Efeito:** hold do SKU original permanece zero (ou no valor que já havia); hold do substituto é criado.  
**Retorno:** **redirect para `/cart/`** + toast `Adicionamos [Nome] ao carrinho`.

**Por que redirect em Substituição?** Semanticamente o cliente deixou a jornada do produto original. Mantê-lo na PDP do original gera dissonância ("esta página fala de X, mas tem Y no meu carrinho"). O cart é o lugar onde a ação se torna visível.

---

## 5. Comportamento por superfície

| Surface | Badge/estado | CTA | Aciona modal? | Substitutos? |
|---|---|---|---|---|
| **Home** | — | — | não | não |
| **Menu (card)** | Badge do estado | Stepper com clamp em `max_orderable` | via stepper overflow | não |
| **PDP disponível** | Preço + stepper | CTA "Adicionar" | via stepper overflow ou submit | não |
| **PDP indisponível** | Badge grande + CTA "Me avise quando chegar" (placeholder hoje) | — | não (nada a adicionar) | não (substitutos são só no modal) |
| **Cart drawer** | Linha por item + badge | `−`/`+` com clamp | via stepper overflow | não |
| **Cart page** | Idem drawer + banner global se `has_unavailable_items` | "Aceitar N" / "Remover" (inline por linha) | via stepper overflow ou aceitar | não |
| **Stock-error modal** | Título + mensagem + primary + substitutos | "Adicionar N disponíveis" + botões 1-clique de substitutos | — (é o modal) | **sim, até 3** |
| **Search** (futuro) | — | — | — | — |
| **Checkout** | Guard pré-commit; bloqueia se algum item Indisponível | Redirect ao cart com explicação | não | não |
| **API `/availability/<sku>/`** | JSON com estado + `max_orderable` + badge | — | — | — |

---

## 6. Modal de erro de estoque — uniforme no acionamento

**Regra de ouro:** o modal é **o mesmo componente, com o mesmo comportamento de acionamento**, disparado de qualquer superfície (PDP, menu, drawer, cart, API). O que diverge é só o **retorno após ação**, conforme seção 4.

**Contrato HTTP (já implementado):** `422 + HX-Retarget: #stock-error-modal + HX-Reswap: innerHTML + X-Shopman-Error-UI: 1`. A resposta traz HTML com `picker_origin` embutido no Alpine component.

**`pickAction(sku, qty, name, isAlternative)`** — 4 parâmetros. `isAlternative=true` + `origin=pdp` aciona `window.location.href = '/cart/'`. Caso contrário fecha o modal.

**Sempre dispara toast** no sucesso: `Adicionamos [Nome] ao carrinho`. Toast tem CTA "Ver carrinho" pra quem quiser checar, mas não força redirect em Ajuste.

---

## 7. Stepper clamp transparente

Três camadas, sempre aplicadas. Nenhum alert() nativo, nenhum modal para mero clamp.

1. **Inline `máx. N`** aparece sob o stepper quando `current_qty ≥ max_orderable − 2`. Discreto, sempre visível, sem surpresa.
2. **Botão `+` desabilitado** ao atingir `max_orderable`. `aria-label="Estoque máximo atingido"`.
3. **Overshoot por digitação direta** (input editável) ou race condition (estoque caiu entre render e click): toast `Apenas N unidades disponíveis` + clamp do valor submetido pro máximo.

Aplicável a **todas** as superfícies com stepper: cards do menu, PDP, cart drawer, cart page, POS.

Modal **só** para erro real de submit que requer decisão (aceitar N / escolher substituto / remover).

---

## 8. Fermata — hold indefinido + materialização + notificação ativa

"Fermata" é metáfora, não termo canônico. No código chamamos **hold de demanda / indefinido**.

### 8.1 Criação

Quando cliente adiciona produto em estado **Lista de espera** (`demand_ok` ou `planned_ok` sem ready):
- Adapter detecta a condição (`ready_physical == 0 && (policy == demand_ok || planned > 0)`).
- Cria Hold com `expires_at = None` (indefinido). O modelo [Hold.active()](../../../packages/stockman/shopman/stockman/models/hold.py) já trata `NULL` como ativo.
- Cart marca linha com flag `is_awaiting_confirmation = True`.
- UI mostra `Aguardando confirmação` + `Avisamos quando chegar.` na linha do cart.
- CTA é habilitado mas sem urgência. Checkout pode ou não ser bloqueado (decisão da seção 5).

### 8.2 Materialização

Quando produção realiza (Stockman `planning.realize()`):
- Holds planejados transitam para ready; holds indefinidos recebem `expires_at = now + materialized_ttl_minutes`.
- `materialized_ttl_minutes` passa a ser **configurável por canal** via `ChannelConfig.stock` (hoje hardcoded em 60min no Stockman). Default razoável: 60–120min.
- Sinal `holds_materialized` dispara (já existe).

### 8.3 Notificação ativa (Shopman, não Stockman)

Receiver `on_holds_materialized` em [shopman/shop/handlers/_stock_receivers.py](../../../shopman/shop/handlers/_stock_receivers.py) é estendido:

1. Resolve Session pelos `hold.metadata.reference` (já faz).
2. Resolve Customer pela Session.
3. Resolve canal preferido via consentimentos ativos de notificação (Guestman).
4. Chama `notify(event="stock.arrived", recipient=<canal resolvido>, context={sku, product_name, deadline_at, cart_url}, backend=<consentimento ativo ou default>)`.
5. Continua com o auto-commit já implementado ([ADR-007](../../_archive/decisions/adr-007-crafting-ordering-integration.md)).

A notificação viaja por WhatsApp (ManyChat), SMS, email, ou canal de origem da sessão — conforme preferência. Nunca apenas toast no storefront.

### 8.4 Janela de confirmação

- Cliente recebe aviso no canal certo com `deadline_at`.
- UI do cart exibe countdown ("Você tem até HH:MM para confirmar").
- Se confirma dentro do prazo: fluxo normal de checkout.
- Se não confirma: TTL estoura, hold libera, cliente recebe aviso final amigável ("infelizmente o prazo expirou, o item volta ao estoque").

---

## 9. Timeouts transparentes — princípio permanente

Registrado em memória persistente ([feedback_transparent_timeouts.md](../../../.claude/memory/feedback_transparent_timeouts.md)).

Todo TTL/timeout que afeta o cliente é considerado **implementado** quando:

1. UI mostra o prazo explicitamente (countdown, timestamp, ou copy clara).
2. Notificação ativa é disparada no início do countdown, pelo canal certo.
3. Opcional: lembrete antes do estouro.
4. Mensagem final amigável na expiração.

Aplicável a: hold de demanda materializado, pagamento Pix aguardando, pagamento em análise, janela de retirada, reservas de produção.

Se um destes rodar sem aviso ativo, **é bug de produto**, não polish.

---

## 10. Códigos de erro — vocabulário unificado

Após esta spec, apenas estes códigos são emitidos/consumidos:

| Código | Significado | Copy |
|---|---|---|
| `paused` | Pausado (product OU listing) | "Indisponível" |
| `not_in_listing` | Fora deste canal | **404** (não chega ao cliente como erro visível) |
| `insufficient_stock` | `max_orderable < requested` | "Apenas N unidades disponíveis" |
| `hold_failed` | Falha técnica em criar hold | Genérico "Tente novamente" |

**Removidos**: `below_min_qty` (min_qty não é operacionalmente usado — ver WP-AV-05).

---

## 11. O que NÃO é parte desta spec

| Feature | Por quê não agora | Registro |
|---|---|---|
| "Me avise quando chegar" (subscrição avulsa) | Feature independente; cliente sem hold. | [project_notify_me_pending.md](../../../.claude/memory/project_notify_me_pending.md) |
| "Veja também" na PDP | Descoberta lateral por keywords. Reutiliza scorer existente. | [project_pdp_veja_tambem_pending.md](../../../.claude/memory/project_pdp_veja_tambem_pending.md) |
| Cross-sell ("vai bem com") | Outro sistema, outro dia. | — |

---

## 12. Arquitetura de sinalização

**Stockman não é modificado.** Já faz o papel dele: emite `holds_materialized` como fato puro em [planning.py](../../../packages/stockman/shopman/stockman/services/planning.py).

**Shopman orquestra.** O receiver `on_holds_materialized` em [handlers/_stock_receivers.py](../../../shopman/shop/handlers/_stock_receivers.py) é o único ponto que precisa ser estendido. Usa o registry de `notifications.py` existente.

**Zero sinal novo. Zero tópico de notificação novo na infraestrutura** — `stock.arrived` é apenas a chave semântica passada para o `notify()` registry; as backends (ManyChat/SMS/email) já existem.

---

## 13. Work Packages (execução)

Ordem respeitando dependências. Um por vez, com testes + verificação em preview antes de fechar.

### WP-AV-01 — Rename global `alternatives` → `substitutes`

**Status 2026-05-05:** implementado e validado. O código ativo usa `substitutes` (`shopman/shop/services/substitutes.py`, `CartUnavailableError.substitutes`, templates/modal e testes). A varredura final não encontra `find_alternatives` nem `alternatives` no código ativo.

**Escopo:** puro refactor mecânico, zero mudança de comportamento.

- `packages/offerman/shopman/offerman/contrib/suggestions/` → `substitutes/`
- `find_alternatives` → `find_substitutes` (todas camadas)
- `shopman/shop/services/alternatives.py` → `substitutes.py`
- `CartUnavailableError.alternatives` → `CartUnavailableError.substitutes`
- Chaves de context em templates, keys de projeção, nomes de variáveis em testes
- Módulo `shopman.offerman.__init__.py` + `contrib.__init__.py`

**Testes:** todos devem continuar passando sem ajuste de lógica (só renomes). Atualizar apenas asserts que batem em nome.

**Dependências:** nenhuma.

---

### WP-AV-02 — Vocabulário unificado

**Status 2026-05-05:** implementado e validado. API, badges, modal, cart drawer/page e projeções usam os estados canônicos: `Disponível`, `Últimas unidades`, `Lista de espera`/planned e `Indisponível`; linhas planejadas usam `Aguardando confirmação` e `Tudo pronto!`.

**Escopo:** aplicar os 4 estados canônicos em todos os copys.

- Badge de menu card, PDP, API response
- Modal title/message: mapear error_codes → copy unificado
- Warnings inline no cart drawer e cart page
- Toast messages
- Remover todos os copys proibidos da tabela da seção 2

**Arquivos:** templates de storefront (`partials/*.html`, `components/availability_badge.html`), projeções (`cart.py`, `catalog.py`, `product_detail.py`), `web/views/cart.py`.

**Testes:** atualizar asserts de copy; adicionar teste de cobertura que verifica ausência das strings proibidas nos templates.

**Dependências:** WP-AV-01.

---

### WP-AV-03 — Remover seção "Outras opções" da PDP

**Status 2026-05-05:** implementado e validado. PDP não renderiza seção de substitutos; substituição fica restrita ao modal acionável de shortage. Cobertura em `shopman/storefront/tests/web/test_web_catalog.py`.

**Escopo:** correção do resíduo da rodada anterior. Substitutos são só no modal.

- Remover `{% if product.substitutes %}` de `templates/storefront/product_detail.html`
- Remover `substitutes` / `alternatives` do `ProductDetailProjection` dataclass e do builder
- Remover chamada a `find_substitutes` no builder quando `not can_add_to_cart`
- API `/api/catalog/.../` devolve `substitutes: []` apenas quando consumidor do modal pedir

**Testes:** atualizar `test_projections_product_detail.py`; adicionar teste que garante ausência da seção na PDP.

**Dependências:** WP-AV-01, WP-AV-02.

---

### WP-AV-04 — Gap B: PDP own-hold-aware

**Status 2026-05-05:** implementado e validado. Superfícies de leitura levam em conta o hold da própria sessão; o carrinho não marca como indisponível a quantidade já reservada pelo cliente. Cobertura em `shopman/storefront/tests/web/test_projections_cart.py` e no E2E do WP-AV-14.

**Escopo:** PDP usa o mesmo cálculo do cart. Coerência entre superfícies.

- `projections/product_detail.py`: ler `own_hold` via `_own_holds_for_session` (mover helper para um módulo compartilhado)
- Usar `max_orderable = max(0, ready_physical − (held_ready − own_hold) − margin)` em vez de `total_promisable`
- Atualizar `can_add_to_cart`, `available_qty`, `max_qty` da projeção com o novo cálculo

**Testes:** novo teste — cliente adiciona todas as unidades ao carrinho, PDP do mesmo SKU deve mostrar "Últimas unidades" compatível com cart_qty atual, não zero.

**Dependências:** WP-AV-01.

---

### WP-AV-05 — Gap E: extirpar `below_min_qty`

**Status 2026-05-05:** implementado e validado. `ListingItem.min_qty` permanece como dado de catálogo/preço, mas não é gate operacional de disponibilidade; `below_min_qty` só aparece em comentários/testes que documentam sua remoção.

**Escopo:** min_qty não é operacional; remover completamente.

- Remover branch `if qty < listing_item.min_qty` de `availability.decide()` e `availability.py`
- Campo `ListingItem.min_qty` permanece no modelo (zero custo), só não é enforced
- API `_badge_for()` remove código `below_min_qty`
- Testes que cobrem `below_min_qty` → remover

**Testes:** ajustar `test_services.py` e similar.

**Dependências:** WP-AV-02 (copy já removido no modal).

---

### WP-AV-06 — Gap F: 404 para fora do canal

**Status 2026-05-05:** implementado e validado. Produto publicado fora do `ListingItem` do canal retorna 404 no PDP. Cobertura em `shopman/storefront/tests/web/test_availability_plan_e2e.py`.

**Escopo:** produto não listado no canal retorna 404 em toda superfície.

- `web/views/catalog.py::ProductDetailView`: checar `ListingItem` antes de renderizar; se ausente/unpublished → 404
- `api/catalog.py`: mesmo guard → 404
- Menu e home: produto sem listing já não aparece (confirmar)

**Testes:** novo teste — GET `/produto/<sku>` de produto não listado devolve 404.

**Dependências:** WP-AV-02.

---

### WP-AV-07 — Gap G: stepper clamp transparente

**Status 2026-05-05:** implementado e validado. Steppers do menu, PDP, cart drawer e cart page recebem `effectiveMax`, desabilitam incremento no limite e mostram hint `máx. N`; o backend mantém o fallback 422/modal. Cobertura E2E no cenário "Últimas unidades".

**Escopo:** três camadas da seção 7, em todas as superfícies.

- Componente Alpine reutilizável para stepper (ou helper em `storefront_tags.py`)
- Inline `máx. N` + botão `+` desabilitado + toast em overshoot
- Aplicar em: `_catalog_item_grid.html`, `product_detail.html`, `cart_drawer.html`, `_cart_page_content.html`
- Backend clamp preserva regra no fallback 422 + toast

**Testes:** cobertura mínima: verificar inline `máx. N` aparece quando `current_qty` próximo de `max_orderable`.

**Dependências:** WP-AV-02, WP-AV-04.

---

### WP-AV-08 — Gap D: bundle libera holds de componentes em qty=0

**Status 2026-05-05:** implementado e validado. Holds de carrinho agora carregam `metadata.cart_source_sku`; holds de componentes de bundle também carregam `metadata.cart_bundle_sku`. O reconcile de bundle opera só nos holds desse bundle, então remover um combo libera todos os componentes daquele combo sem tocar uma linha simples que compartilhe o mesmo SKU de componente.

**Escopo:** `availability.reconcile()` para bundle SKU com `new_qty=0` libera holds de TODOS os componentes.

- `shopman/shop/services/availability.py`: reconcile branch `new_qty == 0` para bundles chama release por componente
- Manter invariante de grow-vs-shrink simétrico

**Testes:** `shopman/shop/tests/test_hold_adoption.py`, `shopman/shop/tests/test_hold_adoption_integration.py`, `shopman/shop/tests/test_services.py::TestAvailabilityReserveBundles`.

**Dependências:** nenhuma (isolado).

---

### WP-AV-09 — Gap C: renovação de `expires_at` em atividade do cart

**Status 2026-05-05:** implementado e validado. `availability.bump_session_hold_expiry()` renova holds ativos da sessão sem encurtar holds com janela maior e sem tocar holds planejados/indefinidos (`expires_at IS NULL`). `add_item`, `update_qty` e `remove_item` chamam a renovação após mutações bem-sucedidas.

**Escopo:** holds órfãos morrem naturalmente em TTL; holds ativos são renovados a cada atividade.

- `CartService.add_item`, `update_qty`, `set_qty`: após mutação, bumpar `expires_at = now + 30min` em todos os holds da sessão com `metadata.reference == session_key`
- Batch update em uma query

**Testes:** `shopman/shop/tests/test_hold_adoption.py`, `shopman/shop/tests/test_hold_adoption_integration.py`.

**Dependências:** nenhuma.

---

### WP-AV-10 — Gap A: push ativo via HTMX SSE

**Status 2026-05-05:** implementado e validado. `django-eventstream` está instalado; `storefront:stock_events` e `storefront:sku_state` existem; templates usam `hx-ext="sse"`/`sse-connect`; emissores em `shopman/shop/handlers/_sse_emitters.py` cobrem `stock-update`, `product-paused`, `listing-changed`, pedido e backstage. Redis fanout é canônico via `EVENTSTREAM_REDIS`.

**Escopo:** mudanças operacionais (Stockman Move, Product pause) disparam atualização ativa de steppers e badges abertos.

- Endpoint SSE `/storefront/stock/events/` em `web/views/`
- Shopman signal handler: `Move` post_save + `Product.is_sellable` change → publish event
- Templates chave adicionam `hx-ext="sse"` + `sse-connect=...` + `sse-swap=...`
- Escopo: apenas SKUs visíveis na página atual (filter client-side ou server-side)

**Testes:** integração simples — página carregada com SKU X, signal dispara, cliente recebe e re-fetcha.

**Dependências:** WP-AV-02.

---

### WP-AV-11 — Fermata: hold indefinido para demand/planned

**Status 2026-05-05:** implementado e validado. `create_hold` transforma holds de demanda/planned em `expires_at=None` e marca `metadata.planned=True`; `CartService.get_cart` classifica a linha com `is_awaiting_confirmation` / `is_ready_for_confirmation`. Cobertura em `shopman/shop/tests/test_planned_hold_classify.py` e no cenário Fermata do WP-AV-14.

**Escopo:** criação do hold-fermata.

- `shopman/shop/adapters/stock.py::create_hold`: detectar `demand_ok` ou `planned_ok + ready_physical == 0` → `expires_at = None`
- Cart `add_item`: não barrar; criar hold indefinido
- `CartProjection.items[].is_awaiting_confirmation` flag

**Testes:** adicionar produto `demand_ok` a cart vazio → hold criado com `expires_at IS NULL`; linha do cart marcada como aguardando.

**Dependências:** WP-AV-04.

---

### WP-AV-12 — Fermata: notificação ativa ao materializar

**Status 2026-05-05:** implementado e validado. `on_holds_materialized` resolve cliente da sessão por `customer_id` UUID/pk, `customer_ref` ou telefone, dispara `stock.arrived` com `deadline_at` calculado dos holds materializados e `cart_url` do storefront. Sessões anônimas continuam em no-op silencioso.

**Escopo:** wire `on_holds_materialized` com dispatch de notificação.

- Estender `shopman/shop/handlers/_stock_receivers.py::on_holds_materialized`: chamar `notify(event="stock.arrived", recipient=<canal resolvido>, context=...)` para cada sessão afetada
- Context inclui `sku`, `product_name`, `deadline_at`, `cart_url`
- Respeitar consentimentos ativos do cliente (ManyChat/SMS/email)
- `ChannelConfig.stock.materialized_ttl_minutes` passa a ser a fonte (default 60min, override por canal)

**Testes:** `shopman/shop/tests/test_stock_receivers.py`.

**Dependências:** WP-AV-11.

---

### WP-AV-13 — Fermata UI: countdown + estado "aguardando confirmação"

**Status 2026-05-05:** implementado e validado. Cart drawer e cart page exibem `Aguardando confirmação` antes da materialização e `Tudo pronto! Confirme até HH:MM` + countdown Alpine após materialização. `confirmation.js` faz countdown, polling barato e toast sticky de chegada.

**Escopo:** superfícies mostram o prazo explicitamente conforme princípio dos timeouts transparentes.

- Cart drawer e cart page: linha com `is_awaiting_confirmation` mostra badge `Aguardando confirmação`
- Após materialização: badge muda para `Tudo pronto! Confirme até HH:MM` + countdown Alpine
- Toast `cartUpdated` recebe notificação quando alguma linha materializa

**Testes:** render com linha em fermata → badge presente; após materialização + countdown → novo badge.

**Dependências:** WP-AV-11, WP-AV-12.

---

### WP-AV-14 — Testes E2E cross-surface

**Status 2026-05-05:** implementado e validado. Cobertura coletada pelo `make test-framework` em `shopman/storefront/tests/web/test_availability_plan_e2e.py`, usando `Client`/projeções para não tornar Playwright obrigatório.

**Escopo:** fechar o plano com cobertura ponta-a-ponta.

- Cenário 1 — Disponível normal: menu → PDP → add 2 → cart → checkout.
- Cenário 2 — Últimas unidades: menu → card clamp ativo → add max → no warning.
- Cenário 3 — Ajuste: pedir 10, tem 3 → modal → aceitar 3 → fica na superfície.
- Cenário 4 — Substituição (PDP): produto indisponível → modal → escolher substituto → redirect `/cart/`.
- Cenário 5 — Fermata: `demand_ok` → add → cart mostra "aguardando" → simular materialização → notificação + countdown.
- Cenário 6 — 404: produto não listado → 404.

**Testes:** pytest integration com `Client` ou Playwright (avaliar custo). Atualmente o projeto não tem Playwright; pode ficar em `Client` se cobertura suficiente.

**Dependências:** todos os anteriores.

---

## Dependências (grafo)

```
WP-AV-01 (rename)
├─→ WP-AV-02 (vocabulário)
│   ├─→ WP-AV-03 (remove PDP substitutos)
│   ├─→ WP-AV-05 (below_min_qty)
│   ├─→ WP-AV-06 (404)
│   └─→ WP-AV-10 (SSE push)
├─→ WP-AV-04 (PDP own-hold)
│   ├─→ WP-AV-07 (stepper clamp)
│   └─→ WP-AV-11 (fermata hold)
│       └─→ WP-AV-12 (notificação)
│           └─→ WP-AV-13 (UI countdown)
├─→ WP-AV-08 (bundle reconcile) [independente]
└─→ WP-AV-09 (expires_at renewal) [independente]

WP-AV-14 (E2E) ← todos
```

Execução serial recomendada; paralelismo possível apenas entre os ramos realmente independentes.

---

## Critério de saída

O plano é considerado completo quando:

1. Todos os WPs verdes, cada um com seus testes.
2. Teste E2E automatizado ou preview manual cobre os 6 cenários do WP-AV-14.
3. Zero resíduo do vocabulário proibido.
4. Nenhuma chamada a `find_alternatives` ou referência a `alternatives` no código (só `substitutes`).
5. Fermata funcional em sandbox: cliente adiciona produto `demand_ok`, simula materialização, recebe notificação (log de `notify()` com context correto), countdown aparece no cart.
