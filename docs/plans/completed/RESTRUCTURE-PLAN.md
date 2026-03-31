# Plano de Reestruturação e Documentação — Django Shopman

> Fonte de verdade para WP-S1 a WP-D3.
> Cada WP é executável em uma única conversa com Claude Code.

---

## Diagnóstico

### 1. shopman-app/shopman/ — Problemas Concretos

**1.1 Dupla registração de handlers (contrib/ vs módulos)**

`orchestration.py` registra handlers simplificados do `contrib/`:
```python
register_directive_handler(StockHoldHandler())       # contrib/stock_handler.py
register_directive_handler(NotificationHandler())     # contrib/notification_handler.py
register_validator(StockCheckValidator())              # contrib/stock_validator.py
```

Mas `stock/apps.py` e `notifications/apps.py` TAMBÉM registram suas próprias versões:
- `stock/handlers.py` → `StockHoldHandler(backend)` + `StockCommitHandler(backend)` (mais sofisticados, com protocol)
- `notifications/handlers.py` → `NotificationSendHandler` (com routing, fallback, recipient resolution)

O que acontece: o registry recebe `ValueError` no segundo registro (mesmo topic) e silencia com `except ValueError: pass`. A versão que "ganha" depende da ordem de import. Isso é frágil e confuso.

**1.2 Inconsistência de status dos submódulos**

| Módulo | AppConfig? | Em INSTALLED_APPS? | Signal handlers? | URLs? | API? |
|--------|-----------|-------------------|------------------|-------|------|
| confirmation | Sim | Sim | Sim (hooks.py) | Não | Não |
| stock | Sim | Sim | Sim (receivers.py) | Não | Não |
| customer | Sim | Sim | Não | Não | Não |
| notifications | Sim | Sim | Não | Não | Não |
| payment | Sim | Sim | Não | Sim | Não |
| returns | Sim | Sim | Não | Não | Não |
| webhook | Sim | Sim | Não | Sim | Sim (views) |
| **pricing** | **Não** | **Não** | **Não** | **Não** | **Não** |
| **fiscal** | **Não** | **Não** | **Não** | **Não** | **Não** |
| **accounting** | **Não** | **Não** | **Não** | **Não** | **Sim (!)** |

`pricing`, `fiscal` e `accounting` são módulos soltos. `accounting` tem API REST mas não é Django app registrada.

**1.3 Naming confusion**

- `shopman.stock` (orquestrador) vs `shopman.stocking` (core) — dev novo confunde
- `shopman.customer` (orquestrador) vs `shopman.customers` (core) — idem
- `contrib/` contém handlers "legados" que fazem a mesma coisa que os módulos novos

**1.4 Infraestrutura misturada com domínio**

Na raiz de `shopman/`:
- `orchestration.py`, `channels.py`, `config.py`, `presets.py` — infraestrutura do orquestrador
- `confirmation/`, `stock/`, `payment/`, ... — módulos de domínio

Tudo no mesmo nível hierárquico.

### 2. Documentação — Situação

A suite antiga (`django-shopman-suite`) contém ~129 arquivos .md com conteúdo valioso:
- 4 ADRs (protocol-adapter, centavos, directives-sem-celery, string-refs)
- 11 guias de domínio (catálogo, estoque, produção, pedidos, clientes, auth, integrações)
- 18 specs técnicas
- Tutorial narrativo "dia na padaria"
- README, CONTRACTS.md, CHANGELOG.md por app
- SCORECARD.md, DECISIONS.md

**Problemas:** usa nomes antigos (offerman, stockman, omniman, craftsman, guestman, doorman), contém código obsoleto, referências a arquivos que não existem mais. Picada e espalhada.

O repo novo (django-shopman) tem: REFACTOR-PLAN.md e Makefile. Nada mais.

---

## Plano de Ação

### WP-S1: Reestruturar shopman-app

**Objetivo:** Eliminar ambiguidades, absorver contrib/, uniformizar módulos.

#### Estrutura alvo:

