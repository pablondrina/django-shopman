# Análise Profunda v3d — Django Shopman Orquestrador + Apresentação

Data: 2026-04-21
Base: estado pós-split (shop/storefront/backstage) + SPLIT-HARDENING-PLAN pendente
Autor: Dispatch (agente Cowork)
Versão: v3d — round final após análise cruzada entre dispatch_v2 e externo_v2

---

## Nota de método

Esta versão resulta da análise cruzada entre:

- **dispatch_v2** — minha análise, baseada em 5 agentes paralelos + síntese + autocrítica + incorporação seletiva da v1 externa
- **externo_v2** — análise independente, baseada em varredura estrutural + leitura de hotspots + tentativa de execução de testes

Para esta v3d, reli ambas com olhar frio, verifiquei claims controversas no código, e reorganizei o documento em torno do que realmente importa: **o que fazer para elevar o orquestrador e as superfícies ao nível dos kernels**.

As seções marcadas com:
- ✓ = verificado no código nesta rodada
- △ = parcialmente correto (claim ajustada)
- ✗ = incorreto ou exagerado (removido/corrigido)

---

## O padrão dos kernels — a régua certa

Ambas as análises concordam no que torna os kernels maduros. Mas nenhuma definiu a régua com precisão suficiente para ser usada como checklist. Aqui está:

Um pacote do kernel é maduro porque combina **cinco propriedades ao mesmo tempo**:

1. **Dono nítido** — cada modelo, service e invariante tem exatamente um lugar onde mora. Não há ambiguidade.
2. **Contrato explícito** — a superfície pública é pequena e tipada. `CommitService` recebe `channel_ref + session_key`, retorna `Order`. `PaymentBackend` define `create_intent() → PaymentIntent`.
3. **Invariante testável** — regras de negócio são enforçadas por testes que expressam a invariante, não o implementation detail. Ex: `test_commit_fails_if_session_empty`, `test_hold_prevents_double_reservation`.
4. **Resultado formal** — operações retornam DTOs tipados: `PaymentResult`, `NotificationResult`, `CaptureResult`, `RefundResult`. Nunca dict ad hoc, nunca mutação silenciosa.
5. **Degradação previsível** — exceções são tipadas (`CommitError`, `InvalidTransition`), com `code` + `context`. O chamador sabe exatamente o que falhou e por quê.

A pergunta então é: **onde o orquestrador e as superfícies falham em cada uma dessas cinco propriedades?**

---

## 1. Dono nítido — o split ainda é topológico

### 1.1 ✓ Templates e statics duplicados — shadowing silencioso

76 templates + 13 statics existem tanto em `shop/` quanto nas superfícies. `APP_DIRS=True` + `shop` antes em `INSTALLED_APPS` (config/settings.py L114-118) → Django resolve do shop, não da superfície.

Isso é o problema mais perigoso do split. Não por ser difícil de resolver — por criar **falsa certeza**. Um dev edita `storefront/templates/storefront/checkout.html` achando que é o arquivo em uso. Não é. O de `shop/templates/storefront/checkout.html` ganha.

**Status:** WP-H1 do SPLIT-HARDENING-PLAN. ~84 arquivos a deletar. Baixa complexidade.

### 1.2 ✓ Imports diretos shop→backstage sem adapter

10 imports de `shopman.backstage.models` em 6 arquivos de produção de `shop/`. Os adapters KDS (`kds.py`) e Alert (`alert.py`) foram planejados no split mas nunca criados. O adapter `promotion.py` existe e funciona como referência.

**Status:** WP-H2. 2 adapters novos + 7 arquivos editados. Média complexidade.

### 1.3 ✓ Docstrings e loggers referenciam `shopman.shop.web` (morto)

33 referências a `shopman.shop.web` em 21 arquivos — incluindo 4 loggers de produção em storefront/views que escrevem sob namespace inexistente. Logs silenciosamente roteaveis para lugar nenhum dependendo da config.

**Status:** WP-H3. Baixa complexidade.

### 1.4 ✓ Guardrails não cobrem o perímetro do split

`test_no_deep_kernel_imports.py` usa `FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent` → escaneia apenas `shopman/shop/`. Storefront e backstage estão fora da cerca.

A externo_v2 formulou isso da forma mais precisa: **"Falsa confiança é mais perigosa que ausência explícita de teste."**

