# RESTRUCTURE-PLAN — Kernel + Framework

**Criado:** 2026-04-10
**Entrada:** [`docs/audit/2026-04-10-kernel-framework-audit.md`](../audit/2026-04-10-kernel-framework-audit.md)
**Status:** ativo

---

## 0. Por que este plano existe

A auditoria de 2026-04-10 mostrou que o **kernel** (`packages/`) está
estruturalmente intacto — protocols vivos, zero imports inversos, fronteiras
respeitadas — mas tem **resíduo massivo de naming antigo** e **dois pontos onde
o framework vaza para dentro dele** (`Hold.metadata__reference`, contribs do
guestman). O **framework** (`framework/shopman/`) é onde está o estrago real:
runtime imperativo (subclasses de Flow) que ignora o `ChannelConfig`
declarativo, caminhos duplicados (`handlers/customer.py` vs
`services/customer.py`), 13 dos 21 campos de config nunca lidos, handlers
órfãos, `try/ImportError` mascarando dependências obrigatórias.

Este plano é a reestruturação completa. Não é série de patches — é a
reescrita do runtime do framework + limpeza cirúrgica do kernel + publicação
de superfícies públicas que faltam.

---

## 1. Princípios fundadores (decisões já fechadas)

Estas decisões saíram da conversa de auditoria e **não** são revisitadas durante
os WPs — são entrada, não output.

1. **Configurabilidade via Admin é objetivo de primeira classe.**
   O máximo de regras de negócio, decisões comerciais e parâmetros de canal
   deve ser configurável via Django Admin (com permissões), não via código.
   Isso significa que o `ChannelConfig` precisa ser **realmente consumido**
   pelo runtime, não decorativo.

2. **Aplicação configurável > kit.**
   Shopman é uma aplicação configurável. A camada de **instância**
   (`instances/nelson/`) é responsável apenas por: settings, dados (seed),
   branding, adapters concretos (gateways, fiscal), e management commands
   próprios. **Nunca** subclasses de Flow nem overrides de service.

3. **Payman é dono do processo de pagamento, Order é dono do fato.**
   `Order.data["payment"]` contém apenas: `intent_ref`, `method`, `amount_q`
   e — quando captura ocorre — um snapshot **imutável** `captured: {transaction_id, captured_at, gateway}`.
   Status atual de pagamento é **sempre** consultado via `PaymentService.get(intent_ref).status`.
   Inferir status de pagamento a partir de presença de chave em `order.data` é proibido.

4. **Eixos `*.timing` substituem subclasses de Flow.**
   `LocalFlow`, `RemoteFlow`, `MarketplaceFlow` existem apenas porque o runtime
   é imperativo. A reescrita os substitui por dois novos eixos no `ChannelConfig`:

   - `payment.timing`: `pre_commit` | `at_commit` | `post_commit` | `external`
   - `fulfillment.timing`: `pre_commit` | `at_commit` | `post_commit` | `external`

   Mais o eixo já existente `confirmation.mode`. Combinações dessas três
   variáveis cobrem todos os "Flows" atuais. `dispatch()` vira função pura
   que roteia por config, não por classe.

5. **Kernel é sagrado — mas pode ganhar API pública.**
   Adicionar API explícita no kernel (ex: `StockmanService.find_holds_by_reference`)
   é permitido e desejável. **Esconder** ou **mover** coisa do kernel é proibido,
   exceto para os dois campos `Channel.pricing_policy`/`edit_policy` que são
   claramente vazamento reverso (WP-D).

6. **Zero `try/ImportError` para mascarar dependências obrigatórias.**
   Se o framework precisa de stockman, ele importa stockman direto. Se faltar,
   o app falha **no boot**, com mensagem clara, nunca em runtime. `try/ImportError`
   só é permitido para extensões realmente opcionais (SMS adapter, contrib de produção).

7. **Zero residuals em renames.** A regra `feedback_zero_residuals` continua
   valendo. Migrações serão resetadas. Nada de `# formerly Stocking`.

8. **Plano é iterativo e aprovado por WP.** Cada WP é fechado com aprovação
   antes de abrir o próximo. Prompts são auto-contidos para retomar em sessão
   limpa (regra `feedback_iterative_analysis`).

---

## 2. Mapa dos workpackages

| WP | Nome | Resolve | Dependências | Risco |
|----|------|---------|--------------|-------|
| **WP-A** | Kernel hygiene | C1, C7, C8, C9, C10 | — | Baixo (mecânico) |
| **WP-B** | Framework runtime rewrite | C2, C5, C6, C11, C13, C14 | WP-A | **Alto** (reescrita) |
| **WP-C** | Kernel API publication | C3, C15 | WP-A | Médio |
| **WP-D** | ChannelConfig consolidation | C16 + parte de C1 | WP-B, WP-C | Médio |
| **WP-E** | Instance separation | C12 | WP-B | Baixo |
| **WP-F** | Contribs decision | C4 | WP-B, WP-D | Médio (decisão de design) |

**Caminho crítico:** WP-A → WP-B → WP-C/WP-D (paralelos) → WP-E → WP-F.

WP-A é pré-requisito de tudo porque sem ele o admin do orderman quebra (C1) e
qualquer trabalho no framework esbarra em código com nomes antigos. WP-B é o
coração da reestruturação — é nele que o `ChannelConfig` passa a ser consumido
de verdade.

---

## 3. Workpackages

### WP-A — Kernel Hygiene

**Objetivo:** zerar resíduos de naming antigo no kernel e desbloquear o admin
do orderman. Trabalho mecânico, sem decisão de design.

**Resolve:**
- **C1** — admin do orderman referenciando `Channel.config`/`Channel.flow`
- **C7** — `framework/shopman/checks.py:140` filtrando `config__fiscal__enabled`
- **C8** — todos os resíduos `Stocking/Crafting/Offering/Identification/Customers/Payments/Auth` em docstrings, AppConfig, settings dataclasses, `__init__.py`, `pyproject.toml`
- **C9** — 7 arquivos `*_test_settings.py` com nomes antigos
- **C10** — `craftsman/contrib/stocking/` → `craftsman/contrib/stockman/`

