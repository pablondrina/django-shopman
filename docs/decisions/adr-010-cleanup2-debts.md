# ADR-010: CLEANUP2 — Auditoria de débitos pós WP-CLEAN1

**Status:** Aceito
**Data:** 2026-04-08
**Contexto:** Fechamento dos 8 débitos identificados após WP-CLEAN1

---

## Contexto

WP-CLEAN1 migrou o stock para o pattern function-style adapter, criou
`services/availability.py` como API canônica sync para checagem/reserva,
e fixou `MarketplaceFlow` com rejeição pré-emptiva. Este ADR valida cada
um dos 8 débitos (D1..D8) contra o código atual e decide o tipo de fix.

Arquivos de referência auditados:
- `framework/shopman/services/availability.py` — check(), reserve(), _sku_in_channel_listing()
- `framework/shopman/models/alerts.py` — TYPE_CHOICES
- `framework/shopman/flows.py` — LocalFlow.on_commit, MarketplaceFlow.on_commit
- `framework/shopman/web/views/tracking.py` — ReorderView
- `framework/shopman/backends/` — listagem de arquivos remanescentes
- `packages/*/shopman/` — namespaces Python reais vs persona names

---

## D1 — Bundle expansion em `availability.check`

**Estado atual** (`services/availability.py:37-126`):

`check(sku, qty, channel_ref)` não tem nenhuma lógica de bundle expansion.
Linha 76: importa `availability_for_sku` do Stockman e consulta diretamente o
SKU passado. Para um SKU de bundle que não tem posição própria no Stockman
(apenas seus componentes têm), a branch "untracked" (linha 104-112) retorna
`ok=True, available_qty=999999, untracked=True` — o bundle passa silenciosamente
como disponível infinito, mesmo que seus componentes estejam esgotados.

`reserve()` (linha 160-244) chama `check()` e depois `adapter.create_hold(sku=bundle_sku)` —
cria um hold no bundle, não nos componentes. O `services/stock.py::hold(order)` a
jusante expande corretamente (linhas 54-91), mas nesse ponto o hold de reserva
do carrinho já foi criado de forma errada.

**Veredito:** `confirmado` — débito real e crítico.

**Tipo de fix:** Modificar `check()` para expandir bundles via
`CatalogService.expand()` e iterar sobre componentes. `reserve()` deve criar
um hold por componente (não um hold do bundle). Detalhes em DD-1 do plano.

**WP responsável:** CL2-1

**Justificativa:** Um cliente pode adicionar um bundle ao carrinho mesmo que
todos os seus componentes estejam esgotados. O pedido só falha em
`stock.hold(order)` no commit, que cria holds parciais e loga warning. O
cliente vê o pedido como criado, mas o stock está inconsistente. Impacto em
produção: alto.

---

## D2 — `OperatorAlert.TYPE_CHOICES` desatualizado

**Estado atual** (`models/alerts.py:11-17`):
```python
TYPE_CHOICES = [
    ("notification_failed", "Notificação falhou"),
    ("payment_failed", "Pagamento falhou"),
    ("stock_discrepancy", "Discrepância de estoque"),
    ("payment_after_cancel", "Pagamento após cancelamento"),
    ("stock_low", "Estoque baixo"),
]
```

Tipos emitidos no código (grep `_create_alert` + `OperatorAlert.objects.create`):
- `flows.py:137` — `"payment_after_cancel"` ✓ (registrado)
- `flows.py:286` — `"marketplace_rejected_unavailable"` ✗ (NÃO registrado)
- `flows.py:298` — `"marketplace_rejected_oos"` ✗ (NÃO registrado)
- `flows.py:312` — `"payment_after_cancel"` ✓ (registrado)
- `handlers/stock_alerts.py:56` — `OperatorAlert.objects.create` direto (verificar tipo)
- `handlers/notification.py:124` — `OperatorAlert.objects.create` direto (verificar tipo)

Dois tipos são emitidos mas não registrados: `marketplace_rejected_unavailable`
e `marketplace_rejected_oos`. O admin filter por tipo pode mostrar uma string
solta sem label legível.

**Veredito:** `confirmado`.

**Tipo de fix:** Adicionar os dois tipos faltantes em `TYPE_CHOICES`. Verificar
também os tipos emitidos em `stock_alerts.py` e `notification.py` (leitura
direta, não via `_create_alert`).

**WP responsável:** CL2-2

**Justificativa:** Sem impacto em runtime (CharField sem `choices` enforcement
no DB), mas o admin Unfold exibe o valor bruto em vez do label PT-BR. Em
produção, o operador vê `"marketplace_rejected_unavailable"` no filtro em vez
de "Marketplace rejeitado: indisponível". Low severity, fix trivial.

---

## D3 — `availability.check` ignora `ListingItem.min_qty`

**Estado atual** (`services/availability.py:129-157`):

`_sku_in_channel_listing()` retorna `bool` — apenas verifica existência da
`ListingItem`. A `ListingItem.min_qty` (se existir no modelo) não é consultada.
`check()` usa o retorno bool da função (linha 64) e não tem acesso ao objeto
`ListingItem` para verificar `min_qty`.