```
shopman-app/shopman/
├── __init__.py                    # version
├── apps.py                        # ShopmanConfig (ready → orchestration)
├── orchestration.py               # setup_channels, register_extensions (LIMPO)
├── channels.py                    # ensure_channel
├── config.py                      # validate_channel_config
├── presets.py                     # pos(), remote(), marketplace()
│
├── confirmation/                  # Django app ✓ (sem mudança)
│   ├── apps.py, handlers.py, hooks.py, service.py
│   └── __init__.py
│
├── stock/                         # Django app ✓ (absorve contrib/stock_*)
│   ├── apps.py                    # StockConfig (registra handlers)
│   ├── handlers.py                # StockHoldHandler, StockCommitHandler
│   ├── validator.py               # ← absorve contrib/stock_validator.py
│   ├── receivers.py, resolvers.py, protocols.py
│   ├── adapters/
│   └── __init__.py
│
├── customer/                      # Django app ✓ (sem mudança)
│   ├── apps.py, handlers.py, protocols.py
│   ├── adapters/
│   └── __init__.py
│
├── pricing/                       # Módulo puro (sem AppConfig — correto, só usado por outros)
│   ├── modifiers.py, protocols.py
│   ├── adapters/
│   └── __init__.py
│
├── notifications/                 # Django app ✓ (absorve contrib/notification_*)
│   ├── apps.py                    # NotificationsConfig (registra handler)
│   ├── handlers.py                # NotificationSendHandler
│   ├── service.py, protocols.py
│   ├── backends/
│   └── __init__.py
│
├── payment/                       # Django app ✓ (sem mudança)
│   ├── apps.py, handlers.py, protocols.py, webhooks.py, urls.py
│   ├── adapters/
│   └── __init__.py
│
├── fiscal/                        # Módulo puro (sem AppConfig — correto)
│   ├── handlers.py
│   ├── backends/
│   └── __init__.py
│
├── accounting/                    # ← DECISÃO: promover a Django app ou remover API?
│   ├── handlers.py
│   ├── backends/
│   ├── api/                       # tem API REST mas não é app registrada
│   └── __init__.py
│
├── returns/                       # Django app ✓ (sem mudança)
│   ├── apps.py, handlers.py, service.py
│   └── __init__.py
│
└── webhook/                       # Django app ✓ (sem mudança)
    ├── apps.py, conf.py, serializers.py, urls.py, views.py
    └── __init__.py
```

#### Ações concretas:

1. **Absorver `contrib/stock_handler.py` → já morto.**
   - `stock/handlers.py` já tem a versão completa (com backend protocol).
   - `contrib/stock_handler.py` é a versão simplificada legada.
   - Ação: deletar `contrib/stock_handler.py`.

2. **Absorver `contrib/stock_validator.py` → `stock/validator.py`.**
   - Mover o `StockCheckValidator` para `stock/validator.py`.
   - Registrar em `stock/apps.py` (junto com os handlers).
   - Deletar `contrib/stock_validator.py`.

3. **Absorver `contrib/notification_handler.py` → já morto.**
   - `notifications/handlers.py` já tem `NotificationSendHandler` (completo).
   - `contrib/notification_handler.py` é legado.
   - Ação: deletar `contrib/notification_handler.py`.

4. **Absorver `contrib/notification_backends.py`.**
   - O protocol `NotificationBackend` e `LogNotificationBackend` devem migrar para `notifications/backends/`.
   - Se já existe `notifications/backends/console.py` equivalente, verificar e deletar.
   - Ação: mover protocol para `notifications/protocols.py` se não existir lá, deletar `contrib/notification_backends.py`.

5. **Limpar `orchestration.py`.**
   - Remover `register_extensions()` inteiro (registrações agora vivem nos AppConfig de cada módulo).
   - Manter apenas: `setup_channels()`, `DEFAULT_CHANNELS`, `PRESETS`.
   - Atualizar `ShopmanConfig.ready()` se necessário.

6. **Deletar `contrib/` inteiro** após absorção.

7. **Decidir `accounting/`:**
   - Tem API REST (`api/serializers.py`, `api/urls.py`, `api/views.py`) mas NÃO está em INSTALLED_APPS.
   - Opção A: promover a Django app (criar apps.py, registrar).
   - Opção B: remover API (se não está em uso, a API é dead code).
   - **Decisão no WP:** verificar se urls.py referencia accounting API.

