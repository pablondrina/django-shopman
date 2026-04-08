# STATUS-REVIEW-PLAN — Revisão semântica do ciclo de vida do Order

> **Origem:** Auditoria de 2026-04-08 mapeou 10 incongruências entre o significado
> dos status do Order no Kernel (`packages/omniman/.../order.py`), no Framework
> (`framework/shopman/flows.py` + services), no Gestor (`web/views/pedidos.py`),
> no Storefront (`web/views/tracking.py` + templates), no KDS (`templates/kds/`)
> e no Admin Unfold.
>
> Este plano é dividido em pacotes de trabalho (WPs) auto-contidos, cada um
> com prompt autossuficiente para execução em uma sessão isolada do Claude Code.
> Prefixo `WP-ST` (status) para não colidir com `WP-S` (storefront).

## Inventário de incongruências (baseline da auditoria 2026-04-08)

| # | Incongruência | Camadas afetadas |
|---|---|---|
| 1 | `new` é ambíguo: docstring diz "aguardando processamento", mas `on_commit` já fez hold/loyalty/handle_confirmation. Em modo `immediate` é estado de microssegundos. | Kernel ↔ Framework |
| 2 | `processing` no Kernel diz "produção", mas KDS Prep é **montagem do pedido**, não produção em lote (regra `feedback_production_vs_sales`). | Kernel ↔ KDS ↔ memória |
| 3 | `ready` significa duas coisas (pickup: balcão / delivery: aguardando motoboy) mas o label customer-facing é único: "Pronto". | Kernel ↔ Storefront |
| 4 | `dispatched` é "só delivery" no docstring, mas a regra é enforced apenas em `_next_status_for()` (UI gestor). Modelo aceita transição direta `ready→dispatched` em pickup. | Kernel ↔ Gestor |
| 5 | `delivered` está fora de `_ACTIVE_STATUSES` no Gestor (`pedidos.py:82`) mas tem `next_action` definida (`pedidos.py:51`). Pedidos `delivered` somem da fila sem caminho operacional para `completed`. | Gestor |
| 6 | `delivered` vs `completed`: dois status sucessivos, ambos verdes, indistinguíveis para o cliente. Diferença real é fiscal/loyalty (invisível na UI). | Storefront |
| 7 | `Order.status` × `Fulfillment.status` aparecem **duplicados** no tracking.html (badge principal + seção "Entrega"), mesma string ("Saiu para entrega"), sem enforcement de sincronismo. | Storefront ↔ Kernel |
| 8 | `returned` é terminal no Gestor mas Kernel aceita `returned → completed`. Operação de devolução só existe via admin. | Gestor ↔ Kernel |
| 9 | `processing` é o único nome do enum cujo inglês destoa visivelmente do label português ("em preparo"). Carrega jargão técnico. | Convenção `ref-not-code` |
| 10 | KDS não reage a rollback de `Order.status`. Ponte `KDSTicket.done → Order.READY` é unidirecional. | Framework ↔ KDS |

---

## Pacotes de Trabalho

### WP-ST0 — Validação & escolha do tipo de fix (sem código)
**Objetivo:** Para cada uma das 10 incongruências, **validar contra o código
atual** (algumas podem já ter sido resolvidas) e, para as que persistem,
**escolher o tipo de correção** — não decidir SE corrige, mas COMO corrige.
**Zero código** apenas porque WP-ST1 a WP-ST6 vão implementar tudo. O plano
é orientado a CORREÇÃO, não a justificação.

**Saídas:**
- `docs/decisions/adr-009-order-status-semantics.md` — Para cada item:
  - Estado atual (caminho:linha citado).
  - Veredito: `já resolvido` (somente se grep prova) ou `corrigir`.
  - Se `corrigir`: tipo de fix (`renomear`, `refatorar Kernel`,
    `refatorar UI`, `enforcement`, `dedupe`, `split/merge`) + nome final
    proposto se aplicável + WP responsável (ST1/ST2/ST3/ST4/ST5/ST6).
  - Justificativa em 2-4 linhas citando impacto cross-layer.
- Tabela de decisões anexada na seção "Decisões aprovadas" deste arquivo.

**Veto explícito:** O ADR-009 NÃO PODE classificar nenhum item como
"manter porque é estilo" ou "aceitável". Toda incongruência real é dívida.
A única forma de um item sair sem fix é o grep provar que já foi resolvido
em commit recente — nesse caso o ADR cita o commit.

