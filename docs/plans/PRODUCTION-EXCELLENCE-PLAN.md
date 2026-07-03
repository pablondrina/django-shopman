# PRODUCTION-EXCELLENCE-PLAN — Produção de ponta a ponta no nível das demais superfícies

> Elaborado em 2026-07-02, a partir de auditoria e2e verificada contra o código
> (Core Craftsman, orquestração `shop/`, superfícies backstage/fournil, docs/ADRs).
> Objetivo: a cadeia de planejamento e produção entra na fase alpha com a mesma
> maturidade, confiabilidade e excelência operacional de Pedidos/POS/KDS — e com a
> simplicidade que faz concorrente pensar "como não pensei nisso antes?".

## Princípios (inegociáveis)

1. **Core é sagrado.** A auditoria confirmou: o Craftsman é o elo mais maduro da
   cadeia (6 models com event ledger imutável, concorrência otimista via `rev`,
   `finish` idempotente, snapshot de BOM, sugestão com demanda/estação/desperdício,
   244 testes). **Nenhum WP deste plano altera o Core.** As lacunas estão na
   orquestração e na superfície; capacidades dormentes do Core viram features.
2. **Produção é LOTE, nunca por pedido.** WorkOrder = produção em lote planejada;
   KDS Prep = montagem do pedido. A conexão vendas↔produção permanece indireta
   (estoque, alertas, demanda, vínculo visual via `production_order_sync`).
3. **Config-driven como Orders.** Orders têm `ChannelConfig` (cascata, 8 aspectos);
   produção deve ter o equivalente — sem classes de lifecycle, sem herança.
4. **Ferramenta certa por interação** (ADR-001/ADR-003): signal para anunciar,
   adapter só com 2+ impls reais, Directive para comando async confiável.
5. **Omotenashi first.** O padeiro às 4h da manhã, de mãos enfarinhadas, num tablet:
   cada tela serve esse momento. Nada de jargão, nada de beco sem saída, feedback
   sempre.

## Estado atual (verificado 2026-07-02)

### O que já é excelente — preservar

| Camada | Evidência |
|--------|-----------|
| **Craftsman core** | `plan/adjust/start/finish/void` com invariantes, eventos semânticos (`WorkOrderEvent` com payloads canônicos), idempotência no `finish`, snapshot de BOM em `meta._recipe_snapshot`, `suggest()` com histórico/estação/committed/safety/waste (`packages/craftsman/.../services/queries.py:120`) |
| **Ponte estoque** | `craftsman/contrib/stockman/handlers.py` é o escritor único: planned→quant futuro, started→materializa expected, finished→consome insumos + `StockPlanning.realize()` + write-off de shortfall, voided→cancela planned |
| **Vínculo pedido↔WO** | `shop/handlers/production_order_sync.py` — denormalizado em `Order.data["awaiting_wo_refs"]` ↔ `WorkOrder.meta["committed_order_refs"]`, estratégia configurável (`Shop.defaults["production_order_match"]`), unlink transacional no void |
| **Fournil (Nuxt)** | Chão ao vivo (cards com timer/steps/finish/void/shortage-override) + Planejamento (matriz com sugestão inline, basis de confiança, atalho planejar/iniciar) — `surfaces/production-uithing-nuxt/app/pages/` |
| **Admin/Unfold** | Console com 6 páginas (produção do dia, planejamento, painel, relatórios 3 abas + CSV, pesagem, compromissos) — `shopman/backstage/admin_console/production.py` |
| **API headless** | `/api/v1/backstage/production/*` com envelope estruturado de shortage e permissão `operate_production` |

### As lacunas — o que este plano fecha