8. **Rodar `make test` e garantir 0 regressões.**

#### Critério de sucesso:
- `contrib/` não existe mais
- Cada handler tem exatamente UMA versão, registrada em exatamente UM lugar
- `make test` passa com o mesmo número de testes (±0)

---

### WP-D1: README + Arquitetura + Quickstart + ADRs

**Objetivo:** Dev novo consegue entender o projeto e rodar em < 15 minutos.

#### Artefatos:

```
docs/
├── README.md                          # Raiz do repo (symlink ou cópia)
├── architecture.md                    # Diagrama + explicação das 7 camadas
├── getting-started/
│   ├── quickstart.md                  # make install → make seed → make run → abrir admin
│   └── dia-na-padaria.md             # Tutorial narrativo (portado + atualizado)
└── decisions/
    ├── adr-001-protocol-adapter.md    # Portado + atualizado
    ├── adr-002-centavos.md            # Portado + atualizado
    ├── adr-003-directives-sem-celery.md
    └── adr-004-string-refs.md
```

#### Fontes (suite antiga):
- `README.md` → extrair estrutura, atualizar nomes
- `DECISIONS.md` → consolidar com ADRs individuais
- `docs/getting-started/dia-na-padaria.md` → traduzir nomes, verificar fluxos
- `docs/getting-started/instalacao.md` → adaptar para Makefile do repo novo
- `docs/decisoes/adr-*.md` → portar, atualizar terminologia

#### Regras:
- Cada exemplo de código DEVE ser verificado contra o repo atual
- Nomes antigos (offerman, stockman, etc.) → ZERO ocorrências nos docs novos
- Mapa de nomes incluído em `architecture.md` para quem conhece a suite antiga
- ADRs mantêm formato: Contexto, Decisão, Consequências

#### Critério de sucesso:
- `README.md` existe na raiz com quickstart funcional
- `docs/architecture.md` tem diagrama ASCII das 7 camadas + orquestrador
- 4 ADRs portados e atualizados
- Tutorial "dia na padaria" funciona com nomes novos

---

### WP-D2: Guias de Domínio

**Objetivo:** Documentar os 7 core apps + orquestrador com guias atualizados.

#### Artefatos:

```
docs/guides/
├── offering.md          # Catálogo, preços, listings, bundles
├── stocking.md          # Estoque, holds, moves, batches, planejamento
├── crafting.md          # Receitas, work orders, BOM, coef. français
├── ordering.md          # Pedidos, sessões, canais, directives, fulfillment
├── customers.md         # Clientes, contatos, grupos, loyalty, consent
├── auth.md            # Auth, OTP, device trust, bridge tokens
└── orchestration.md     # Como os módulos se conectam, signal flow, presets
```

#### Fontes (suite antiga):
- `docs/guias/catalogo-precos.md` → `offering.md`
- `docs/guias/estoque.md` → `stocking.md`
- `docs/guias/producao.md` → `crafting.md`
- `docs/guias/ciclo-do-pedido.md` → `ordering.md`
- `docs/guias/clientes.md` → `customers.md`
- `docs/guias/autenticacao.md` → `auth.md`
- Novo: `orchestration.md` (não existia na suite antiga)

#### Regras:
- Cada guia segue estrutura: Conceitos → Modelos → Serviços → Exemplos → Protocols
- Código verificado contra `models.py`, `service.py`, `protocols.py` atuais
- Manter em português (consistente com o projeto)
- Não inventar features — documentar SOMENTE o que existe

#### Critério de sucesso:
- 7 guias completos e consistentes
- Zero referência a nomes antigos
- Exemplos de código que funcionam

---

### WP-D3: Referência Técnica

**Objetivo:** Documentação de referência para consulta rápida.

#### Artefatos:

```
docs/reference/
├── protocols.md         # Mapa de todos os protocols e adapters
├── settings.md          # Configurações por app (SHOPMAN_*, etc.)
├── commands.md          # Management commands disponíveis
├── errors.md            # Códigos de erro estruturados
└── signals.md           # Sinais emitidos e consumidos por cada app
```