**Por que vem primeiro:** Os WPs seguintes precisam saber o nome final dos
status (para fazer renomes), a topologia final do enum (para atualizar
transitions), e quem é fonte da verdade entre Order e Fulfillment (para
implementar enforcement). Sem essas escolhas pré-feitas, WP-ST1 vira
debate em vez de execução.

---

### WP-ST1 — Kernel: Semântica de status
**Depende de:** WP-ST0 aprovado.
**Objetivo:** Aplicar as decisões do ADR-009 ao Kernel — docstrings, renomes,
splits/merges, transitions, schemas.

---

### WP-ST2 — Kernel: Enforcement de regras estruturais
**Depende de:** WP-ST1 mergeado.
**Objetivo:** Mover regras "só delivery", sync `Order ↔ Fulfillment`, e demais
invariantes do enforcement de UI para enforcement de modelo/service.

---

### WP-ST3 — Framework: KDS bridge & ciclo do prep
**Depende de:** WP-ST1.
**Objetivo:** KDS reagir a rollback de status (se ainda for problema), idempotência
de `kds.dispatch`, documentação explícita da ponte KDSTicket↔Order.status.

---

### WP-ST4 — Gestor: Fila ativa coerente
**Depende de:** WP-ST1, WP-ST2.
**Objetivo:** Resolver `delivered` órfão (`_ACTIVE_STATUSES` × `next_action`),
caminho operador para `returned`, labels alinhados ao Kernel renomeado.

---

### WP-ST5 — Storefront: UX de tracking sem duplicação
**Depende de:** WP-ST1, WP-ST2.
**Objetivo:** Dedupe Order.status × Fulfillment.status no tracking.html,
contextualizar "Pronto" para pickup/delivery, decidir UX final para
`delivered` vs `completed` para o cliente.

---

### WP-ST6 — Admin Unfold + testes E2E
**Depende de:** Todos os anteriores.
**Objetivo:** Alinhar labels do admin com nomenclatura final, cobertura E2E
para pickup completo, delivery completo, cancelamento e devolução. Garantir
regressão dos enforcements do WP-ST2.

---

## Decisões aprovadas
> Preenchido no WP-ST0 (2026-04-08). ADR completo: `docs/decisions/adr-009-order-status-semantics.md`.