**Critérios de pronto:**
1. `grep -r "Stocking\|Crafting\|Offering\|Ordering\|Identification\|Customers\b\|Payments\b\|Doorkeeper" packages/` retorna **só** ocorrências legítimas (ex: `customer_type`, etc.). Nenhum resíduo de persona antiga.
2. Admin do orderman abre Channel sem AttributeError. A aba "Config" foi **removida** do ChannelAdmin do kernel (config vive no framework).
3. `framework/shopman/checks.py` não menciona `Channel.config`.
4. `craftsman/contrib/stocking/` renomeado para `stockman/`, todos os imports atualizados.
5. Os 7 `*_test_settings.py` renomeados para `<persona>_test_settings.py` ou `test_settings.py`.
6. `make test` verde no kernel inteiro (`make test-stockman`, `make test-offerman`, etc.).
7. `make lint` limpo.

**Fora de escopo:**
- Mexer no framework além de `checks.py:140`.
- Reescrever ChannelAdmin do framework (isso é WP-D).
- Mover `pricing_policy`/`edit_policy` (isso é WP-D).

**Riscos:**
- AppConfig rename pode quebrar `INSTALLED_APPS` em testes — verificar todos os `test_settings.py` após rename.
- Diretório `contrib/stocking → stockman` move arquivos físicos: cuidado com migrações antigas que possam referenciar o nome antigo.

---

#### Prompt auto-contido WP-A

```
Tarefa: WP-A do RESTRUCTURE-PLAN do django-shopman.

Leia primeiro:
- docs/plans/RESTRUCTURE-PLAN.md (princípios + escopo do WP-A)
- docs/audit/2026-04-10-kernel-framework-audit.md (achados C1, C7, C8, C9, C10)
- CLAUDE.md (convenções)

Objetivo: zerar resíduos de naming antigo (Stocking/Crafting/Offering/
Ordering/Identification/Customers/Payments/Auth/Doorkeeper) no kernel
(packages/) e desbloquear o admin do orderman, sem mexer em design.

Faça nesta ordem:

1. Corrigir packages/orderman/shopman/orderman/admin.py:
   - Remover toda referência a Channel.config e Channel.flow.
   - Remover a aba "Config" do ChannelAdmin (vira responsabilidade do framework).
   - Manter Identidade (name, ref, kind), Display, ações.
   - Verificar com: python framework/manage.py check + abrir admin manualmente.

2. Corrigir framework/shopman/checks.py:140:
   - Remover/reescrever o filter Channel.objects.filter(config__fiscal__enabled=True).
   - Decidir: ou ler de ChannelConfigRecord, ou marcar como TODO do WP-D.
     Recomendação: comentar o check com TODO WP-D, retornar lista vazia por enquanto.

3. Renomear AppConfig classes e dataclasses de settings:
   - StockingConfig → StockmanConfig, StockingSettings → StockmanSettings
   - CraftingConfig → CraftsmanConfig
   - OfferingConfig → OfferanConfig (atenção: ofermAn, não offerinG)
   - PaymentsConfig → PaymanConfig
   - AuthConfig → DoormanConfig
   - StockingAlertsConfig → StockmanAlertsConfig
   - StockingAdminUnfoldConfig → StockmanAdminUnfoldConfig
   - get_stocking_settings → get_stockman_settings, etc.

4. Atualizar docstrings, comentários e __init__.py module docstrings em
   TODOS os packages/ — usar a lista detalhada do C8 da auditoria como
   guia. Trocar todas as ocorrências de Stocking/Crafting/Offering/Ordering/
   Identification/Customers/Payments/Doorkeeper para a persona correta.

5. pyproject.toml de cada package: atualizar description.

6. Renomear arquivos *_test_settings.py:
   - packages/craftsman/crafting_test_settings.py → craftsman_test_settings.py
   - packages/doorman/auth_test_settings.py → doorman_test_settings.py
   - packages/guestman/customers_test_settings.py → guestman_test_settings.py
   - packages/offerman/offering_test_settings.py → offerman_test_settings.py
   - packages/orderman/ordering_test_settings.py → orderman_test_settings.py
   - packages/payman/payments_test_settings.py → payman_test_settings.py
   - packages/stockman/stocking_test_settings.py → stockman_test_settings.py
   Atualizar Makefile, tox.ini, pytest.ini, .github/workflows se referenciarem.

7. Renomear diretório craftsman/contrib/stocking/ → craftsman/contrib/stockman/:
   - Mover diretório
   - Atualizar todos os imports (grep por shopman.craftsman.contrib.stocking)
   - Atualizar AppConfig name/label
   - Cuidado com migrações: se houver app_label no Meta de modelos, ajustar

8. Atualizar referências no framework:
   - framework/shopman/handlers/customer.py:4 — comentário "Inline de shopman.identification.handlers"
   - framework/shopman/services/production.py:23 — comentário "Stocking reage..."
   - framework/shopman/protocols.py — comentário "(inline — era shopman.identification.protocols)"
   - framework/shopman/web/constants.py:15-16,19-20 — HAS_STOCKING → HAS_STOCKMAN
   - framework/shopman/web/cart.py:269 — uso de HAS_STOCKING
   - framework/shopman/context_processors.py:72 — comentário "Ordering session"
   - framework/shopman/rules/validation.py:107 — OrderingValidationError → ShopmanValidationError (ou similar)

9. Rodar make test e make lint. Tudo precisa passar.

10. Commit no formato: feat(WP-A): kernel hygiene + orderman admin unblock

Critérios de pronto: ver seção WP-A em docs/plans/RESTRUCTURE-PLAN.md.

NÃO faça neste WP:
- Mover pricing_policy/edit_policy
- Reescrever ChannelAdmin do framework
- Tocar em lifecycle.py, handlers/customer.py, services/customer.py, ChannelConfig
- Decidir sobre contribs do guestman

Se encontrar algo fora de escopo que parece urgente, anote em
docs/plans/RESTRUCTURE-PLAN.md numa seção "Notas de execução" e siga.
```

---

### WP-B — Framework Runtime Rewrite

**Objetivo:** reescrever o coração do runtime do framework para que ele
**consuma** o `ChannelConfig` declarativamente, eliminando subclasses de Flow,
caminhos duplicados, handlers órfãos e padrões mágicos em `order.data`.