**Status:** WP-H4. 4 novos testes. Depende de WP-H2.

### 1.5 △ shop/omotenashi/ é duplicata de storefront/omotenashi/

A externo_v1 reportou este achado. Verificação: `shop/omotenashi/` existe e contém `context.py` e `copy.py`. Preciso verificar se são idênticos ou se divergiram.

✓ **Verificação adicional necessária:** Este resíduo não foi capturado pelo SPLIT-HARDENING-PLAN. Se forem idênticos, `shop/omotenashi/` deve ser deletado no WP-H1. Se divergiram, o de `storefront/` é canônico.

### 1.6 △ "Shop governa demais" — diagnóstico parcialmente correto

Ambas as análises notam que `shop/apps.py` (169L) faz boot de handlers, rules, lifecycle, production lifecycle, nutrition, ref types. Storefront e backstage têm AppConfig vazios.

**Diagnóstico ajustado:** Isso é **parcialmente correto como design**. Shop é orquestrador — registrar handlers e rules transversais no boot É sua responsabilidade. O problema não é que shop faz boot demais; é que:

a) Resíduos dão a impressão de que shop ainda é dono de tudo (templates, statics, omotenashi duplicados)
b) Falta enforcement automatizado da regra de dependência — qualquer dev pode importar `backstage.models` direto

Resolver (a) via WP-H1 e (b) via WP-H4 elimina a ambiguidade sem precisar redistribuir boot que legitimamente pertence ao orquestrador.

---

## 2. Contrato explícito — onde a superfície pública é vaga

### 2.1 ✓ Lifecycle dispatch retorna None — sem contrato de resultado

```python
def dispatch(order, phase: str) -> None:
```

`dispatch()` retorna `None`. Cada phase handler (`_on_commit`, `_on_confirmed`, etc.) também retorna `None`. Se `stock.hold()` funciona mas `notification.send()` falha, o chamador não sabe — a exceção propaga, mas não há registro de "o que deu certo antes da falha".

Compare com o kernel: `CommitService.commit()` retorna `Order`, `PaymentBackend.capture()` retorna `PaymentResult(success, transaction_id, error_code)`.

**Proposta:** `LifecyclePhaseResult` dataclass:

```python
@dataclass(frozen=True)
class LifecyclePhaseResult:
    phase: str
    order_ref: str
    actions_completed: list[str]   # ["customer.ensure", "stock.hold", "loyalty.redeem"]
    actions_failed: list[str]      # ["notification.send"]
    error: str | None = None
```

Não é overengineering — é o mesmo padrão que `PaymentResult`, `NotificationResult`, `ReturnResult` já usam no projeto. O lifecycle é o único componente central sem resultado tipado.

### 2.2 ✓ Services retornam de formas inconsistentes

Verificado em `protocols.py` e adapters: o projeto já tem `PaymentResult`, `NotificationResult`, `CaptureResult`, `RefundResult`, `ReverseGeocodeResult`, `ReturnResult`. Mas os services orquestradores (`stock.hold`, `fulfillment.create`, `customer.ensure`) não seguem esse padrão — retornam None ou mutam order in-place.

A externo_v2 propunha resultado formal por caso de uso (`ok`, `rejected`, `pending`, `partial`, `failed`, `redirect`). A dispatch_v2 propunha `WorkflowResult`. Ambas identificaram o problema. A solução correta é **mais restrita**: não um tipo genérico para tudo, mas **cada service deve retornar seu próprio result DTO**, como os adapters já fazem.

**Proposta:** Estender o padrão existente — `StockHoldResult`, `FulfillmentResult`, etc. O lifecycle agrega os resultados dos services em `LifecyclePhaseResult`.

### 2.3 ✓ commitment_snapshot existe no kernel — mas não é visível nas superfícies

A dispatch_v2 propunha `OrderCommitment` como falha fundamental ("o sistema não tem conceito de promessa ao cliente"). A externo_v2 corrigiu isso com line numbers:

```python
# commit.py L255-258, L313-318
commitment_snapshot = CommitService._build_commitment_snapshot(...)
order = Order.objects.create(
    snapshot={"commitment": commitment_snapshot, ...}
)
```

O commitment JÁ EXISTE no kernel. O que falta é que as superfícies não o usam. Nenhuma view de tracking mostra "o que foi prometido vs. o que aconteceu". Nenhum operador vê o commitment ao decidir sobre uma reclamação.