| # | Veredito | Tipo de fix | Nome final | WP responsável |
|---|----------|-------------|------------|----|
| 1 | corrigir | refatorar Kernel | `new` (docstring) | ST1 |
| 2 | corrigir | refatorar Kernel | `preparing` (docstring; absorvido pelo #9) | ST1 |
| 3 | corrigir | refatorar UI | `ready` (label contextual no Storefront) | ST5 |
| 4 | corrigir | enforcement | `dispatched` — guard no `transition_status()` usando `fulfillment_type` | ST2 |
| 5 | corrigir | refatorar UI | adicionar `delivered` a `_ACTIVE_STATUSES` | ST4 |
| 6 | corrigir | refatorar UI | `completed` invisível ao cliente (label "Entregue" para ambos) | ST5 |
| 7 | corrigir | dedupe | Seção "Entrega" sem badge de status repetido | ST5 |
| 8 | corrigir | refatorar Kernel | `returned` vira terminal; remover `returned → completed` | ST1 |
| 9 | corrigir | renomear | `processing` → `preparing` (cross-layer) | ST1 |
| 10 | corrigir | refatorar Kernel | `kds.cancel_tickets()` chamado em `BaseFlow.on_cancelled()` | ST3 |

---

## Prompts auto-contidos (1 por WP)

> Cada prompt abaixo é executável em sessão isolada. Inclui contexto, escopo,
> arquivos relevantes, restrições e critério de aceitação. Não referencia
> "versões anteriores" — tudo o necessário está no prompt + repo + memória.

---

### Prompt: WP-ST0 — Audit & Decisões

```
Você está retomando o STATUS-REVIEW-PLAN do projeto django-shopman. Leia primeiro:
- CLAUDE.md (raiz do repo)
- docs/plans/STATUS-REVIEW-PLAN.md (este plano — em especial a seção "Inventário de incongruências")
- docs/reference/data-schemas.md
- ~/.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/MEMORY.md

Tarefa do WP-ST0: produzir o ADR-009 que VALIDA cada uma das 10
incongruências contra o código atual e ESCOLHE o tipo de fix para cada uma.
NÃO ESCREVA CÓDIGO. NÃO ALTERE MODELOS, SERVIÇOS, TEMPLATES OU TESTES.

IMPORTANTE: Este plano é orientado a CORREÇÃO. O objetivo do user é
ELIMINAR as incongruências, não justificá-las. NÃO classifique nada como
"manter porque é estilo" ou "aceitável". Toda incongruência real é dívida.
A única forma de um item sair sem fix é o GREP PROVAR que já foi resolvido
em commit recente — nesse caso o ADR cita o commit (hash + arquivo:linha).

Para cada item do inventário:
1. Verifique o estado ATUAL do código (caminho:linha) — algumas incongruências
   podem já ter sido resolvidas em commits recentes. Use Read/Grep/git log,
   não confie no inventário cegamente.
2. Veredito: `já resolvido` (com prova: commit hash + diff que prova) OU
   `corrigir`.
3. Se `corrigir`, escolha o TIPO de fix:
   - `renomear` (status muda de nome — propor o novo nome respeitando
     `ref-not-code`, descritivo, sem jargão inventado)
   - `refatorar Kernel` (semântica de status muda: docstring/transitions)
   - `split/merge` (status vira dois, ou dois viram um — descrever topologia
     final do enum + transitions)
   - `enforcement` (regra que vive na UI desce para o modelo/service)
   - `dedupe` (mesma info aparece em dois lugares — escolher fonte da verdade)
   - `refatorar UI` (label/template muda para refletir Kernel já correto)
4. Atribua o WP responsável: ST1 (semântica Kernel), ST2 (enforcement Kernel),
   ST3 (KDS bridge), ST4 (Gestor UI), ST5 (Storefront UX), ST6 (Admin/E2E).
5. Justifique em 2-4 linhas citando impacto cross-layer.

Formato do ADR-009: siga o template dos ADRs existentes em docs/decisions/
(ver adr-008-orchestrator-as-coordination-center.md como referência mais recente).

Após escrever o ADR, atualize a seção "Decisões aprovadas" de
docs/plans/STATUS-REVIEW-PLAN.md com uma tabela resumida (item # | decisão |
nome final se aplicável | WP que aplica).

Restrições:
- Zero código. Apenas leitura + escrita de docs.
- Convenções obrigatórias: ref-not-code (não `code`), zero residuals em renames,
  sem jargão inventado, Offerman = somente vendáveis (insumos em Stockman/Craftsman),
  zero backward-compat aliases.
- WorkOrders = produção em lote ANTECIPADA. KDS Prep = montagem do pedido.
  Nunca tratar `processing` como produção em lote.
- Se uma decisão exigir mudança de schema em Session.data/Order.data/
  Directive.payload, registre a chave nova/removida no ADR e referencie
  data-schemas.md para atualização posterior (no WP-ST1).

Critério de aceitação:
- ADR-009 escrito em docs/decisions/.
- Seção "Decisões aprovadas" do STATUS-REVIEW-PLAN.md preenchida com tabela
  (item # | veredito | tipo de fix | nome final | WP responsável).
- TODOS os itens corrigidos OU com prova de commit que já resolveu. Nenhum
  item pode ficar como "aceitável" / "manter por estilo".
- Resumo (3-5 bullets) ao usuário com as decisões mais impactantes para
  validação ANTES de partir para WP-ST1.

Ao final, mostre o TEXTO COMPLETO do prompt do WP-ST1 (que está em
docs/plans/STATUS-REVIEW-PLAN.md) para o usuário copiar para a próxima sessão.
```

---

### Prompt: WP-ST1 — Kernel: Semântica de status

```
Você está retomando o STATUS-REVIEW-PLAN do projeto django-shopman. Leia primeiro:
- CLAUDE.md
- docs/plans/STATUS-REVIEW-PLAN.md (em especial a seção "Decisões aprovadas")
- docs/decisions/adr-009-order-status-semantics.md
- docs/reference/data-schemas.md
- ~/.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/MEMORY.md

PRÉ-REQUISITO: O WP-ST0 deve estar concluído. Se a seção "Decisões aprovadas"
estiver vazia, INTERROMPA e peça ao usuário para rodar WP-ST0 primeiro.

Tarefa do WP-ST1: aplicar as decisões do ADR-009 ao Kernel.

Arquivos primários:
- packages/omniman/shopman/ordering/models/order.py (enum Status, _TRANSITIONS,
  docstrings)
- packages/omniman/shopman/ordering/models/fulfillment.py (se a decisão tocar
  o lifecycle paralelo)
- packages/omniman/shopman/ordering/admin.py (labels de get_status_display
  vêm de TextChoices, mudam automaticamente — mas verifique badges custom)
- docs/reference/data-schemas.md (atualizar se o ADR adicionar/remover chaves)

Mudanças a fazer (somente as listadas no ADR-009):
1. Sharpen docstrings de cada status — significado canônico, único, sem ambiguidade.
2. Renomes do enum (se decididos). Lembre: o valor do enum é string usada em
   queries, JSONFields, templates, testes. Faça grep amplo e troque TUDO de uma
   vez. Zero residuals.
3. Splits/merges (se decididos): atualizar `Status` enum + `_TRANSITIONS` +
   estados terminais.
4. Atualizar data-schemas.md se chaves de Session.data/Order.data mudarem.

Restrições inegociáveis:
- Zero residuals: nada de `# formerly X`, nada de aliases `OldName = NewName`.
  Migrações serão resetadas no projeto novo.
- ref-not-code: identificadores são `ref`. Exceção única: `Product.sku`.
- Sem features inventadas. Aplicar APENAS o que está no ADR.
- Confiar no Core: antes de adicionar campos ao Order, verifique se a info
  cabe em `Order.data` (JSONField). Não criar migrações para dados contextuais.
- O CommitService é o contrato Session→Order. Se uma chave nova precisa
  propagar de session.data para order.data, adicione na lista explícita em
  `_do_commit()` (packages/omniman/.../commit.py).

Após editar:
- Rodar `make test-omniman` (ou `make test` se preferir bateria completa).
- Rodar `make lint`.
- Reportar quais testes do Core e do Framework quebraram. Para cada quebra,
  decidir se: (a) é regressão a corrigir aqui, (b) é teste obsoleto a atualizar,
  (c) é dependência de framework que vai ser corrigida em WP-ST2/ST3/ST4/ST5/ST6
  (nesse caso, marcar como `xfail` com referência ao WP).

Critério de aceitação:
- Enum/transitions/docstrings refletem o ADR-009.
- `make lint` passa.
- `make test` passa OU testes que falham têm marcador xfail apontando para o WP responsável.
- Resumo ao usuário com diff conceitual + lista de quebras.

Ao final, mostre o TEXTO COMPLETO do prompt do WP-ST2 (em
docs/plans/STATUS-REVIEW-PLAN.md) para o usuário.
```

---

### Prompt: WP-ST2 — Kernel: Enforcement de regras estruturais

```
Você está retomando o STATUS-REVIEW-PLAN do projeto django-shopman. Leia primeiro:
- CLAUDE.md
- docs/plans/STATUS-REVIEW-PLAN.md
- docs/decisions/adr-009-order-status-semantics.md
- ~/.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/MEMORY.md

PRÉ-REQUISITO: WP-ST1 mergeado. Se enum/docstrings ainda não refletem ADR-009,
INTERROMPA.

Tarefa do WP-ST2: mover invariantes que hoje vivem na UI para o
modelo/service do Kernel.

Invariantes alvo (cada uma só se o ADR-009 confirmou):
A. `dispatched` só pode ser alcançado por orders com `data["delivery_method"] == "delivery"`.
   Hoje a regra vive em `framework/shopman/web/views/pedidos.py:_next_status_for()`.
   Mover para `Order.transition_status()` (ou para o método responsável por
   validar transições) em packages/omniman/shopman/ordering/models/order.py.
   Erro deve ser uma exceção tipada (ex.: `InvalidTransitionError` ou
   reuso de exceção existente — use Grep).

B. Sincronismo Order.status ↔ Fulfillment.status. Decisão do ADR-009 escolheu
   uma das opções:
   - Opção 1: Fulfillment é fonte da verdade para `dispatched`/`delivered`,
     Order replica via signal/handler.
   - Opção 2: Order é fonte da verdade, Fulfillment é replicado.
   - Opção 3: Mantêm-se independentes, mas há um invariante que falha
     fast se divergirem (ex.: `Order.transition_status('delivered')` exige
     `Fulfillment.status == 'delivered'`).
   Implementar a opção escolhida. Documentar no docstring do modelo.

C. Outras invariantes que o ADR-009 tiver proposto.

Arquivos prováveis:
- packages/omniman/shopman/ordering/models/order.py
- packages/omniman/shopman/ordering/models/fulfillment.py
- packages/omniman/shopman/ordering/services/ (procurar por transition logic)
- framework/shopman/services/fulfillment.py (signal handler)
- framework/shopman/web/views/pedidos.py (REMOVER a checagem agora redundante)

Restrições:
- Não duplicar: se a regra está no modelo, REMOVA da UI. Não deixar dois lugares
  validando a mesma coisa.
- Não inventar exceções novas se já existem. Use Grep para encontrar
  exceções de transição existentes.
- Zero gambiarras (memória feedback_zero_gambiarras).

Testes obrigatórios a adicionar:
- pickup tentando transicionar para `dispatched` → falha tipada.
- Ordering em delivery, fulfillment não-`delivered`, transição Order→`delivered` → falha tipada (se opção 3).
- Sincronismo: ao Fulfillment ir para `delivered`, Order vai para `delivered` (se opção 1).

Critério de aceitação:
- `make test` passa.
- `make lint` passa.
- Tentativa manual via shell de violar cada invariante levanta exceção tipada.
- Diff mostra REMOÇÃO da regra duplicada da UI.

Ao final, mostre o prompt do WP-ST3.
```

---

### Prompt: WP-ST3 — Framework: KDS bridge & ciclo do prep

```
Você está retomando o STATUS-REVIEW-PLAN do projeto django-shopman. Leia primeiro:
- CLAUDE.md
- docs/plans/STATUS-REVIEW-PLAN.md
- docs/decisions/adr-009-order-status-semantics.md
- ~/.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/MEMORY.md

PRÉ-REQUISITO: WP-ST1 mergeado.

Tarefa do WP-ST3: revisar a ponte KDS↔Order e garantir que o ciclo do prep
é coerente com o novo enum.

Pontos a verificar (não assuma — leia o código):
1. `framework/shopman/services/kds.py` — confirma se `kds.dispatch()` e
   `on_all_tickets_done()` ainda batem com o novo enum (status renomeado?
   transitions atualizadas?).
2. Idempotência de `kds.dispatch`: já foi parcialmente abordado em commit
   `0f2d745` ("deduplicate KDS dispatch"). Verifique se a lógica cobre:
   re-dispatch após rollback de status, dispatch concorrente, dispatch após
   ticket cancelado.
3. Rollback de Order.status enquanto há tickets KDS abertos: o que acontece?
   Hoje (segundo auditoria) o KDS não reage. Decida com base no ADR-009 se:
   (a) rollback é proibido enquanto há tickets ativos (enforcement no Kernel),
   (b) rollback cancela tickets automaticamente,
   (c) rollback é silencioso e tickets ficam órfãos (estado atual — não aceitável).
4. Documentar no docstring do KDSService a direção da ponte (uni ou bidirecional)
   e os invariantes garantidos.

Arquivos prováveis:
- framework/shopman/services/kds.py
- framework/shopman/models/ (KDSTicket — verificar campos de status próprios)
- framework/shopman/flows.py (on_processing → kds.dispatch)
- framework/shopman/handlers/ (handlers de KDS)

Testes a adicionar:
- Rollback de status com tickets ativos → comportamento decidido.
- Re-dispatch idempotente.
- Concurrent dispatch (usar transaction.atomic + select_for_update se necessário).

Restrições:
- WorkOrders ≠ KDS Prep. Não confunda. Memória feedback_production_vs_sales.
- Não criar UIs novas (memória feedback_no_standalone_admin) — KDS já existe.

Critério de aceitação:
- `make test-framework` passa.
- Docstring do KDSService explica a ponte.
- Diff mostra resolução do gap "KDS não reage a rollback".

Ao final, mostre o prompt do WP-ST4.
```

---

### Prompt: WP-ST4 — Gestor: Fila ativa coerente

```
Você está retomando o STATUS-REVIEW-PLAN do projeto django-shopman. Leia primeiro:
- CLAUDE.md
- docs/plans/STATUS-REVIEW-PLAN.md
- docs/decisions/adr-009-order-status-semantics.md
- ~/.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/MEMORY.md

PRÉ-REQUISITO: WP-ST1 e WP-ST2 mergeados.

Tarefa do WP-ST4: alinhar o Gestor de Pedidos ao Kernel pós-renome e
resolver inconsistências operacionais.

Mudanças obrigatórias:
1. **`delivered` órfão**: hoje `pedidos.py:82` não inclui `delivered` em
   `_ACTIVE_STATUSES`, mas `pedidos.py:51` define o label "Concluir ✓" para ele.
   Aplicar a decisão do ADR-009:
   - Opção A: incluir `delivered` em `_ACTIVE_STATUSES` (operador conclui).
   - Opção B: auto-transicionar `delivered → completed` no `flows.py:on_delivered`
     e remover o label de pedidos.py:51.
   Implementar a opção decidida e remover qualquer código residual da outra opção.

2. **`returned`**: se o ADR-009 decidiu criar caminho operador para devolução,
   adicionar a UI no gestor (botão, transição). Caso contrário, manter no admin
   apenas.

3. **Labels alinhados**: atualizar `STATUS_LABELS`/`STATUS_COLORS` em
   `framework/shopman/web/views/tracking.py` para refletir os renomes do
   ADR-009. Como `pedidos.py` importa de `tracking.py`, mudar lá já propaga.

4. **Remover regras duplicadas**: se WP-ST2 moveu a regra "dispatched só
   delivery" para o modelo, remover o `_next_status_for()` ou simplificá-lo
   (pode virar puro lookup do mapa, sem lógica de delivery).

Arquivos primários:
- framework/shopman/web/views/pedidos.py
- framework/shopman/web/views/tracking.py (STATUS_LABELS / STATUS_COLORS / EVENT_LABELS)
- framework/shopman/templates/pedidos/partials/card.html
- framework/shopman/templates/pedidos/partials/detail.html
- framework/shopman/flows.py (se Opção B do item 1)

Restrições:
- HTMX para servidor, Alpine para DOM. Nunca onclick/getElementById/classList.
- Não criar UIs standalone novas para o que admin já resolve
  (memória feedback_no_standalone_admin). Esta é uma exceção válida (gestor já existe).
- Zero residuals em renames de strings.

Testes:
- View tests do gestor cobrindo cada status ativo (lista + detalhe + transição).
- Garantir que pickup não vê botão "Saiu para Entrega".
- Garantir que delivery vê o botão correto em `ready`.

Critério de aceitação:
- `make test-framework` passa.
- Verificação visual via preview_* (preview_start, navegar para /pedidos/,
  preview_snapshot) confirma fila coerente.
- Diff mostra remoção de qualquer regra duplicada removida do gestor.

Ao final, mostre o prompt do WP-ST5.
```

---

### Prompt: WP-ST5 — Storefront: UX de tracking sem duplicação

```
Você está retomando o STATUS-REVIEW-PLAN do projeto django-shopman. Leia primeiro:
- CLAUDE.md
- docs/plans/STATUS-REVIEW-PLAN.md
- docs/decisions/adr-009-order-status-semantics.md
- ~/.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/MEMORY.md

PRÉ-REQUISITO: WP-ST1 e WP-ST2 mergeados.

Tarefa do WP-ST5: refazer a UX de tracking do storefront para eliminar
duplicação Order.status × Fulfillment.status, contextualizar "Pronto" e
aplicar a decisão final de `delivered`/`completed` para o cliente.

Problemas a resolver (cada um conforme decisão do ADR-009):
1. **Duplicação Order × Fulfillment**: hoje cliente vê "Saiu para entrega"
   no badge principal E na seção "Entrega" (`tracking.html:29-60`). Decidir
   uma única apresentação coerente — provavelmente uma timeline única que
   funda eventos de Order.status e Fulfillment.status, com a "Entrega" sendo
   apenas a porção final dessa timeline.

2. **"Pronto" sem contexto**: pickup vê "Pronto" e delivery também. Adicionar
   subtítulo contextual ("Aguarde no balcão" vs "Aguardando motoboy") OU
   substituir por status distinto se o ADR-009 decidiu split.

3. **`delivered` vs `completed` para o cliente**: se o ADR-009 decidiu fundir
   no front (apenas "Entregue" visível, `completed` é interno fiscal), aplicar.
   Se decidiu manter ambos, garantir que o cliente entende a diferença
   (ex.: "Entregue" como state, "Concluído" como evento de timeline).

Arquivos primários:
- framework/shopman/web/views/tracking.py (STATUS_LABELS, FULFILLMENT_STATUS_LABELS, EVENT_LABELS, _build_tracking_context)
- framework/shopman/templates/storefront/tracking.html
- framework/shopman/templates/storefront/partials/order_status.html

Restrições:
- HTMX↔servidor, Alpine↔DOM. Nada de onclick/getElementById/classList.
- Não adotar libs externas de componentes (memória feedback_no_external_component_lib).
- Tailwind + Alpine + HTMX custom.

Testes + verificação visual:
- Testes de view cobrindo: pickup em cada status; delivery em cada status;
  cancelamento; devolução.
- Verificação visual obrigatória via preview_*:
  preview_start → navegar para um order de pickup em `ready` → preview_snapshot
  → navegar para um order de delivery em `ready` → preview_snapshot →
  comparar para confirmar contextualização.
- preview_screenshot final para mostrar ao usuário.

Critério de aceitação:
- `make test-framework` passa.
- preview_snapshot confirma sem duplicação visual.
- Screenshot anexado para validação do usuário.

Ao final, mostre o prompt do WP-ST6.
```

---

### Prompt: WP-ST6 — Admin Unfold + testes E2E

```
Você está retomando o STATUS-REVIEW-PLAN do projeto django-shopman. Leia primeiro:
- CLAUDE.md
- docs/plans/STATUS-REVIEW-PLAN.md
- docs/decisions/adr-009-order-status-semantics.md
- ~/.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/MEMORY.md

PRÉ-REQUISITO: WP-ST1 a WP-ST5 mergeados.

Tarefa do WP-ST6: alinhar admin Unfold à nomenclatura final e garantir
cobertura E2E dos fluxos completos.

Mudanças no admin:
1. Verificar `packages/omniman/shopman/ordering/admin.py` (OrderAdmin,
   FulfillmentAdmin). Os labels de `get_status_display()` vêm das choices do
   model — devem refletir automaticamente o WP-ST1. Garantir.
2. `framework/shopman/admin/dashboard.py` — auditoria detectou um STATUS_LABELS
   variante aqui. Alinhar com tracking.py (ou eliminar a duplicação importando
   de tracking.py se fizer sentido).
3. Row actions: confirmar que `advance_status_row` e `cancel_order_row` ainda
   funcionam após mudanças de transitions (WP-ST1) e enforcement (WP-ST2).

Testes E2E obrigatórios (criar em `framework/shopman/tests/e2e/` ou
estender existentes):
- **Pickup completo**: criar pedido pickup → confirmar → processing → ready →
  completed. Verificar que `dispatched` NÃO é alcançável.
- **Delivery completo**: criar pedido delivery → confirmar → processing →
  ready → dispatched → delivered → completed. Verificar Fulfillment sincronizado
  conforme decisão do WP-ST2.
- **Cancelamento**: cancelar em cada status ativo, verificar release de stock
  e refund.
- **Devolução**: completar e devolver, verificar revert de stock e fiscal cancel.
- **Regressão dos enforcements**: tentativa de violar cada invariante do
  WP-ST2 levanta exceção tipada.

Restrições:
- Não inventar testes "porque sim". Cada teste deve cobrir um caminho real
  de usuário ou uma regra do ADR-009.
- Não criar fixtures duplicadas. Reutilizar factories/seed existentes.

Critério de aceitação:
- `make test` (bateria completa) passa.
- `make lint` passa.
- Cobertura E2E demonstrada por relatório curto (lista de cenários × resultado).
- Resumo final ao usuário do que mudou em cada layer (Kernel, Framework, Gestor,
  Storefront, KDS, Admin) — basicamente um changelog do STATUS-REVIEW-PLAN.

Este é o ÚLTIMO WP do plano. Após concluído:
- Mover docs/plans/STATUS-REVIEW-PLAN.md para docs/plans/completed/.
- Atualizar a memória `project_current_state.md` se relevante.
- Avisar explicitamente ao usuário que o plano foi concluído.
```

---

## Notas finais

- **Convenções obrigatórias** referenciadas em todos os prompts: `ref-not-code`,
  zero residuals, sem features inventadas, sem aliases backward-compat,
  Offerman = só vendáveis, KDS Prep ≠ produção, HTMX↔servidor / Alpine↔DOM,
  zero gambiarras, respeitar Core antes de modificar.
- **Memória obrigatória** em cada prompt: o agente deve carregar MEMORY.md
  antes de começar.
- **Verificação visual** (WP-ST4 e WP-ST5) usa preview_* tools, nunca Bash
  para subir dev server.
- **Não pular WP-ST0**: todos os WPs subsequentes dependem das decisões.