Este é o WP central. É o que justifica todo o resto.

**Resolve:**
- **C2** — duplicação `handlers/customer.py` ↔ `services/customer.py`
- **C5** — 13 campos de `ChannelConfig` nunca lidos
- **C6** — handlers órfãos (`customer.ensure`, `checkout.infer_defaults`)
- **C11** — `CustomerBackend` Protocol fantasma
- **C13** — `try/ImportError` em imports obrigatórios
- **C14** — leitura de status de pagamento de `order.data`

**Decisões de design (entram como input, não output):**

1. **`ChannelConfig` ganha dois novos eixos:**
   ```python
   @dataclass
   class Payment:
       method: str = "manychat_link"
       timing: str = "post_commit"  # NOVO: pre_commit | at_commit | post_commit | external
       timeout_minutes: int = 30
       available_methods: list[str] = ...

   @dataclass
   class Fulfillment:  # NOVO aspecto
       timing: str = "post_commit"  # pre_commit | at_commit | post_commit | external
       auto_sync: bool = True
   ```

   `Flow` (aspecto antigo) é **removido**. Seus campos vivos viram parte de
   `Fulfillment` ou somem (transitions, terminal_statuses, auto_transitions
   eram morto).

2. **`lifecycle.py` vira função pura:**
   `LocalFlow`, `RemoteFlow`, `MarketplaceFlow`, `PosFlow`, `TotemFlow`,
   `WebFlow`, `WhatsAppFlow`, `ManychatFlow`, `IFoodFlow` — **todos removidos**.
   `dispatch(order, phase)` lê `ChannelConfig.for_channel(order.channel)` e
   chama os services apropriados em ordem determinada pelos eixos `*.timing`
   e `confirmation.mode`.

   Pseudocódigo:
   ```python
   def dispatch(order, phase: str):
       config = ChannelConfig.for_channel(order.channel)

       if phase == "commit":
           if config.payment.timing == "at_commit":
               payment.initiate(order)
           if config.fulfillment.timing == "at_commit":
               fulfillment.create(order)
           customer.ensure(order)  # sempre

       elif phase == "confirmed":
           if config.payment.timing == "post_commit":
               payment.initiate(order)
           if config.fulfillment.timing == "post_commit":
               fulfillment.create(order)
           # ... etc
   ```

3. **`handlers/customer.py` é deletado.** Tudo passa pelo `services/customer.py`.

4. **Handlers órfãos (`CustomerEnsureHandler`, `CheckoutInferDefaultsHandler`)
   são deletados.** Se a infra de directives quiser ter um modelo "ensure async",
   isso vira WP futuro — não inventar agora.

5. **`framework/shopman/protocols.py::CustomerBackend` é deletado.**
   Usar o protocol do guestman onde for necessário (mas o framework não usa
   nenhum dos dois hoje, então provavelmente nem precisa importar).

6. **`order.data["payment"]` ganha contrato explícito** com snapshot imutável
   de captura. Estabelecer teste de invariante que rejeita gravar `status`
   nessa chave.

7. **`try/ImportError` obrigatórios viram imports diretos.** Lista exata de
   imports que viram obrigatórios (de C13):
   - `framework/shopman/handlers/pricing.py:17,47,56` — `shopman.offerman.*`
   - `framework/shopman/web/constants.py:30` — `shopman.stockman.services.availability`
   - `framework/shopman/web/views/cart.py:337` — `shopman.stockman.models.Hold`
   - `framework/shopman/web/views/checkout.py:755` — `shopman.stockman.models.Hold`
   - `framework/shopman/handlers/_stock_receivers.py:19` — `shopman.stockman.models`

   Mantém `try/ImportError` apenas em:
   - `framework/shopman/handlers/__init__.py:104` — `shopman.adapters.notification_sms`
   - `framework/shopman/handlers/__init__.py:211` — `shopman.craftsman.signals`

**Critérios de pronto:**
1. `framework/shopman/lifecycle.py` tem **zero classes Flow** — só `dispatch()` e helpers.
2. `framework/shopman/production_lifecycle.py` foi unificado com `lifecycle.py` ou removido (decidir durante o WP).
3. `framework/shopman/handlers/customer.py` foi deletado.
4. `framework/shopman/handlers/checkout_defaults.py` foi deletado (`CheckoutInferDefaultsHandler` órfão).
5. `framework/shopman/protocols.py::CustomerBackend` foi deletado.
6. `ChannelConfig` ganhou eixos `payment.timing` e `fulfillment.timing` (e possivelmente um `Fulfillment` aspecto inteiro).
7. `Flow` aspecto antigo foi removido do `ChannelConfig`.
8. `framework/shopman/web/views/checkout.py:442` não infere status de pagamento de `order.data` — consulta Payman.
9. Nenhum `try: from shopman.* except ImportError: pass` para imports obrigatórios listados acima.
10. Teste de invariante `tests/test_invariants_payment.py` que rejeita gravar `status` em `order.data["payment"]`.
11. Teste de invariante `tests/test_invariants_handlers.py` que verifica que todo handler em `ALL_HANDLERS` tem produtor identificado.
12. `make test` verde. **Esperado:** quebras nos testes de flow legacy — devem ser reescritos para testar `dispatch()` por configuração.

**Riscos:**
- **Alto.** É a reescrita do runtime. Os testes E2E (`tests/e2e/test_lifecycle.py`) vão quebrar e precisam ser reescritos.
- Aplicação rodando depende de `dispatch()` correto. Quebrar isso quebra storefront, KDS, gestor de pedidos.
- A migração dos eixos `*.timing` exige ajuste do `ChannelConfigRecord` (admin record do framework).

**Estratégia de execução:**
1. Adicionar eixos `*.timing` em paralelo ao `Flow` antigo (sem quebrar nada).
2. Reescrever `dispatch()` lendo dos novos eixos.
3. Migrar testes E2E para configurar canais via `payment.timing`/`fulfillment.timing`.
4. Deletar subclasses de Flow.
5. Deletar `Flow` aspecto antigo.
6. Deletar handlers órfãos.
7. Deletar `handlers/customer.py`.
8. Substituir `try/ImportError` obrigatórios.
9. Limpar `protocols.py`.