**Proposta ajustada:** Não criar novo modelo. Criar projection:
- `storefront/projections/order_commitment.py` — extrai commitment do snapshot, compara com estado atual
- Usar em order tracking ("prometido: 14h-15h, entregue: 15:20") e em backstage ("cliente esperava X, entregou-se Y")

Isso eleva um conceito que o kernel já implementou ao nível das superfícies — exatamente o tipo de trabalho que fecha a distância de maturidade.

### 2.4 ✓ ChannelConfig define comportamento, mas não capabilities

`ChannelConfig` (config.py) tem 8 aspectos: confirmation, payment, fulfillment, stock, notifications, pricing, editing, rules. Todos definem **como** o lifecycle processa.

Falta o complemento: **o que a superfície do canal pode fazer**. Hoje, para saber se um canal suporta catálogo browseable, checkout completo, tracking, push notification, ou reorder, é preciso ler views e templates. Não há declaração.

Ambas as análises convergem aqui. A dispatch_v2 propunha `ChannelCapabilities` dataclass. A externo_v2 descreve o mesmo conceito. Mas nenhuma verificou se o padrão existente acomoda isso.

**Verificação:** `ChannelConfig` é um dataclass com nested dataclasses (Confirmation, Payment, Fulfillment, Stock, Notifications, Pricing, Editing, Rules). Adicionar `Capabilities` como 9º aspecto é consistente com o design:

```python
@dataclass
class Capabilities:
    browseable_catalog: bool = True
    checkout_type: str = "full"  # "full" | "assisted" | "none"
    payment_flow: str = "inline"  # "inline" | "external" | "none"
    tracking: bool = True
    push_notifications: bool = False
    reorder: bool = False
    auth_required: bool = True
```

**Proposta:** Adicionar `Capabilities` ao `ChannelConfig`. Não é extensibilidade genérica (bag de `dict[str, Any]` — ideia ruim que a dispatch_v1 propunha e que removi na v2). É tipagem forte do que já é implícito.

---

## 3. Invariante testável — onde a cobertura é nominal

### 3.1 ✓ Testes de storefront/backstage vivem em shop/tests/

`shop/tests/test_web.py` testa URLs e views de storefront/backstage. `shop/tests/test_flow_s6.py` testa `storefront._helpers._shop_status`. Devem estar nos tests das respectivas apps.

**Status:** WP-H3. Redistribuição mecânica.

### 3.2 Testes que faltam para fechar maturidade

O projeto tem ~2.448 testes. Mas os edge cases que mais revelam maturidade estão ausentes:

- **Cancelamento parcial** — múltiplos itens, cancel mid-webhook (payment authorized, stock held, cancel chega)
- **Payment timeout + duplicate webhook race** — PIX timeout + webhook tardio chegam simultâneos
- **Notification failure → OperatorAlert escalation** — notification falha, operador nunca é avisado
- **iFood webhook out-of-order** — status `dispatched` chega antes de `preparing`
- **Lifecycle partial failure** — `_on_commit` completa 3 de 5 services, o 4º falha

Estes não são testes de feature — são **testes de invariante** como os kernels já têm (`test_commit_fails_on_expired_hold`, `test_double_hold_is_idempotent`).

---

## 4. Resultado formal — onde o retorno é informal

### 4.1 ✓ _OFFLINE_PAYMENT_METHODS — constante Python que deveria ser config

```python
# lifecycle.py L97-101
_OFFLINE_PAYMENT_METHODS = {
    "counter", "external",
    "cash", "dinheiro", "money",
    "balcao",
    "debito", "credito", "credit", "debit",
    "",
}
```

Isso é uma mistura de enum canônico (counter, external), localização PT-BR (dinheiro, balcao), e string vazia. Adicionar vale-refeição ou Apple Pay exige editar código.

**Proposta:** Derivar de `ChannelConfig.Payment.available_methods` + atributo `requires_intent: bool` por método. O lifecycle consulta config, não constante.

### 4.2 △ Handlers sem filtro por canal — parcialmente correto

A dispatch_v2 notava que handlers são lista flat. Verificação: `_PHASE_HANDLERS` em lifecycle.py É flat (dict phase→handler), mas cada handler internamente já consulta `config.confirmation.mode`, `config.payment.timing`, etc. Ou seja: o filtro existe, só não é declarativo.