Verificação rápida do modelo:

```python
# packages/offerman/shopman/offering/models/listing.py
# ListingItem.min_qty precisa ser confirmado
```

**Veredito:** `confirmado` — `_sku_in_channel_listing` retorna bool, não
`ListingItem`; `min_qty` não é checado em `availability.check`.

**Tipo de fix:** Refatorar `_sku_in_channel_listing()` para retornar
`ListingItem | None`. Em `check()`, após o gate de listing, verificar se
`qty < listing_item.min_qty` e retornar `ok=False, error_code="below_min_qty"`.
Adicionar mensagem correspondente no modal de erro do storefront.

**WP responsável:** CL2-3

**Justificativa:** Pedidos com qty abaixo do mínimo do canal chegam ao hold
sem validação. Impacto médio — encomendas mínimas de pão francês (24 unidades)
podem ser feitas com qty=1.

---

## D4 — POS path bypassa `availability.check`

**Estado atual** (`flows.py:191-194`):
```python
class LocalFlow(BaseFlow):
    def on_commit(self, order):
        customer.ensure(order)
        stock.hold(order)           # sem availability.check antes
        loyalty.redeem(order)
        order.transition_status(Order.Status.CONFIRMED, actor="auto_confirm")
```

`MarketplaceFlow.on_commit` (linha 264-298) faz `availability.check` por item
antes de `stock.hold` e rejeita o pedido se falhar. `LocalFlow.on_commit` vai
direto para `stock.hold`. Um item pausado ou esgotado no POS chega ao hold sem
gate.

**Veredito:** `confirmado`.

**Tipo de fix:** Adicionar loop de `availability.check` em `LocalFlow.on_commit`
antes de `stock.hold`, simétrico ao `MarketplaceFlow`. Em caso de falha:
`_create_alert(order, "pos_rejected_unavailable")` + transição para CANCELLED.
Adicionar `"pos_rejected_unavailable"` em `TYPE_CHOICES` (se CL2-2 não tiver
feito).

**WP responsável:** CL2-4

**Justificativa:** Assimetria entre canais: web e marketplace têm gate,
POS não tem. Severidade baixa (operador vê o estoque visualmente), mas o
comportamento inconsistente é um débito real. Fix tem cuidado especial com
double-transition (on_commit já faz `transition_to(CONFIRMED)`; se rejeitarmos,
devemos ir para CANCELLED e retornar sem confirmar).

---

## D5 — `ReorderView` engole `CartUnavailableError` silenciosamente

**Estado atual** (`web/views/tracking.py:274-302`):
```python
except CartUnavailableError:
    # Best-effort reorder: skip items currently out of stock.
    continue
```

Itens pulados são ignorados silenciosamente. O cliente é redirecionado para
o cart sem saber quais itens não foram adicionados. Pode criar confusão
("meu pedido anterior tinha 5 itens, o cart tem 2").

**Veredito:** `confirmado` — o `pass`/`continue` silencioso é o problema
exato descrito em D5.

**Tipo de fix:** Coletar SKUs/nomes dos itens pulados, salvá-los em
`request.session["reorder_skipped"]`, redirecionar para o cart com
`?reorder_skipped=1`. O template do cart renderiza um banner Alpine `x-show`
dispensável. Nada de JS imperativo.

**WP responsável:** CL2-5

**Justificativa:** UX de reorder é uma feature de conversão. Cliente que não
entende por que o pedido ficou menor pode abandonar o carrinho. Fix simples
com session + banner Alpine.

---

## D6 — `backends/` com 8 arquivos não migrados para `adapters/`

**Estado atual** (`framework/shopman/backends/`):
```
accounting_mock.py
checkout_defaults.py
fiscal_mock.py
notification_console.py
notification_email.py
notification_manychat.py
notification_sms.py
pricing.py
```

WP-CLEAN1 migrou os backends de stock e payment para `adapters/` no padrão
function-style. Os 8 arquivos acima permanecem class-based em `backends/`.

Estratégia por arquivo (definida em DD-5 do plano):
- `notification_console.py`, `notification_email.py`, `notification_manychat.py`,
  `notification_sms.py` → **migrar** para `adapters/` function-style (CL2-6)
- `pricing.py`, `checkout_defaults.py` → **inline** no service/handler e deletar (CL2-7)
- `fiscal_mock.py`, `accounting_mock.py` → **mover** para tests/_mocks/ ou deletar (CL2-8)

**Veredito:** `confirmado` — 8 arquivos remanescentes exatamente como descrito.

**WP responsável:** CL2-6 (notifications), CL2-7 (pricing/checkout_defaults),
CL2-8 (mocks)

**Justificativa:** Inconsistência arquitetural: stock e payment são
function-style em adapters/, notification e pricing são class-based em
backends/. Dificulta onboarding e aumenta o overhead cognitivo.

---

## D7 — Namespaces Python divergem das personas

**Estado atual** (verificado com `ls packages/*/shopman/`):