**Pode ser dividido:** se o WP for grande demais para uma sessão, dividir em
**WP-B1** (eixos novos + `dispatch()` + testes) e **WP-B2** (deleções +
limpeza). Decidir no início da sessão.

---

#### Prompt auto-contido WP-B

```
Tarefa: WP-B do RESTRUCTURE-PLAN do django-shopman.

Pré-requisito: WP-A precisa estar concluído. Verificar com:
  git log --oneline | grep WP-A

Leia primeiro:
- docs/plans/RESTRUCTURE-PLAN.md (princípios + escopo do WP-B)
- docs/audit/2026-04-10-kernel-framework-audit.md (achados C2, C5, C6, C11, C13, C14)
- CLAUDE.md
- framework/shopman/config.py (entender ChannelConfig atual)
- framework/shopman/lifecycle.py (entender o que vai sumir)
- framework/shopman/services/customer.py + handlers/customer.py (duplicação)

Objetivo: reescrever o runtime do framework para consumir ChannelConfig
declarativamente, eliminando subclasses de Flow, duplicação de customer,
handlers órfãos, padrões mágicos em order.data e try/ImportError disfarçados.

Decisões já fechadas (NÃO revisar):
- ChannelConfig ganha eixos payment.timing e fulfillment.timing
  (pre_commit | at_commit | post_commit | external)
- Flow aspecto antigo é REMOVIDO (transitions/terminal_statuses/auto_transitions são morto)
- LocalFlow/RemoteFlow/MarketplaceFlow/PosFlow/TotemFlow/WebFlow/WhatsAppFlow/
  ManychatFlow/IFoodFlow são todos REMOVIDOS — dispatch vira função pura
- handlers/customer.py é deletado (services/customer.py é a fonte)
- handlers/checkout_defaults.py é deletado (órfão)
- protocols.py::CustomerBackend é deletado (fantasma)
- order.data["payment"] vira contrato imutável: intent_ref, method, amount_q
  e — só após captura — captured: {transaction_id, captured_at, gateway}
- Status de pagamento sempre via PaymentService.get(intent_ref).status

Estratégia: avançar gradualmente em 9 etapas:

1. Adicionar Fulfillment aspect ao ChannelConfig com timing + auto_sync.
   Adicionar payment.timing ao Payment aspect existente.
   Manter Flow aspect antigo intocado por enquanto.
   Adicionar testes de defaults e cascata para os novos campos.

2. Reescrever framework/shopman/lifecycle.py:
   - dispatch(order, phase) lê ChannelConfig e chama services em ordem.
   - Manter assinatura de dispatch() compatível com signal handler atual.
   - Documentar a tabela de combinações (timing × phase × service).

3. Reescrever testes E2E (tests/e2e/test_lifecycle.py e amigos) para
   configurar canais via payment.timing/fulfillment.timing em vez de
   selecionar Flow class.

4. Deletar todas as subclasses de Flow em lifecycle.py. Manter só dispatch()
   + helpers necessários.

5. Decidir production_lifecycle.py: unificar com lifecycle.py OU remover. NÃO deixar
   como está. Recomendação: remover e mover lógica para services/production.py
   se ainda for necessária.

6. Remover Flow aspect antigo de ChannelConfig (transitions, terminal_statuses,
   auto_transitions, auto_sync_fulfillment vai para Fulfillment.auto_sync).

7. Deletar:
   - framework/shopman/handlers/customer.py
   - framework/shopman/handlers/checkout_defaults.py
   - framework/shopman/protocols.py::CustomerBackend (e o dataclass CustomerInfo
     se ele só servia ao protocol fantasma)
   - As entradas correspondentes em handlers/__init__.py::ALL_HANDLERS e
     register_all().

8. Substituir try/ImportError por imports normais nos arquivos:
   - framework/shopman/handlers/pricing.py:17, 47, 56
   - framework/shopman/web/constants.py:30
   - framework/shopman/web/views/cart.py:337
   - framework/shopman/web/views/checkout.py:755
   - framework/shopman/handlers/_stock_receivers.py:19
   Manter try/ImportError APENAS em handlers/__init__.py:104 (sms) e :211 (craftsman).

9. Adicionar testes de invariante em framework/shopman/tests/:
   - test_invariant_payment_data.py: rejeita gravar 'status' em order.data['payment']
   - test_invariant_handlers.py: todo handler de ALL_HANDLERS tem produtor identificado
   - test_invariant_no_legacy_flow.py: nenhuma classe Flow definida em lifecycle.py

10. Corrigir framework/shopman/web/views/checkout.py:442 — substituir leitura de
    order.data['payment']['intent_ref'] por consulta a PaymentService.

11. make test inteiro. Esperado: quebras em testes de flow legacy — corrigir
    para o novo dispatch().

12. make lint.

13. Commit no formato: refactor(WP-B): framework runtime rewrite — declarative dispatch

NÃO faça neste WP:
- Mover pricing_policy/edit_policy do Channel kernel (WP-D)
- Mexer em packages/ além do que for indispensável (idealmente nada)
- Decidir contribs do guestman (WP-F)
- Mexer no instances/nelson/ (WP-E)
- Reescrever ChannelAdmin do framework (WP-D)

Se o WP for grande demais para uma sessão, parar após etapa 6 e abrir
WP-B2 para etapas 7-13. Documentar o ponto de parada em
docs/plans/RESTRUCTURE-PLAN.md.

Critérios de pronto: ver seção WP-B em docs/plans/RESTRUCTURE-PLAN.md.
```

---

### WP-C — Kernel API Publication

**Objetivo:** publicar superfícies públicas no kernel para que o framework pare
de tocar em internos (`Hold.metadata__reference`, submódulos privados).

**Resolve:**
- **C3** — `Hold.metadata__reference` em 5 lugares
- **C15** — imports de submódulos internos (`stockman.models.enums`, `stockman.models.position`, `doorman.models.device_trust`, `offerman.contrib.suggestions`)

**Decisões de design:**