**Proposta ajustada:** Não é urgente. Com `ChannelCapabilities`, os handlers poderiam consultar capabilities declarativamente em vez de ifs distribuídos. Mas funciona hoje. Prioridade baixa.

---

## 5. Degradação previsível — onde o sistema falha silenciosamente

### 5.1 △ Checks e Health já existem — mas incompletos

A dispatch_v2 afirmava "sem validação de startup" e "sem health check endpoint". **Incorreto.** Ambos existem:

**checks.py** (179L) — 4 errors + 3 warnings registrados via `@register(deploy=True)`:
- SHOPMAN_E001: SECRET_KEY default
- SHOPMAN_E002: ALLOWED_HOSTS vazio
- SHOPMAN_E003: Payment adapter é mock
- SHOPMAN_E004: Webhook token ausente
- SHOPMAN_W001: SQLite em produção
- SHOPMAN_W002: Notification console fora de DEBUG
- SHOPMAN_W003: Fiscal adapter ausente com canal fiscal ativo

**health.py** (124L) — `/health/` (liveness: DB + cache críticos) + `/ready/` (readiness: DB + cache + migrations críticos). JSON, sem auth, sem CSRF.

A dispatch_v2 errou ao afirmar ausência. A externo_v2 acertou ao referenciar esses arquivos e dizer "há espaço para elevar". **O que falta:**

- Check de invariante cruzada: `HOLD_TTL_MINUTES > PIX_TIMEOUT_MINUTES + buffer` (invariante operacional, não de deploy)
- Check de adapters obrigatórios resolverem no boot (não apenas mock detection)
- Health de APIs externas (geocoding, ManyChat alcançáveis)
- Degradation matrix documentada: "se Redis cai → rate limiting desliga, SSE congela; se ManyChat cai → notificação some"

### 5.2 ✓ Lifecycle propaga exceção sem compensação

```python
def dispatch(order, phase: str) -> None:
    """Exceptions propagate — an order stuck in an inconsistent state is worse
    than a visible error."""
```

O docstring é honesto: exceções propagam deliberadamente. Mas a consequência é que em `_on_commit`:

```python
customer.ensure(order)       # 1. OK
stock.hold(order)            # 2. OK — holds criados
loyalty.redeem(order)        # 3. FALHA — exception propaga
# payment.initiate nunca executa
# notification.send nunca executa
```

O pedido fica com holds ativos + loyalty não revertida + sem payment + sem notificação. O estado é inconsistente. O operador não vê nada (sem alert). O cliente não recebe nada (sem notification).

**Proposta:** Não é try/except genérico. É registro de progresso:

```python
def _on_commit(order, config):
    completed = []
    try:
        customer.ensure(order); completed.append("customer.ensure")
        stock.hold(order); completed.append("stock.hold")
        loyalty.redeem(order); completed.append("loyalty.redeem")
        # ...
    except Exception:
        _record_partial_failure(order, completed)
        raise
```

`_record_partial_failure` grava em `order.data["lifecycle_partial"]` o que completou. Um handler (`PartialFailureHandler`) detecta e cria OperatorAlert. O operador vê: "Pedido X: stock reservado, loyalty falhou, sem pagamento iniciado".

### 5.3 ✓ Cart qty sem validação de tipo

`cart.py` faz `int(request.POST.get("qty", 1))` sem try-except. Input não-numérico → `ValueError` → 500 não tratado.

**Fix:** `try: qty = max(1, min(int(…), 99)) except (ValueError, TypeError): qty = 1`

### 5.4 ✓ Notes e Name sem max_length no checkout

`checkout.py:237`: `notes = request.POST.get("notes", "").strip()` sem truncamento. Payload gigante → grava em `order.data`.

**Fix:** `notes[:500]`, `name[:200]`.

### 5.5 ✓ SSE sem fallback

`SkuStateView` envia badges via SSE. Conexão cai → badges congelam. Sem timeout client-side, sem polling, sem indicação de staleness.

**Fix:** Client-side timeout (30s sem evento → polling 2min). Badge de staleness visual.

---

## 6. Projection-first — onde a promessa já foi imaginada mas o fluxo não confia

### 6.1 ✓ Checkout: projection existe, view ignora

`storefront/projections/checkout.py` (146L) é o read model completo do checkout. A docstring diz isso. Mas `storefront/views/checkout.py` (1012L) monta contexto inline, concentra validação, address picker, repricing, tudo na view.