| # | Lacuna verificada | Evidência |
|---|-------------------|-----------|
| L1 | **Alerta de produção atrasada está morto em runtime.** `check_late_started_orders()` só é chamado pelo seed (`config/management/commands/seed.py:3533`). Nenhuma directive agendada, nenhum worker o dispara. O badge "atrasada" do fournil é cálculo da projection — o `OperatorAlert` nunca nasce em produção real. | `shop/handlers/production_alerts.py:63` |
| L2 | **`notify()` de produção é log-only.** O registry de notificações não conhece nenhum evento de produção; zero directives de produção (Orders têm 10+ topics). Operador não recebe nada fora da tela. | `shop/services/production.py:69-75`; `shop/notifications.py` (sem "production") |
| L3 | **Configuração de produção fragmentada e parte hardcoded.** `LOW_YIELD_THRESHOLD=0.80` e `DEFAULT_STARTED_MINUTES=240` em constantes; `production_lifecycle`, `max_started_minutes`, `waste_rate` soltos em `Recipe.meta` sem validação nem dataclass; `seasons`/`high_demand_multiplier`/`production_order_match` em `Shop.defaults` sem contrato documentado. | `shop/handlers/production_alerts.py:13-14`; `shop/production_lifecycle.py:21-27` |
| L4 | **`craft.needs()` (explosão de BOM → insumos do dia) não tem UI.** A capacidade mais valiosa para o mise en place do padeiro está dormente. A pesagem no Admin é estática (não escala insumos pela quantidade planejada). | `packages/craftsman/.../services/queries.py:89` |
| L5 | **Fournil é single-date e alertas são só contagem.** Sem horizonte (amanhã/semana); `AlertsBell` conta mas não abre detalhe nem deep-link; polling fixo 30s (SSE já existe no projeto para KDS de pedidos). | `surfaces/production-uithing-nuxt/app/pages/planejamento.vue`; `components/AlertsBell.vue` |
| L6 | **Fechamento do dia ignora produção.** `DayClosing` não acusa WOs abertas (planned esquecida, started atravessando o dia). | `shopman/backstage/models/` |
| L7 | **Cobertura de testes da orquestração é 1/10 da de Orders.** `test_production_lifecycle.py` = 94 linhas/7 casos vs `test_lifecycle.py` = 1045/75. Sem e2e da cadeia completa suggest→plan→start→finish→realize→venda. | `shop/tests/` |
| L8 | **Duplicação de superfície.** A matriz de planejamento existe no Admin e no fournil; risco de divergência e custo dobrado de manutenção. Papéis não estão formalizados. | `admin_console/production.py` + fournil |

### O que NÃO é lacuna (auditoria descartou)

- ~~"Nuxt não tem sugestões"~~ — tem, inline com basis (`planejamento.vue:101-107`).
- ~~"void não compensa estoque"~~ — `_handle_voided` do contrib/stockman cancela
  planned quants; `production_order_sync` desvincula pedidos transacionalmente.
- ~~"plan não valida insumos"~~ — o caminho formula/backstage devolve envelope de
  shortage no plan e no finish, com override explícito (`force`).
- ~~"variantes de lifecycle são gambiarra"~~ — `Recipe.meta["production_lifecycle"]`
  é decisão registrada (ADR-007). O que falta é validação/UI, não redesign.

## North star — o dia do padeiro

**04:00** Abre o fournil no tablet. O chão ao vivo mostra o que ficou de ontem (se
ficou, com alerta explicando). Toca "Planejamento": a matriz de hoje já veio
preenchida pela sugestão (demanda 28d, estação, committed dos pedidos, margem).
Cada número explica a si mesmo — um toque mostra o porquê.

**04:05** Toca "Mise en place": a lista de insumos do dia, explodida da BOM das
WOs planejadas, escalada e agrupada — pesa, separa, confere. Inicia as ordens.

**06:30** Fornadas saem. "Concluir" com a quantidade real; yield baixo gera alerta
com contexto (não um número mudo). Estoque da vitrine atualiza sozinho; pedidos
que aguardavam aquele lote ficam visíveis no gestor.

**14:00** Sugestão de amanhã pronta. Ajusta dois números, confirma. Se uma ordem
passou do tempo, o alerta chegou sozinho — ninguém precisou estar olhando a tela.