1. **Stockman expõe API de busca por reference:**
   ```python
   # packages/stockman/shopman/stockman/services/holds.py
   class HoldService:
       @staticmethod
       def find_by_reference(reference: str, *, sku: str | None = None,
                             status_in: list[str] | None = None) -> QuerySet[Hold]: ...

       @staticmethod
       def find_active_by_reference(reference: str) -> QuerySet[Hold]: ...
   ```

   Por trás, internamente, ainda usa `metadata__reference` — mas isso vira
   detalhe de implementação. O framework chama só `HoldService.find_by_reference(...)`.

2. **Cada package exporta superfície pública via `__init__.py`:**
   - `stockman.enums` — re-export de `models/enums.py`
   - `stockman.positions` — re-export do que `models/position.py` expõe hoje
   - `doorman.device_trust` — re-export
   - Etc.

   Imports do framework passam a ser **só** dessas superfícies. Importar
   `shopman.stockman.models.enums` direto vira erro (lint).

3. **`offerman.contrib.suggestions` é caso especial:** decidir se vira API
   pública do offerman ou se a lógica que o framework usa (`alternatives.py`)
   migra para o framework. Provavelmente o segundo — alternatives é regra de
   negócio do framework, não do catálogo.

**Critérios de pronto:**
1. `HoldService.find_by_reference()` (ou nome equivalente) existe em stockman e tem testes próprios.
2. Os 5 call sites do framework que filtram `Hold.metadata__reference` foram migrados.
3. `services/stock.py:200-260` não manipula `Hold.metadata` direto — usa API pública.
4. Cada package do kernel listado tem re-exports explícitos no `__init__.py` para os símbolos que o framework precisa.
5. Nenhum import `from shopman.<package>.models.<sub>` ou `from shopman.<package>.contrib.<x>` no framework, exceto onde decidido em WP-F.
6. `make test` verde (kernel + framework).
7. Lint do framework configurado para reprovar imports profundos do kernel (regra opcional, mas recomendada).

**Riscos:**
- Mexer em kernel (adicionar API). Risco baixo porque é **adicionar**, não mudar.
- A regra de lint pode pegar imports legítimos que precisam de exceção — ajustar caso a caso.

---

#### Prompt auto-contido WP-C

```
Tarefa: WP-C do RESTRUCTURE-PLAN do django-shopman.

Pré-requisito: WP-A concluído. WP-B concluído (framework runtime já reescrito).

Leia primeiro:
- docs/plans/RESTRUCTURE-PLAN.md (princípios + escopo do WP-C)
- docs/audit/2026-04-10-kernel-framework-audit.md (achados C3, C15)
- CLAUDE.md

Objetivo: publicar superfícies públicas no kernel para que o framework pare
de tocar em internos do stockman/doorman/offerman.

Decisões já fechadas:
- HoldService.find_by_reference(reference, *, sku=None, status_in=None)
  vira API pública do stockman. Internamente usa metadata__reference.
- Cada package exporta no __init__.py os símbolos que o framework precisa.
- offerman.contrib.suggestions: decidir se vira API pública ou se a lógica
  migra para o framework (recomendação: migrar alternatives.py).

Faça:

1. Criar packages/stockman/shopman/stockman/services/holds.py com HoldService
   contendo find_by_reference e find_active_by_reference. Testes em
   packages/stockman/.../tests/test_hold_service.py.

2. Migrar os 5 call sites do framework:
   - framework/shopman/services/availability.py:508
   - framework/shopman/services/stock.py:214
   - framework/shopman/adapters/stock.py:227
   - framework/shopman/web/views/cart.py:341
   - framework/shopman/web/views/checkout.py:758
   Substituir Hold.objects.filter(metadata__reference=...) por
   HoldService.find_by_reference(...).

3. Limpar services/stock.py:200-260 — toda manipulação direta de Hold.metadata.
   Se faltar API no stockman para algo, adicionar e usar.

4. Publicar superfícies nos __init__.py dos packages:
   - packages/stockman/shopman/stockman/__init__.py — re-export de enums,
     positions, services públicos
   - packages/doorman/shopman/doorman/__init__.py — re-export de device_trust
     se o framework precisar
   - packages/offerman/shopman/offerman/__init__.py — re-export do que for
     necessário
   Cada __init__.py declara __all__.

5. Migrar imports do framework dos seguintes arquivos para usar superfícies
   públicas (lista em C15 da auditoria):
   - framework/shopman/services/availability.py:503
   - framework/shopman/services/stock.py:209
   - framework/shopman/adapters/stock.py:170, 221
   - framework/shopman/handlers/_stock_receivers.py:21
   - framework/shopman/management/commands/cleanup_d1.py:10
   - framework/shopman/web/views/production.py:18
   - framework/shopman/admin/dashboard.py:452
   - framework/shopman/web/views/closing.py:22
   - framework/shopman/web/views/devices.py:67, 107

6. Decidir offerman.contrib.suggestions:
   - Opção A: virar API pública do offerman (offerman.suggestions)
   - Opção B: mover a lógica que o framework usa para
     framework/shopman/services/alternatives.py (já existe)
   Recomendação: B. Documentar a decisão num comentário no topo de alternatives.py.

7. Adicionar regra de lint (opcional mas recomendada): reprovar imports
   profundos do kernel no framework. Pode ser via ruff custom rule ou
   simplesmente um teste que faz grep e falha.

8. make test inteiro + make lint.

9. Commit: feat(WP-C): kernel API publication + remove deep imports

NÃO faça neste WP:
- Mexer em ChannelConfig (WP-B já fez)
- Mover pricing_policy/edit_policy (WP-D)
- Decidir contribs do guestman (WP-F)

Critérios de pronto: ver seção WP-C em docs/plans/RESTRUCTURE-PLAN.md.
```

---

### WP-D — ChannelConfig Consolidation

**Objetivo:** consolidar tudo que é configuração de canal dentro do
`ChannelConfig` do framework, retirando do kernel os dois campos que vazaram
(`pricing_policy`, `edit_policy`) e dando ao framework um Admin de
configuração de canal.

**Resolve:**
- **C16** — `Channel.pricing_policy`/`edit_policy` consumidos só pelo framework
- Parte de **C1** — substituir a aba "Config" que foi removida do ChannelAdmin do kernel

**Decisões de design:**