WP-H5 e WP-H6 do SPLIT-HARDENING-PLAN extraem mecanicamente (address picker → service, validação → service, _helpers → projections). O passo seguinte — que nenhum WP cobre ainda — é:

**Proposta:** `build_checkout_context(request, channel_ref) → CheckoutContext` como a interface única entre view e lógica. A view faz:

```python
def get(self, request):
    ctx = build_checkout_context(request, self.channel_ref)
    return render(request, "storefront/checkout.html", ctx.as_dict())
```

Isso é o padrão que `catalog.py` já usa com `build_catalog()`. Checkout deveria seguir.

### 6.2 ✓ Omotenashi: infraestrutura sem motor

`storefront/omotenashi/context.py` congela contexto temporal e pessoal. `favorite_category` retorna None (nunca populado). `days_since_last_order` é computado mas nenhuma view usa.

A externo_v2 formulou o melhor: **"O Shopman já sabe contextualizar; agora precisa aprender a agir consistentemente a partir desse contexto."**

**Proposta concreta (3 wires):**
1. `favorite_category` ← top category por qty nos últimos 90 dias (query em `OrderItem` via guestman)
2. Reorder suggestion na home se `days_since_last_order > 7` — link direto para cart com itens do último pedido
3. Badge "fechamos em Xmin" quando `OmotenashiContext.temporal_period == "closing"` — já existe o período, falta o wire no template

### 6.3 ✓ Backstage: admin melhorado, não posto de trabalho

KDS e POS usam projections (correto). Mas:
- Sem design tokens de touch target (44×44px mínimo para operação com mãos sujas/luvas)
- Status por cor apenas — sem dual-mode (cor + ícone) para color-blind-safe
- Sem alerta sonoro/vibração para ticket parado >10 min
- Sem fallback para rede instável (cozinha com Wi-Fi fraco)

A externo_v2 reformulou isso de forma que vale preservar: **"Se o software quer garantir a operação de um comércio, o backstage precisa ser um posto de trabalho confiável."**

---

## 7. Documentação — desinformação ativa

### 7.1 ✓ README e docs narram o Shopman pré-split

Verificado pela externo_v1 com line numbers, mantido pela externo_v2:

- `README.md` L15-20 — fala em "Flows, Services e Adapters" como se split não tivesse ocorrido
- `README.md` L76-112 — estrutura mostra `shopman/shop/web`, `api`, `admin` (pré-split)
- `README.md` L174-184 — referencia `docs/architecture.md`, `docs/guides/flows.md`, `docs/guides/auth.md` (inexistentes)
- `docs/README.md` L7-16, L81-103 — aponta para `docs/status.md`, `backends/`, `setup.py`
- `docs/getting-started/quickstart.md` L32-35 — "instalar o framework orquestrador (shopman/shop/)"
- `docs/reference/system-spec.md` L11-22 — define Shopman como `shopman/shop/`

**Impacto:** Quem chega pelo GitHub recebe narrativa antiga. Isso **reduz confiança no split** — o oposto do que se quer.

### 7.2 O que falta além da correção do drift

- **Production Checklist** — env vars, checks esperados, Redis config, CSRF origins
- **Adapter Contracts** — quais são prod-ready vs. mock; qual o fallback chain
- **Mapa canônico do split** — 1 página: "shop faz X, storefront faz Y, backstage faz Z, nenhum faz W"
- **"How to Add X" guides** — nova view, novo handler, novo adapter, nova fase

---

## 8. Multi-canal — de capacidade técnica a produto

### 8.1 ✓ WhatsApp é 1-way

ManyChat adapter envia OTP e notificações. Mas não há ingestão inbound, state machine de conversa, ou geração de link de pagamento. Testes de webhook inbound ManyChat estão `skip` com justificativa explícita de reimplementação pendente.

**Proposta (3 etapas, incrementais):**
1. Definir `Capabilities` do canal WhatsApp (assistido, sem browse, payment external, tracking via link)
2. Webhook inbound `/api/webhooks/whatsapp/` → parser de intenção (reorder, status, ajuda)
3. Reorder via WhatsApp: "quero o mesmo de sempre" → cart populado → link de pagamento

### 8.2 ✓ Marketplace é shallow