**18:00** Fechamento do dia acusa: 1 WO ainda iniciada. Resolve (conclui ou
estorna) e fecha com yield e perdas do dia no relatório.

Cada passo desse dia é um critério de aceite deste plano.

---

## Work Packages

Auto-contidos, em ordem de execução. Cada WP fecha com suíte verde
(`make test-framework` + `make test-craftsman` quando tocar em contrib) e, quando
tocar Admin, `make admin`.

### WP-PE0 — Sinais operacionais confiáveis (fundação) 🔴 ✅ (2026-07-02)

**Problema:** L1 + L6. O sistema sabe calcular atraso mas nunca avisa; o dia fecha
com produção pendurada sem ninguém acusar.

**Entregáveis:**
1. Directive agendada `production.late_check` (novo topic + handler), processada
   pelo worker de directives existente (ADR-003) — reagenda a si mesma no cadence
   configurado. Chama `check_late_started_orders()`; dedup já existe
   (`_recent_exists`, janela 12h).
2. Sweep de "produção esquecida" no mesmo handler: WO `planned` com `target_date`
   vencida → `OperatorAlert` (`production_forgotten`, novo tipo); WO `started`
   atravessando a virada do dia → incluída no late check.
3. `DayClosing` passa a acusar produção aberta: projection de fechamento
   (`backstage/projections/closing.py`) ganha bloco "produção pendente" (WOs
   planned/started do dia) com ação de resolver (link fournil/console). Não
   bloqueia o fechamento — acusa cedo e inline (validação omotenashi), com
   registro no snapshot do fechamento.
4. ~~Side-effects não-transacionais movem para `transaction.on_commit`~~ —
   **descartado na execução (2026-07-02)**: verificado que todos os
   side-effects do caminho de produção são writes transacionais (`OperatorAlert`
   via adapter, `Directive`). Directives devem nascer NA transação (ADR-003 —
   atomicidade com a mudança da WO); o `on_commit` de orders existe porque o
   dispatch de orders chama adapters externos, o que não é o caso aqui.
   Espelhar seria cargo-cult.

**Não fazer:** timeout automático que estorna WO sozinho (produção física não se
cancela por timer; o sistema avisa, o humano decide).

**Aceite:** com o worker rodando, uma WO started além de `max_started_minutes`
gera alerta sem nenhuma tela aberta; fechamento com WO aberta mostra o bloco;
testes de directive (agendamento, reagendamento, dedup) e de projection.

### WP-PE1 — `ProductionConfig`: configuração com contrato 🔴 ✅ (2026-07-02)

> **Exceção pontual ao "zero Core", justificada e mínima**: descoberto na
> execução que `Shop.defaults["safety_stock_percent"]` (editável no ShopAdmin)
> era **chave morta** — o Core lia só `settings.CRAFTSMAN`. Correção:
> `craft.suggest()`/`formula.suggest()` ganharam o parâmetro opcional
> `safety_pct` (default `None` = setting, comportamento inalterado),
> completando o seam de parametrização que já existia para `season_months` e
> `high_demand_multiplier`. Sem migração, sem mudança de schema, coberto por
> teste no pacote. Bônus da unificação via `suggest_for()`: a projection do
> backstage passou a aplicar estação/multiplicador/margem — antes só o CLI
> aplicava (sugestão da tela divergia da config da loja).

**Problema:** L3. Thresholds hardcoded, chaves soltas em dois JSONFields sem
validação nem inventário.

**Entregáveis:**
1. Dataclass `ProductionConfig` no orquestrador (`shop/config.py` ou módulo
   irmão), source of truth (padrão `feedback_dataclass_driven_admin`), lida de
   `Shop.defaults["production"]` com defaults sensatos:
   `low_yield_threshold` (0.80), `default_max_started_minutes` (240),
   `late_check_cadence_minutes`, `order_match` (absorve
   `production_order_match`), `seasons`, `high_demand_multiplier`,
   `suggestion_horizon_days`.