#### Fontes (suite antiga):
- `docs/referencia/protocolos.md` → `protocols.md`
- `docs/referencia/configuracoes.md` → `settings.md`
- `docs/referencia/comandos.md` → `commands.md`
- `docs/referencia/codigos-erro.md` → `errors.md`
- Novo: `signals.md`

#### Regras:
- Gerado a partir de leitura do código atual (conf.py, exceptions.py, signals/, management/)
- Formato tabular onde possível
- Cross-referência com guias

#### Critério de sucesso:
- 5 documentos de referência atualizados
- Consistente com o código atual
- Índice em docs/README.md linkando tudo

---

## Sequência de Execução

```
WP-S1 (estrutura) → WP-D1 (fundação docs) → WP-D2 (guias domínio) → WP-D3 (referência)
```

WP-S1 DEVE ser primeiro: docs precisam referenciar caminhos corretos.

---

## Prompts Sequenciais

Cada prompt abaixo será copiado e colado em uma nova conversa com Claude Code.
O LLM deve, ao final da implementação de cada WP, gerar o texto do próximo prompt.

### Prompt WP-S1

```
Projeto: django-shopman (repo em /Users/pablovalentini/Dev/Claude/django-shopman)

Leia o arquivo RESTRUCTURE-PLAN.md na raiz do repo. Execute o WP-S1 (Reestruturar shopman-app).

Resumo do que fazer:
1. Ler TODO o código de shopman-app/shopman/contrib/ e entender o que cada arquivo faz
2. Ler os módulos equivalentes (stock/handlers.py, notifications/handlers.py) e confirmar que são a versão evoluída
3. Absorver contrib/stock_validator.py → stock/validator.py
4. Verificar se contrib/notification_backends.py tem algo que notifications/ não tem; absorver se necessário
5. Limpar orchestration.py: remover register_extensions() e tudo que agora vive nos AppConfig dos módulos
6. Atualizar ShopmanConfig.ready() se necessário
7. Verificar se accounting/ tem URLs referenciadas em urls.py — decidir se promove a Django app ou remove API morta
8. Deletar shopman-app/shopman/contrib/ inteiro
9. Rodar make test — DEVE passar com o mesmo número de testes (tolerância: ±2 por skips)
10. Se algum teste quebrar, investigar e corrigir (a causa será algum import de contrib/)

Regras:
- NÃO inventar features. NÃO refatorar código de negócio. Só mover/limpar.
- Cada mudança deve ser mínima e rastreável.
- Se encontrar algo inesperado, parar e perguntar.

Ao final, gere o commit message e o texto do próximo prompt (WP-D1).
```

### Prompt WP-D1

```
Projeto: django-shopman (repo em /Users/pablovalentini/Dev/Claude/django-shopman)

Leia RESTRUCTURE-PLAN.md (seção WP-D1). Crie a documentação fundacional.

Você tem acesso à suite antiga em /Users/pablovalentini/Dev/Claude/django-shopman-suite/ como referência.
Os nomes mudaram: offerman→offering, stockman→stocking, omniman→ordering, craftsman→crafting, guestman→customers, doorman→auth, commons→utils.

O que fazer:
1. Criar README.md na raiz do repo com: visão geral, quickstart (make install/seed/run), estrutura do projeto, link para docs/
2. Criar docs/architecture.md com: diagrama ASCII das 7 camadas + orquestrador, explicação do Protocol/Adapter pattern, mapa de dependências entre apps
3. Criar docs/getting-started/quickstart.md com: pré-requisitos, instalação, seed, primeiro acesso ao admin
4. Portar docs/getting-started/dia-na-padaria.md da suite antiga: traduzir TODOS os nomes para os novos, verificar fluxos contra código atual, remover referências a coisas que não existem mais
5. Portar 4 ADRs de docs/decisoes/ da suite antiga para docs/decisions/: atualizar terminologia, verificar que as decisões ainda são válidas

Regras:
- Ler o código atual ANTES de escrever cada doc. Não copiar cegamente da suite antiga.
- Zero ocorrências de nomes antigos (offerman, stockman, omniman, craftsman, guestman, doorman).
- Exemplos de código devem ser verificáveis contra o repo.
- Manter em português.
- Não inventar features. Documentar SOMENTE o que existe.

Ao final, gere o commit message e o texto do próximo prompt (WP-D2).
```