iFood ingest existe e funciona. Falta: sync de catálogo bidirecional, callback de aceitação/rejeição, desconto de taxas.

**Proposta:** `MarketplaceAdapter` protocol com `sync_catalog()`, `accept_order()`, `reject_order()`, `report_ready()`. iFood como primeira implementação.

### 8.3 API para mobile e chatbot

API storefront é session-cookie-based. Para mobile falta token auth, push notification, batch. Para chatbot falta reorder endpoint, availability com target_date.

**Proposta:** Isso é consequência de `ChannelCapabilities` não existir. Com capabilities por canal, os endpoints necessários para mobile e chatbot ficam derivados, não inventados.

---

## Análise cruzada: onde as análises convergem e divergem

### Convergências (incorporadas integralmente)

| Tema | Dispatch v2 | Externo v2 | Veredito |
|------|-------------|------------|----------|
| Templates duplicados = problema #1 | Sim, com contagem | Sim, com exemplos | ✓ Ambas corretas |
| Guardrails fora do perímetro | Sim | "Falsa confiança" | ✓ Externo formulou melhor |
| Projection-first incompleto | Checkout como exemplo | Checkout como exemplo | ✓ Mesma observação |
| Omotenashi: infra sem motor | Sim, wires específicos | "Sabe contextualizar, falta agir" | ✓ Complementares |
| Capability profile por canal | Sim, proposta de dataclass | Sim, lista de capabilities | ✓ Convergência total |
| Docs desinformam | Sim, mas genérico na v1 | Line numbers específicos | ✓ Externo mais preciso |
| Workflow result formalization | WorkflowResult genérico | Result types formais | ✓ Ambas, externo mais taxonômico |

### Divergências resolvidas

| Tema | Dispatch v2 | Externo v2 | Resolução v3d |
|------|-------------|------------|---------------|
| checks.py / health.py | "Não existem" (dispatch v1) → "Existem" (v2) | "Existem, espaço para elevar" | ✓ Externo v2 estava correto desde o início. Dispatch v2 corrigiu parcialmente. |
| commitment_snapshot | "Não existe, criar OrderCommitment" | "Existe no kernel (L255-258), falta nas superfícies" | ✓ Externo v2 verificou no código. Proposta ajustada: projection, não modelo novo. |
| Shop governa demais | Parcial — "design correto para orquestrador" | "Monólito federado, centralmente governado" | △ Ambos parciais. Shop governa boot corretamente. O problema são os resíduos (templates, imports diretos), não o boot. |
| handlers/__init__.py monolítico | "Design correto" (v2) | Não mencionado na v2 | ✓ Design correto. Handler registration flat é responsabilidade do orquestrador. |
| AppConfig minimalista | "Correto para surfaces" | "Dono difuso" | △ Parcial. AppConfig vazio é correto. Ownership difuso vem dos resíduos, não do AppConfig. |

### O que a dispatch v2 tinha que a externo v2 não

1. **Achados concretos de segurança** — cart qty DoS, notes injection, address ownership. Externo v2 menciona "parsing frágil" mas sem o impacto (500, DoS, payload injection).
2. **Lifecycle partial failure mechanics** — análise de `_on_commit` step-by-step mostrando estado inconsistente. Externo v2 diz "falha parcial" genericamente.
3. **_OFFLINE_PAYMENT_METHODS como constante** — achado específico de code smell. Externo v2 não cobre.
4. **Propostas com código** — dataclasses, fixes, patterns. Externo v2 descreve direções; dispatch v2 propõe implementações.

### O que a externo v2 tinha que a dispatch v2 não

1. **commitment_snapshot verificado no kernel** — line numbers em commit.py. Dispatch v2 tratava como inexistente.
2. **checks.py e health.py referenciados** — dispatch v1 afirmava ausência; externo v2 sabia que existiam.
3. **"Falha real vs. expansão de produto"** — separação explícita e correta. Dispatch v2 fazia essa separação mas menos claramente.
4. **"O Shopman já sabe contextualizar; agora precisa agir"** — formulação superior para o gap de Omotenashi.
5. **Escala observada (56.403 LOC, 330 arquivos)** — quantificação que dá proporção ao problema.
6. **Fluxo formal entry→workflow→backend→result→projection→surface** — framework conceitual para avaliar completude.

---

## Prioridades — o que fazer, em que ordem

### P0 — Completar autoridade semântica do split