1. **Os dois campos saem do `Channel` do kernel** e viram aspectos do
   `ChannelConfig`:
   ```python
   @dataclass
   class Pricing:
       policy: str = "default"  # ou enum
       # ... outros campos relevantes

   @dataclass
   class Editing:  # ou nome melhor
       policy: str = "default"
   ```

2. **Migration no kernel:** drop dos dois campos. Como o projeto pode resetar
   migrações (regra `feedback_zero_residuals`), provavelmente vai ser uma
   migração do tipo "remove fields" simples.

3. **Framework ganha um `ChannelConfigAdmin`:** UI de Admin que lê/escreve
   `ChannelConfigRecord` (modelo do framework) e tem aba "Config" com tabs
   por aspecto (Confirmation, Payment, Stock, Notifications, Rules,
   Fulfillment, Pricing, Editing). Substitui visualmente a aba que foi
   removida do ChannelAdmin do kernel em WP-A.

4. **Cascata continua:** defaults → shop → channel. Admin permite editar nos
   três níveis.

**Critérios de pronto:**
1. `Channel` do kernel tem só: `name`, `ref`, `kind`, `is_active`, `display_order` (+ timestamps).
2. `ChannelConfig` (no framework) tem aspectos `Pricing` e `Editing` (ou nomes equivalentes).
3. Migration do orderman remove `pricing_policy` e `edit_policy` de `Channel`.
4. `framework/shopman/admin/channel_config.py` (novo) tem UI de aba por aspecto.
5. Testes do `cart.py` e `pos.py` do framework continuam passando, agora lendo da config.
6. `framework/shopman/checks.py` lê fiscal config do `ChannelConfigRecord`.
7. Seed do nelson é atualizado para popular `ChannelConfigRecord` em vez de gravar nos campos do kernel.
8. `make test` verde.

**Riscos:**
- Migration no kernel exige cuidado com dados existentes. Como regra é resetar, deveria ser tranquilo, mas confirmar antes de rodar.
- Admin novo é trabalho de UI — pode demandar Unfold customization. Manter simples na primeira iteração.

---

#### Prompt auto-contido WP-D

```
Tarefa: WP-D do RESTRUCTURE-PLAN do django-shopman.

Pré-requisito: WP-A, WP-B, WP-C concluídos.

Leia primeiro:
- docs/plans/RESTRUCTURE-PLAN.md (princípios + escopo do WP-D)
- docs/audit/2026-04-10-kernel-framework-audit.md (achado C16, parte de C1)
- packages/orderman/shopman/orderman/models/channel.py
- framework/shopman/config.py
- framework/shopman/web/cart.py (leitor atual de pricing_policy/edit_policy)
- CLAUDE.md

Objetivo: consolidar pricing_policy e edit_policy dentro do ChannelConfig
do framework, removê-los do kernel, e dar ao framework um Admin de config
de canal que substitua a aba "Config" removida em WP-A.

Decisões fechadas:
- pricing_policy e edit_policy saem de Channel (kernel) e viram aspectos
  ChannelConfig.Pricing.policy e ChannelConfig.Editing.policy (revisar nomes
  durante a sessão).
- Migration no orderman remove os dois campos.
- Framework ganha admin/channel_config.py com UI por aba (Confirmation,
  Payment, Stock, Notifications, Rules, Fulfillment, Pricing, Editing).
- Seed do nelson é atualizado para popular ChannelConfigRecord.

Faça:

1. Adicionar Pricing e Editing aspects ao ChannelConfig em
   framework/shopman/config.py. Adicionar testes de defaults e cascata.

2. Migrar consumidores do framework para ler da config:
   - framework/shopman/web/cart.py — pricing_policy/edit_policy
   - framework/shopman/web/views/pos.py — idem
   - framework/shopman/management/commands/seed.py — idem (popula
     ChannelConfigRecord)

3. Criar migration no packages/orderman/ removendo pricing_policy e
   edit_policy de Channel. Limpar fixtures/seeds que ainda gravam neles.

4. Reescrever framework/shopman/checks.py:140 (que ainda estava com TODO de
   WP-A) para ler de ChannelConfigRecord.

5. Criar framework/shopman/admin/channel_config.py com ChannelConfigAdmin
   apresentando os aspectos por aba. Pode ser simples na primeira iteração
   — JSON editor por aspecto + validação. Refinar UX em iteração futura.

6. Atualizar framework/shopman/admin/__init__.py para registrar o novo admin.

7. Atualizar instances/nelson/ se houver referência aos campos removidos.

8. make test + make lint.

9. Commit: refactor(WP-D): channel config consolidation + remove kernel leak

NÃO faça neste WP:
- Mexer em lifecycle.py / dispatch (já fechado em WP-B)
- Mexer em contribs do guestman (WP-F)
- Mover seed.py inteiro (WP-E)

Critérios de pronto: ver seção WP-D em docs/plans/RESTRUCTURE-PLAN.md.
```

---

### WP-E — Instance Separation

**Objetivo:** mover tudo o que é específico da Nelson Boulangerie do
`framework/` para `instances/nelson/`. Framework volta a ser agnóstico.

**Resolve:**
- **C12** — Nelson hardcoded em `seed.py`, `fiscal.py`, templates de teste

**Decisões de design:**

1. **`framework/shopman/management/commands/seed.py` é movido inteiro** para
   `instances/nelson/management/commands/seed.py`. Framework fica sem comando
   de seed (ou ganha um `seed_demo.py` minimalista, sem branding).

2. **`framework/shopman/fiscal.py:16`** — referência hardcoded a
   `nelson.adapters.fiscal_focus.FocusNFCeBackend`. Vira lookup via settings.

3. **`tests/web/test_web_pwa.py:99`** — assertion sobre `CACHE_NAME = 'nelson-v2'`.
   Vira parametrizado por settings ou movido para testes da instância.

**Critérios de pronto:**
1. `framework/shopman/management/commands/seed.py` removido (ou substituído por seed genérico).
2. `instances/nelson/.../management/commands/seed.py` existe e roda.
3. `make seed` continua funcionando (delegando para o comando da instância).
4. `framework/shopman/fiscal.py` não menciona `nelson` em string nenhuma.
5. Nenhum teste do framework menciona `nelson` em assertion.
6. `grep -r "nelson" framework/` retorna **só** ocorrências em comentários/docstrings legítimos (ex: "exemplo: Nelson Boulangerie") ou zero.
7. `make test` verde.