| Diretório de package | Namespace Python real | Persona |
|---|---|---|
| `packages/stockman/` | `shopman.stocking` | Stockman |
| `packages/omniman/` | `shopman.ordering` | Omniman |
| `packages/offerman/` | `shopman.offering` | Offerman |
| `packages/guestman/` | `shopman.customers` | Guestman |
| `packages/craftsman/` | `shopman.crafting` | Craftsman |
| `packages/payman/` | `shopman.payments` | Payman |
| `packages/doorman/` | `shopman.auth` | Doorman |

Grep mostra **401 ocorrências** de `from shopman.stocking/ordering/offering/customers`
só no `framework/shopman/`. Os nomes de persona são os definitivos desde ADR
e memória `feedback_persona_names_only.md`.

**Veredito:** `confirmado` — divergência real entre diretório do package
(persona) e namespace Python importável (nome antigo).

**Tipo de fix:** WP-CL2-9 produz o mapa completo e script idempotente.
WP-CL2-10 executa o rename físico, exige aprovação separada do usuário.

**WP responsável:** CL2-9 (prep), CL2-10 (execução — exige aprovação)

**Justificativa:** O código é lido com muito mais frequência do que é escrito.
`from shopman.ordering.models import Order` e `from shopman.omniman.models import Order`
têm o mesmo resultado hoje, mas o segundo reflete a identidade do projeto.
Com 401 ocorrências, o rename é o maior WP do plano — justifica o dry-run
isolado de CL2-9.

---

## D8 — Sem endpoint público de availability + sem polling HTMX na vitrine

**Estado atual:**
- `framework/shopman/api/catalog.py` tem endpoint de catálogo com
  availability embutida (`/api/catalog/` retorna produtos com badge).
  Não existe endpoint dedicado `/api/availability/<sku>/`.
- Templates de storefront: há polling `hx-trigger="every 60s"` no
  `home.html:112-113` para availability_preview do menu, mas é um endpoint
  de menu completo, não um badge individual por SKU.
- Não existe `templates/storefront/partials/availability_badge.html`.
- PDP (`product_detail.html`) e cards de catálogo renderizam badge via SSR
  sem polling.

**Veredito:** `confirmado` — endpoint dedicado e badges HTMX auto-atualizáveis
por SKU não existem.

**Tipo de fix:**
- CL2-11: criar `GET /api/availability/<sku>/?channel=<ref>` retornando
  `{ok, available_qty, badge_text, badge_class, is_bundle}`. Com cache de
  10s e rate limit.
- CL2-12: criar `partials/availability_badge.html` com
  `hx-trigger="every 30s"`. Substituir badges estáticos em catálogo e PDP.

**WP responsável:** CL2-11, CL2-12

**Justificativa:** Em produção, a vitrine pode mostrar "Disponível" para um
produto que esgotou há 20 minutos. O cliente adiciona ao carrinho, o
`reserve()` falha, e ele vê o modal de erro. Com polling de 30s, o badge
já estaria correto quando o cliente chega na PDP.

---

## Tabela de decisões

| D# | Veredito | Tipo de fix | WP |
|----|----------|-------------|-----|
| D1 | confirmado | Implementar bundle expansion em `check()` + holds por componente em `reserve()` | CL2-1 |
| D2 | confirmado | Adicionar 2 tipos faltantes em `TYPE_CHOICES` + migration | CL2-2 |
| D3 | confirmado | Refatorar `_sku_in_channel_listing()` → retorna `ListingItem\|None`; checar `min_qty` | CL2-3 |
| D4 | confirmado | Loop de `availability.check` em `LocalFlow.on_commit` antes de `stock.hold` | CL2-4 |
| D5 | confirmado | Coletar skipped em session, banner Alpine no cart | CL2-5 |
| D6 | confirmado | 4 notification backends → adapters/ (CL2-6); pricing/checkout_defaults inline (CL2-7); mocks → tests/ (CL2-8) | CL2-6/7/8 |
| D7 | confirmado | dry-run map (CL2-9) + rename físico (CL2-10, exige aprovação) | CL2-9/10 |
| D8 | confirmado | endpoint `/api/availability/<sku>/` (CL2-11) + HTMX badges (CL2-12) | CL2-11/12 |

---

## Consequências

### Positivas
- D1 (crítico): pedidos de bundle nunca mais chegam ao commit com stock inconsistente
- D4: comportamento de stock uniform entre todos os canais
- D6: `backends/` vazio ao fim de CL2-8 — arquitetura coerente
- D7: `from shopman.omniman.models import Order` — identidade do projeto refletida no código
- D8: vitrine sempre atualizada sem reload do cliente

### Negativas
- D7 é o maior WP em volume de mudanças (401+ ocorrências) — risco de regressão
  mitigado pelo dry-run de CL2-9 e aprovação explícita antes de CL2-10
- D1 requer atenção ao caso de bundles com componentes que se repetem (evitar
  double-hold do mesmo componente se dois bundles no carrinho compartilham
  um ingrediente)

### Mitigações
- CL2-9 produz script idempotente e mapa completo antes de qualquer rename
- CL2-1 espelha exatamente o padrão já validado em `services/stock.py:54-91`
- Todos os WPs têm `make test` como critério de aceitação