**SPLIT-HARDENING-PLAN (já planejado, pronto para execução):**

| WP | O que | Complexidade |
|----|-------|-------------|
| WP-H1 | Purgar 84 templates/statics duplicados (incluir shop/omotenashi/) | Baixa |
| WP-H2 | Criar adapters KDS + Alert, eliminar 10 imports diretos | Média |
| WP-H3 | Corrigir 33 referências stale + redistribuir tests | Baixa-Média |
| WP-H4 | 4 testes arquiteturais de enforcement (após H2) | Média |
| WP-H5 | Emagrecer _helpers.py (627L → ~370L) | Média |
| WP-H6 | Emagrecer checkout.py (1012L → ~650L) | Média |

### P1 — Hardening de segurança e robustez

| Item | Esforço | Impacto |
|------|---------|---------|
| Cart qty safe parsing + max_length em inputs | 1h | Elimina vetor de DoS |
| Checks de invariante cruzada (HOLD_TTL > PIX_TIMEOUT + buffer) | 2h | Previne inconsistência |
| Check de adapters obrigatórios no boot | 2h | Fail-fast em deploy |
| SSE fallback polling client-side | 3h | Resiliência mobile |
| _OFFLINE_PAYMENT_METHODS → config-driven | 3h | Extensibilidade |

### P2 — Formalização de contratos (elevar ao padrão kernel)

| Item | Esforço | Impacto |
|------|---------|---------|
| `LifecyclePhaseResult` dataclass + partial failure tracking | 8h | Contrato formal para lifecycle |
| Result DTOs para services orquestradores (StockHoldResult, etc.) | 8h | Alinha com padrão dos adapters |
| `ChannelCapabilities` no ChannelConfig | 4h | Capabilities declarativas por canal |
| Commitment projection (storefront + backstage) | 6h | Surfacea conceito existente do kernel |

### P3 — Documentação como produto

| Item | Esforço | Impacto |
|------|---------|---------|
| README refletindo split real | 4h | Primeira impressão correta |
| docs/ corrigidos (caminhos mortos, topologia) | 3h | Elimina desinformação |
| Mapa canônico do split (1 página) | 2h | Orientação imediata para novos |
| Production Checklist | 3h | Deploy seguro |

### P4 — Omotenashi wiring + backstage como produto

| Item | Esforço | Impacto |
|------|---------|---------|
| favorite_category via order history | 3h | Antecipação real |
| Reorder suggestion na home | 4h | Conversão + retenção |
| Badge de urgência temporal | 2h | UX contextual |
| Backstage design tokens (touch, dual-status, sound) | 6h | Operação confiável |

### P5 — Canais externos first-class

| Item | Esforço | Impacto |
|------|---------|---------|
| WhatsApp inbound webhook + parser | 16h | Canal conversacional |
| MarketplaceAdapter protocol | 12h | Multi-marketplace |
| API token auth para mobile | 8h | Mobile nativo |

---

## Conclusão

O Shopman tem o que poucos projetos nessa faixa conseguem: **kernel de domínio denso e correto, visão de produto clara, e uma arquitetura que antecipa crescimento**. O commitment_snapshot no commit, os webhooks exemplares, o LGPD completo, os checks de deploy — são sinais de maturidade real.

O que separa o orquestrador e as superfícies do nível dos kernels são cinco lacunas específicas, todas endereçáveis:

1. **Ownership ainda difuso** — resíduos do split criam ambiguidade. P0 resolve.
2. **Lifecycle sem contrato de resultado** — o único componente central que retorna None. P2 resolve.
3. **Commitment invisível nas superfícies** — conceito forte no kernel, ausente onde o cliente e operador interagem. P2 resolve.
4. **Documentação desatualizada** — desinforma em vez de orientar. P3 resolve.
5. **Omotenashi inerte** — sabe tudo sobre o contexto, não age sobre nada. P4 resolve.

O salto para estado da arte não pede mais features. Pede que a disciplina que fez os kernels excelentes — dono nítido, contrato explícito, invariante testável, resultado formal, degradação previsível — seja aplicada com o mesmo rigor ao orquestrador e às superfícies.

Quando isso acontecer, o Shopman deixa de ser "kernel forte com camada de apresentação ainda se ajustando" e passa a ser o que já pretende: uma suíte operacional de comércio inequívoca de ponta a ponta.