2. Consumidores param de ler constantes/chaves cruas: `production_alerts`,
   `production_order_sync`, `suggest_production`, projections.
3. Contrato de `Recipe.meta` validado e documentado. **Nota de execução
   (2026-07-03)**: o contrib Unfold do Craftsman já expunha estruturados
   `max_started_minutes`/`capacity_per_day`/`requires_batch_tracking`/
   `shelf_life_days`; faltava só `production_lifecycle`. Implementado como
   **seam provider-driven** (`CRAFTSMAN["PRODUCTION_LIFECYCLE_PROVIDER"]` →
   `production_lifecycle_choices()` do orquestrador), porque o gate de
   arquitetura veta deep-import de contrib em superfície e o pacote não pode
   conhecer as variantes do dispatch. Sem provider = sem campo (standalone
   limpo). `waste_rate` em `Recipe.meta` era mito documental: ninguém lê
   (o suggest computa do histórico) — não exposto.
4. `docs/reference/data-schemas.md` ganha as seções `Shop.defaults["production"]`
   e `Recipe.meta` (obrigação do CLAUDE.md — hoje o inventário não cobre produção).
5. Migração de dados: seed e deploy staging atualizados para o novo namespace
   (chaves antigas de `Shop.defaults` movidas com zero residuals — pré-go-live).

**Não fazer:** campo novo em model do Core; `RuleConfig` para produção (a engine
de rules serve pricing/validação de pedido — produção não tem 2º caso de uso real
ainda; reavaliar pós-alpha).

**Aceite:** nenhuma constante de produção hardcoded fora do dataclass; alterar
threshold no Admin reflete no alerta sem deploy; docs atualizados; suíte verde.

### WP-PE2 — Notificações de produção reais 🟠

**Problema:** L2. `notify()` é log; operador só descobre problema se estiver
olhando a tela certa.

**Entregáveis:**
1. Eventos de produção no registry de notificações
   (`production.late`, `production_low_yield`, `production_forgotten`,
   `production_stock_short`) com `NotificationTemplate` seedados — destinatário é
   **operador** (console/e-mail; WhatsApp Meta quando credencial existir), nunca
   cliente.
2. `production_svc.notify()` deixa de ser log-only: cria Directive
   `notification.send` (reuso integral da infra de Orders — handler, retry,
   idempotência), gated por `ProductionConfig.notifications_enabled` (default: só
   alertas críticos, para não virar spam).
3. `production_alerts` passa a emitir o par alerta-na-tela + notificação (quando
   habilitada), pelo mesmo caminho.

**Depende de:** WP-PE0 (topics/worker), WP-PE1 (config).

**Não fazer:** backend novo de notificação; notificação por evento de lifecycle
feliz (planned/started/finished normais ficam só no ledger — sinal, não ruído).

**Aceite:** yield baixo com notificações habilitadas → directive criada, template
renderizado, retry em falha; templates revisados com voz do projeto; testes de
handler + integração.

### WP-PE3 — Mise en place: `craft.needs()` ganha UI 🟠

**Problema:** L4. A joia dormente do Core. Nenhum concorrente de PDV/ERP leve dá
ao padeiro a lista de pesagem do dia derivada do plano — é exatamente o "uau".

**Entregáveis:**
1. Projection `build_production_mise_en_place(date, position)` em
   `backstage/projections/production.py`: agrega `craft.needs(date)` (imediato) +
   opção expandida (matéria-prima, `expand=True`), quantidades escaladas pelo
   coeficiente das WOs planejadas, agrupadas por insumo com quebra por receita.
2. Fournil: aba/rota "Mise en place" — lista tocável (check de separado por item,
   estado local Alpine→Vue), quantidade escalada + unidade, busca. Estado de
   separação é da sessão do turno (localStorage), não do banco — zero migração.