### Prompt WP-D2

```
Projeto: django-shopman (repo em /Users/pablovalentini/Dev/Claude/django-shopman)

Leia RESTRUCTURE-PLAN.md (seção WP-D2). Crie os guias de domínio.

Suite antiga em /Users/pablovalentini/Dev/Claude/django-shopman-suite/ como referência (docs/guias/).
Mapa: offerman→offering, stockman→stocking, omniman→ordering, craftsman→crafting, guestman→customers, doorman→auth.

Para CADA guia (offering, stocking, crafting, ordering, customers, auth, orchestration):
1. Ler os models.py, service.py, protocols.py do app correspondente no repo ATUAL
2. Ler o guia equivalente na suite antiga como referência (NÃO como fonte de verdade)
3. Escrever o guia com estrutura: Conceitos → Modelos → Serviços → Protocols → Exemplos
4. Verificar cada exemplo de código contra o repo atual

Ordem sugerida: offering → stocking → crafting → ordering → customers → auth → orchestration.
O último (orchestration.md) é NOVO — não existe na suite antiga. Documentar:
- Como os módulos de shopman-app/shopman/ se conectam via signals e directives
- O fluxo de um pedido do commit até a conclusão
- Presets de canal (pos, remote, marketplace)
- Backend loading (stock, payment, fiscal, notifications)

Regras:
- Verificar TUDO contra o código atual. A suite antiga tem coisas obsoletas.
- Zero nomes antigos. Zero features inventadas.
- Manter em português.

Ao final, gere o commit message e o texto do próximo prompt (WP-D3).
```

### Prompt WP-D3

```
Projeto: django-shopman (repo em /Users/pablovalentini/Dev/Claude/django-shopman)

Leia RESTRUCTURE-PLAN.md (seção WP-D3). Crie a documentação de referência técnica.

Suite antiga em /Users/pablovalentini/Dev/Claude/django-shopman-suite/ como referência (docs/referencia/).
Mapa: offerman→offering, stockman→stocking, omniman→ordering, craftsman→crafting, guestman→customers, doorman→auth.

Para CADA documento de referência:
1. protocols.md — Ler TODOS os arquivos protocols.py do repo atual. Listar cada protocol, onde é definido, quais adapters existem.
2. settings.md — Ler TODOS os conf.py e apps.py. Listar cada setting (SHOPMAN_*, MANYCHAT_*, etc.) com default e descrição.
3. commands.md — Ler TODOS os management/commands/. Listar cada comando com flags e exemplos.
4. errors.md — Ler TODOS os exceptions.py. Listar cada exceção com código e quando ocorre.
5. signals.md — Ler TODOS os signals/ e receivers.py. Documentar cada sinal: quem emite, quem escuta, payload.

Também criar docs/README.md como índice geral linkando todos os docs criados em WP-D1, WP-D2 e WP-D3.

Regras:
- Gerado 100% a partir do código atual. A suite antiga é referência de formato, não de conteúdo.
- Formato tabular onde possível.
- Cross-referência com guias de WP-D2.
- Manter em português.

Ao final, gere o commit message e um resumo do que foi feito nos 4 WPs.
```

---

## Mapa de Nomes (referência rápida)

| Suite Antiga | Repo Novo | App Label |
|-------------|-----------|-----------|
| commons | shopman.utils | utils |
| offerman | shopman.offering | offering |
| stockman | shopman.stocking | stocking |
| craftsman | shopman.crafting | crafting |
| omniman | shopman.ordering | ordering |
| guestman | shopman.customers | customers |
| doorman | shopman.auth | auth |
| omniman/contrib/* | shopman-app/shopman/* | shopman_* |
| shopman-nelson | shopman-app/nelson | nelson |