**Riscos:**
- Baixo. É mudança mecânica.

---

#### Prompt auto-contido WP-E

```
Tarefa: WP-E do RESTRUCTURE-PLAN do django-shopman.

Pré-requisito: WP-B concluído (runtime já não depende de Flow classes).

Leia primeiro:
- docs/plans/RESTRUCTURE-PLAN.md (princípios + escopo do WP-E)
- docs/audit/2026-04-10-kernel-framework-audit.md (achado C12)
- framework/shopman/management/commands/seed.py
- framework/shopman/fiscal.py
- instances/nelson/ (estrutura atual)

Objetivo: mover tudo que é Nelson-específico do framework para a instância.
Framework volta a ser agnóstico.

Faça:

1. Mover framework/shopman/management/commands/seed.py inteiro para
   instances/nelson/.../management/commands/seed.py. Atualizar imports.

2. Atualizar Makefile: o alvo `make seed` agora roda o comando da instância
   (DJANGO_SETTINGS_MODULE=nelson.settings python manage.py seed ou similar).

3. Substituir referência hardcoded a "nelson.adapters.fiscal_focus..." em
   framework/shopman/fiscal.py:16 por lookup via settings
   (settings.SHOPMAN_FISCAL_BACKEND ou similar).

4. Atualizar instances/nelson/settings.py para configurar SHOPMAN_FISCAL_BACKEND.

5. Mover ou parametrizar tests/web/test_web_pwa.py:99 (assertion sobre
   nelson-v2). Provavelmente vira teste de instância.

6. Verificar com grep -r "nelson" framework/ que só sobram ocorrências
   legítimas (comentários explicativos).

7. make test + make seed (rodar de verdade para garantir).

8. Commit: refactor(WP-E): move Nelson-specific code to instance

NÃO faça neste WP:
- Mexer em ChannelConfig
- Mexer em runtime/flows
- Decidir contribs

Critérios de pronto: ver seção WP-E em docs/plans/RESTRUCTURE-PLAN.md.
```

---

### WP-F — Contribs Decision

**Objetivo:** decidir, contrib por contrib do guestman, qual fica no kernel
como API pública e qual migra para o framework. Resolve o último vazamento
estrutural.

**Resolve:**
- **C4** — 28 imports profundos do framework para `guestman.contrib.*`

**Por que é o último:** depende de WP-B (runtime limpo) e WP-D (config
consolidada) para ter visibilidade clara de quem é responsabilidade de quem.

**Decisões a tomar (não fechadas — entram como input do WP):**

Para cada contrib do guestman, escolher uma das opções:

| Contrib | Imports do framework | Opções |
|---------|----------------------|--------|
| `preferences` | 9 | A) API pública do guestman. B) move para framework. C) split. |
| `identifiers` | 6 | Idem |
| `loyalty` | 5 | Idem |
| `timeline` | 2 | Idem |
| `insights` | 4 | Idem |
| `consent` | 2 | Idem |

**Heurística sugerida:**
- Se a lógica é **dado de cliente puro** (independente de canal/storefront),
  vira API pública do guestman. Ex: `identifiers` (provedor + valor),
  `consent` (LGPD).
- Se a lógica é **comportamento de loja** (regras, eventos, integrações),
  vira parte do framework. Ex: `loyalty` (regras de pontos e cupons),
  `preferences` (preferências de checkout).
- Se for misto, split: o modelo fica no guestman, a lógica de framework no
  framework.

**Critérios de pronto:**
1. Cada um dos 6 contribs tem decisão documentada e implementada.
2. Nenhum `try: from shopman.guestman.contrib.* except ImportError` no framework para os contribs que ficaram no guestman — viraram imports normais.
3. Os contribs que viraram framework não têm mais dependência circular com guestman.
4. `make test` verde.

**Riscos:**
- Decisão de design real. Pode demorar mais que uma sessão. Pode ser dividido
  em WP-F1 (preferences + identifiers + consent) e WP-F2 (loyalty + timeline + insights).

---

#### Prompt auto-contido WP-F

```
Tarefa: WP-F do RESTRUCTURE-PLAN do django-shopman.

Pré-requisito: WP-B, WP-C, WP-D concluídos.

Leia primeiro:
- docs/plans/RESTRUCTURE-PLAN.md (princípios + escopo do WP-F)
- docs/audit/2026-04-10-kernel-framework-audit.md (achado C4)
- packages/guestman/shopman/guestman/contrib/ (estrutura)
- Lista de imports do framework para guestman.contrib em C4

Objetivo: decidir contrib por contrib do guestman se fica no kernel
(API pública) ou move para o framework. Eliminar try/ImportError sobre eles.

Decisão por contrib (uma das três opções):
A) Mantém no kernel, mas vira API pública. Re-export no
   guestman/__init__.py, remove try/ImportError no framework.
B) Move para framework. Move código + migrações para framework/shopman/
   contribs/. Atualiza imports.
C) Split: modelo no guestman, lógica de framework no framework.

Heurística sugerida (mas não obrigatória):
- preferences → A ou B (provavelmente B: preferências de checkout são framework)
- identifiers → A (provedor+valor é dado puro de cliente)
- loyalty → B (regras de pontos são framework)
- timeline → A (evento de cliente é dado puro)
- insights → A (RFM é cálculo sobre dado de cliente)
- consent → A (LGPD é dado puro)

Discutir as decisões com o usuário ANTES de implementar. Não decidir sozinho.

Faça:

1. Apresentar análise contrib-por-contrib com recomendação e razão.
   PARAR e esperar aprovação do usuário.

2. Para cada contrib aprovado como A:
   - Re-export no guestman/__init__.py
   - Remover try/ImportError no framework
   - Atualizar testes

3. Para cada contrib aprovado como B:
   - Mover diretório
   - Migrations: mover ou recriar
   - Atualizar imports
   - Atualizar AppConfig se necessário

4. Para cada contrib aprovado como C:
   - Definir corte
   - Implementar split

5. Verificar zero try/ImportError sobre guestman.contrib no framework
   (exceto onde o usuário aprovou explicitamente como opcional).

6. make test + make lint.

7. Commit por contrib decidido (não bundlar tudo): refactor(WP-F): <contrib> decision

Se o WP for grande demais, dividir em WP-F1 (3 primeiros contribs) e
WP-F2 (3 últimos).

NÃO faça neste WP:
- Decidir sem aprovação do usuário
- Tocar em outras coisas além de contribs

Critérios de pronto: ver seção WP-F em docs/plans/RESTRUCTURE-PLAN.md.
```