3. Admin/pesagem: filipetas passam a escalar insumos pela quantidade planejada da
   WO (hoje estático) reusando a mesma projection; imprime por ficha-base.
4. Disponibilidade de insumo anotada quando `INVENTORY_BACKEND` estiver ligado
   (Buyman WP-B5b) — **degrade gracioso**: sem backend, a lista vem sem saldos
   (não bloquear, conforme lei do seam dormente).

**Não fazer:** ligar `INVENTORY_BACKEND` antes de insumo ter estoque (bloquearia
`adjust`/`finish`); persistir checklist no Core.

**Aceite:** com 3 WOs planejadas para hoje, a lista mostra insumos agregados
corretos (casos com sub-receita cobertos por teste de projection); filipeta
térmica sai escalada; fournil funciona com luva/touch (alvos ≥44px).

### WP-PE4 — Fournil excellence: horizonte, alertas acionáveis, explicabilidade 🟠

**Problema:** L5 + L8. A superfície viva precisa do polish que POS/KDS já têm — e
os papéis Admin×fournil precisam ser formais.

**Entregáveis:**
1. **Split canônico formalizado** (resolve L8): fournil = execução (chão + planejamento
   + mise en place); Admin/Unfold = gestão (receitas, relatórios, pesagem,
   compromissos, auditoria). A matriz do Admin (`planning.html`) vira leitura
   (link "planejar no Fournil") ou é aposentada — decisão registrada no
   `unfold_canonical_inventory.md`. Zero residuals do caminho aposentado.
2. **Horizonte de planejamento**: seletor hoje/amanhã/D+n na matriz (a API já
   aceita `target_date`; a projection já é por data). Padrão: amanhã após as 12h
   (`ProductionConfig.suggestion_horizon_days`).
3. **Alertas acionáveis**: `AlertsBell` abre painel com os alertas de produção
   (tipo, WO, idade, mensagem) e deep-link para o card/linha correspondente;
   dispensar alerta = resolver `OperatorAlert` via API existente.