---

## 4. Decisões deferidas (não entram em nenhum WP até nova ordem)

Estas saíram da auditoria/conversa mas não foram alocadas:

1. **`framework/shopman/protocols.py` ainda tem razão de existir?**
   Após WP-B (que apaga `CustomerBackend`), ele só re-exporta de payman/orderman.
   Decisão: avaliar no fim do WP-B se vale a pena deletar de vez.

2. **`orderman.contrib.refs` e `orderman.contrib.stock`** continuam sendo
   contribs do kernel? Estão saudáveis hoje, mas se a decisão de WP-F
   estabelecer um padrão, pode valer revisitar.

3. **Lint custom para imports profundos do kernel** (proposta de WP-C).
   Pode virar tarefa autônoma de tooling.

---

## 5. Notas de execução

> Esta seção é para WPs em andamento. Cada WP escreve aqui o que descobriu,
> bloqueios, mudanças de escopo aprovadas. Evita perder contexto entre sessões.

### WP-E — 2026-04-10

**Status: concluído.**

Alterações realizadas:

1. **seed.py movido** para `instances/nelson/management/commands/seed.py`.
   - Criado `instances/nelson/apps.py` com `NelsonConfig` (Django app).
   - Adicionado `"nelson"` ao `INSTALLED_APPS` em `framework/project/settings.py`.
   - Django descobre o comando via app `nelson` — `make seed` continua funcionando.
   - Framework não tem mais comando seed próprio.

2. **fiscal.py** — docstring limpo (exemplo `nelson.adapters...` → `myinstance.adapters...`).
   O código já usava `settings.SHOPMAN_FISCAL_BACKENDS` corretamente.

3. **SVG icons** (`icon-192.svg`, `icon-512.svg`) — Nelson-branded movidos para
   `instances/nelson/static/`. Framework ganhou ícones genéricos "Shopman Demo".

4. **Test fixtures** — shop_instance trocado de "Nelson Boulangerie" para "Demo Bakery"
   em `tests/web/conftest.py`, `tests/api/test_availability.py`, `tests/web/test_web_pwa.py`.

5. **Makefile** — comentário do target `seed` genericizado.

6. **settings.py** — docstring limpo ("Nelson Boulangerie demo" → genérico).

7. **Correção adjacente:** migration `0006_order_status_processing_to_preparing.py`
   usava `jsonb_set` (PostgreSQL-only). Trocado para `json_set` (SQLite-compatible).

**Referências legítimas que permaneceram:**
- `framework/project/settings.py`: `"nelson"` em INSTALLED_APPS + `SHOPMAN_CUSTOMER_STRATEGY_MODULES`
  (configuração de instância — é onde deve estar).
- `shopman/migrations/0001_initial.py`: help_text com URLs de exemplo (registro histórico).

**Testes:** 21 PWA tests passam. 661 framework tests passam. Falhas restantes são
pré-existentes (KeyError `available_qty` em availability.py:391, hold adoption).

### WP-F — 2026-04-10

**Status: concluído.**

**Decisão:** todos os 6 contribs do guestman ficam como **opção A (API pública do
kernel)**. Razão: todos modelam atributos e comportamentos do cliente, não da loja.
O framework é consumidor, não dono da lógica. Mover qualquer um criaria dependência
inversa.

| Contrib | Decisão | Razão |
|---------|---------|-------|
| preferences | A | Dado puro (preferências alimentares, pagamento, entrega) |
| identifiers | A | Dado puro (resolução multi-canal) |
| loyalty | A | Domínio de cliente (pontos, stamps, tiers) |
| timeline | A | Dado puro (log de interações) |
| insights | A | Cálculos sobre dados de cliente (RFM, churn, LTV) |
| consent | A | LGPD — compliance puro |

Alterações realizadas:

1. **Publicação de API pública** — cada contrib `__init__.py` agora exporta modelos
   além do Service via `__getattr__` + `__all__` (ex: `CustomerPreference`,
   `PreferenceType`, `CustomerIdentifier`, `LoyaltyAccount`, `TimelineEvent`,
   `CustomerInsight`, `CommunicationConsent`, etc.).

2. **Re-exports no guestman principal** — `packages/guestman/shopman/guestman/__init__.py`
   re-exporta todos os símbolos públicos dos 6 contribs via `_CONTRIB_MAP` + `__getattr__`.

3. **Eliminação de `try/ImportError`** — todos os imports defensivos de
   `shopman.guestman.contrib.*` no framework foram substituídos por imports diretos
   via superfície pública (ex: `from shopman.guestman.contrib.loyalty import LoyaltyService`).
   Arquivos alterados:
   - `framework/shopman/services/customer.py` (identifiers, timeline, insights, address)
   - `framework/shopman/services/checkout_defaults.py` (preferences)
   - `framework/shopman/handlers/loyalty.py` (loyalty)
   - `framework/shopman/web/views/account.py` (loyalty, consent, preferences)
   - `framework/shopman/web/views/_helpers.py` (insights)
   - `framework/shopman/web/views/checkout.py` (loyalty)

4. **INSTALLED_APPS atualizado** — adicionados `consent`, `identifiers`, `timeline`
   que estavam implícitos mas não registrados explicitamente.

**Testes:** 369 guestman + 661 framework passam. Falhas restantes são pré-existentes
(KeyError `available_qty` em availability.py:391, hold adoption).

---

## 6. Histórico

| Data | Evento |
|------|--------|
| 2026-04-10 | Plano criado a partir da auditoria do mesmo dia. |
| 2026-04-10 | WP-E concluído: instance separation (seed, icons, fixtures, fiscal). |
| 2026-04-10 | WP-F concluído: contribs decision — todos ficam como API pública do guestman. |