4. **Explicabilidade da sugestão**: tooltip/bottom-sheet no valor sugerido
   expondo o `basis` que o Core já entrega (média, amostra, committed, estação,
   multiplicador, waste) em linguagem de gente ("28 vendidos em média nas últimas
   4 sextas + 12 já encomendados + 10% de margem").
5. **Tempo real**: polling adaptativo (30s → 10s com WO late; pausa em aba
   oculta) e avaliação de SSE (infra `django-eventstream` já existe para KDS de
   pedidos) — adotar SSE se o custo for marginal, senão registrar decisão.
6. **A11y + omotenashi pass**: aria/foco nos dialogs, contraste dos badges,
   empty states com próximo passo, copy revisada (voz "nós", sem jargão).

**Aceite:** padeiro planeja amanhã sem tocar o Admin; alerta na bell leva ao card
em 1 toque; sugestão explica a si mesma; `make admin` verde após o split.

### WP-PE5 — Vínculo pedido↔produção visível nas duas pontas 🟡

**Problema:** o sync existe e funciona (verificado), mas só o Admin mostra
compromissos. O gestor de pedidos não mostra "aguardando produção"; o fournil não
mostra "este lote atende N pedidos".

**Entregáveis:**
1. Card de WO no fournil (chão + matriz) ganha chip "N pedidos" quando
   `meta["committed_order_refs"]` não-vazio; toque lista refs + qtds
   (`order_requirement_for_work_order` já calcula).
2. Gestor de pedidos (orders-uithing-nuxt): pedido com `awaiting_wo_refs` mostra
   badge "aguardando produção" com ref da WO e estado dela (projection do gestor
   já lê `Order.data`; incluir no payload).
3. Void de WO com pedidos vinculados: dialog de estorno passa a avisar ("3
   pedidos aguardam este lote") antes de confirmar — o unlink já é automático.

**Aceite:** cenário e2e seeded — pedido confirmado vincula, fournil mostra chip,
void avisa e desvincula, gestor reflete; testes de projection nas duas pontas.

### WP-PE6 — Paridade de testes: a cadeia inteira sob prova 🟡

**Problema:** L7. A confiança que Orders tem (75 casos de lifecycle + e2e),
produção não tem.

**Entregáveis:**
1. **E2E da cadeia canônica** (`shop/tests/e2e/test_production_e2e.py`):
   suggest (demand backend real com pedidos seeded) → plan → mise en place
   consistente → start → finish parcial (yield < 100%) → quants realizados na
   vitrine → hold de venda atendido → alerta de low yield criado → relatório
   reflete. Variante: void de started com pedido vinculado.
2. **Lifecycle**: casos para as 3 variantes (standard/forecast/subcontract),
   fases × ações, lifecycle desconhecido (fallback standard), `on_commit`.
3. **Integração dos WPs anteriores**: directive `production.late_check`
   (agendamento/reagendamento/dedup), notificações (template + retry),
   fechamento com produção aberta, config override via `Shop.defaults`.
4. Lacunas herdadas do Core cobertas **no nível de integração do orquestrador**
   (sem tocar o pacote): deficit downstream em adjust, ciclo em BOM multi-nível,
   `production_changed` → stockman → holds migrados.

**Aceite:** `make test-framework` cobre produção com ordem de grandeza comparável
a Orders; e2e roda no CI runtime gate.

---

## Sequência e dependências

```
WP-PE0 (fundação: sinais confiáveis)
   └→ WP-PE1 (config) ── necessário para PE2 e PE4.2
        └→ WP-PE2 (notificações)
WP-PE3 (mise en place)          — independente após PE1 (usa config p/ position)
WP-PE4 (fournil excellence)     — após PE0 (alertas) e PE1 (horizonte)
WP-PE5 (vínculo pedidos)        — independente; melhor após PE4.1 (split)
WP-PE6 (testes)                 — transversal; e2e fecha o plano
```

Estimativa de execução: PE0+PE1 numa frente; PE2+PE3 na seguinte; PE4 (a maior,
UI) na terceira; PE5+PE6 fecham. Cada frente termina mergeável e deployável em
staging.

## Progresso

- **2026-07-03 — WP-PE0 + WP-PE1 entregues** (frente de fundação):
  `ProductionConfig` (`shop/production_config.py`, 23 testes) com namespace
  `Shop.defaults["production"]` migrado em seed/Admin/testes (zero residuals);
  `suggest_for()` unifica CLI + projections + matriz (bug corrigido: tela
  ignorava estação/multiplicador; `safety_stock_percent` era chave morta —
  Core ganhou param opcional `safety_pct`, ver nota no WP-PE1); heartbeat
  `production.late_check` (12 testes) + sweep `production_forgotten` armado
  por `production_changed` e pelo seed; fechamento acusa produção aberta
  (projection + snapshot `pending_production` + bloco Unfold canônico, 8
  testes); `Recipe.meta["production_lifecycle"]` estruturado provider-driven
  (6 testes); `data-schemas.md` cobre produção. Suítes: framework 2472 ✅,
  craftsman 243 ✅, ruff ✅, gate Unfold canônico ✅.

## Fora de escopo (registrado para não perder)

- **Capacidade/turnos** (limite de forno, escala de operadores por estação):
  `FORMULA_CAPACITY_PROVIDER` já é o seam; ligar quando houver dado real.
- **Custeio de produção** (custo por lote via Buyman): Fase 2+ do
  BUYMAN-PROCUREMENT-PLAN.
- **Rastreabilidade de lote/validade fim-a-fim**: continua no
  VALIDITY-SHELFLIFE-REVIEW (P1/P2 = WP-B6); o `WorkOrderItem.meta` (lot/expires)
  já suporta.
- **Menuboard/superfícies de exibição**: CROSS-CHANNEL-CATALOG-HUB-PLAN.
- **Ações futuras de operador no KDS de pedidos** (recall/86): plano do KDS.
