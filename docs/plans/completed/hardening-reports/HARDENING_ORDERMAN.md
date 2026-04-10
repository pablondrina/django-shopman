# HARDENING_ORDERMAN.md

## Escopo

Pacote analisado: `django-shopman/packages/orderman`

Objetivo deste documento: consolidar o plano de hardening do **Orderman** como kernel headless de pedidos omnichannel, separando:

- problemas reais
- decisões de design válidas
- melhorias estruturais recomendadas
- prioridades de execução

---

## Veredito sintético

O **Orderman** é, provavelmente, o kernel mais estrategicamente importante da suíte.

Ele já demonstra um desenho de domínio forte:

- `Session` como unidade mutável pré-commit
- `Order` como unidade canônica pós-commit
- `OrderEvent` como audit log append-only
- `IdempotencyKey` como replay guard
- `Directive` como mecanismo de tarefas assíncronas
- `Fulfillment` como execução logística

A arquitetura central é boa.

O principal ponto de atenção é que o Orderman já ocupa papel de **orquestrador central**. Portanto, qualquer ambiguidade nele tende a contaminar múltiplos domínios da suíte ao mesmo tempo.

---

## Decisões já assumidas

### 1. `session_key` será mantido

Decisão do projeto: **manter `session_key`** como identificador da sessão.

Conclusão de hardening:
- não tratar isso como problema
- não propor migração para `ref`
- preservar a semântica atual de `channel_ref + session_key` como identidade da sessão

Observação:
- `Session` continua sendo uma unidade operacional mutável e transitória
- portanto, não há obrigação arquitetural de tratá-la como aggregate root com `uuid + ref`

### 2. `Order` deve continuar sendo o centro canônico

O recorte `Session -> Commit -> Order selado` está correto e deve ser preservado.

### 3. `Directive` continua como infraestrutura at-least-once

Não propor remoção. O subsistema é útil e coerente com a ambição do Orderman.

---

## O que está bom e deve ser preservado

### A. Separação entre `Session` e `Order`

Essa é uma das melhores decisões do pacote.

Preservar:
- `Session` como unidade editável
- `Order` como unidade canônica pós-commit
- `snapshot` como congelamento do estado no momento do commit

### B. `OrderEvent` append-only

Preservar a ideia de audit log monotônico por pedido.

### C. Idempotência tratada como parte do domínio

Preservar o modelo `IdempotencyKey` e a aquisição explícita de lock no `CommitService`.

### D. Lifecycle baked no snapshot

Preservar a decisão de congelar transições e terminal statuses no snapshot do pedido.

### E. Itens relacionais com API simples

Preservar a estratégia de manter `SessionItem` e `OrderItem` relacionais, sem voltar para modelo puramente JSON.

---

## Problemas reais e hardening recomendado

## H1. Imutabilidade do `Order` ainda é mais semântica do que estrutural

### Diagnóstico

O modelo e as docstrings tratam `Order` como pedido selado/canônico/imutável.

Mas, na prática:
- vários campos ainda são mutáveis
- `data` e `snapshot` são JSONFields livres
- a imutabilidade depende mais da disciplina dos serviços do que de proteção estrutural do modelo

### Risco

- mutações indevidas pós-commit
- drift entre snapshot e estado atual
- dificuldade de auditoria real

### Hardening

1. Definir explicitamente quais campos de `Order` são mutáveis após criação.
2. Proibir alterações tardias em campos selados (`ref`, `channel_ref`, `session_key`, `snapshot`, `total_q`, itens).
3. Considerar proteção em `save()` ou via service layer canônica contra mudanças fora do lifecycle permitido.
4. Deixar claro que:
   - status muda
   - timestamps mudam
   - campos operacionais limitados podem mudar
   - conteúdo canônico do pedido não muda

### Prioridade

**Alta**

---

## H2. Blindagem monetária insuficiente no banco

### Diagnóstico

A convenção `_q` está muito bem definida, mas os campos monetários ainda não estão fortemente protegidos por constraint.

Exemplos a rever:
- `SessionItem.unit_price_q`
- `SessionItem.line_total_q`
- `OrderItem.unit_price_q`
- `OrderItem.line_total_q`
- `Order.total_q`

Hoje há boa disciplina de convenção, mas pouca blindagem estrutural.

### Risco

- valores negativos indevidos
- inconsistência silenciosa
- bugs em modifiers ou integrações contaminando o pedido canônico

### Hardening

1. Adicionar `CheckConstraint` para campos monetários onde o domínio exigir não-negatividade.
2. Formalizar quando preço negativo é proibido e quando desconto deve ser modelado em outra estrutura, não como valor unitário negativo.
3. Garantir coerência entre `line_total_q` e `qty * unit_price_q` quando aplicável, ou documentar explicitamente quando divergência deliberada é permitida.

### Prioridade

**Alta**

---

## H3. Política inconsistente entre `draft` e `commit`

### Diagnóstico

`ModifyService` aplica modifiers e validators com filtragem por regras do canal.

Já `CommitService` roda validators de `stage="commit"` sem a mesma clareza de política fina por código.

### Risco

- comportamento diferente demais entre edição e commit
- dificuldade para o canal controlar precisamente o que roda em cada fase
- acoplamento invisível entre regras do canal e commit final

### Hardening

1. Formalizar a política de execução para `stage="commit"`.
2. Decidir explicitamente se:
   - commit sempre roda todos os validators de commit, ou
   - commit também respeita allowlist configurável por canal.
3. Evitar que `draft` e `commit` sigam paradigmas de seleção diferentes sem justificativa documentada.

### Prioridade

**Alta**

---

## H4. `Directive` precisa de fechamento melhor como subsistema

### Diagnóstico

O modelo de `Directive` é bom, mas a robustez do subsistema depende fortemente do runtime em volta.

Ainda falta deixar mais fechado, em termos de produto, o contrato de:
- worker
- retries
- backoff
- terminal vs transient
- dedupe por `dedupe_key`
- observabilidade

### Risco

- semântica forte no modelo, mas fraca na operação
- handlers divergentes demais
- diretivas órfãs ou repetidas sem governança clara

### Hardening

1. Formalizar contrato canônico de worker.
2. Definir política oficial de retry/backoff.
3. Formalizar significado de `dedupe_key` e onde ela é obrigatória.
4. Definir métricas mínimas do subsistema (`queued`, `running`, `failed`, retries, age, lag).
5. Padronizar envelope de erro para handlers.

### Prioridade

**Média/Alta**

---

## H5. `Fulfillment` provavelmente merece identidade operacional própria

### Diagnóstico

Hoje `Fulfillment` opera com PK relacional e vínculo ao pedido.

Mas, pela natureza operacional da entidade, há forte argumento para que ela também tenha:
- `uuid`
- e possivelmente `ref`

### Risco

- dificuldade de rastreio operacional fora do banco
- menor ergonomia para integrações/logística/suporte

### Hardening

1. Avaliar adoção de `uuid` em `Fulfillment`.
2. Avaliar adoção de `ref` se o fulfillment for tratado como aggregate operacional relevante da suíte.
3. Evitar fazer isso para entidades de linha (`FulfillmentItem`), que não precisam de `ref`.

### Prioridade

**Média**

---

## H6. `Order` deve caminhar para `uuid + ref`

### Diagnóstico

Hoje `Order` já possui `ref`, mas não `uuid` técnico.

Pela convenção da suíte em consolidação:
- aggregate root relevante merece `uuid`
- aggregate root operacional também merece `ref`

### Hardening

1. Adicionar `uuid` técnico a `Order`.
2. Manter `ref` como identidade operacional/humana.
3. Padronizar o papel de cada um:
   - `uuid` = técnico/interno
   - `ref` = operacional/canônico

### Prioridade

**Alta**

---

## H7. Política de checks e holds precisa ficar mais explícita

### Diagnóstico

O `CommitService` exige checks frescos, valida `rev`, e também verifica expiração de holds em `result.hold_expires_at` e `result.holds[*].expires_at`.

Isso está bom.

Mas o contrato do payload de checks ainda parece implícito demais.

### Risco

- checks heterogêneos demais
- parsers divergentes entre handlers
- dificuldade de validar integridade entre serviços

### Hardening

1. Formalizar schema mínimo dos checks.
2. Formalizar schema mínimo dos holds retornados por checks.
3. Centralizar helpers de leitura/validação desses payloads.
4. Reduzir parsing ad hoc dentro do `CommitService`.

### Prioridade

**Média**

---

## H8. `Session.data` e `Order.data` ainda são livres demais

### Diagnóstico

O uso de JSONField é correto e útil, mas os contratos desses blobs ainda parecem excessivamente flexíveis.

### Risco

- bagunça semântica
- keys divergentes por canal
- schema drift silencioso

### Hardening

1. Definir schema mínimo canônico para `Session.data`.
2. Definir schema mínimo canônico para `Order.data`.
3. Reservar namespaces internos do kernel (`checks`, `issues`, `pricing`, etc.).
4. Evitar colisão entre chaves do kernel e chaves livres da aplicação.

### Prioridade

**Média**

---

## H9. Eventos e sinais precisam de contrato canônico mais explícito

### Diagnóstico

`Order.save()` emite `OrderEvent` e signal `order_changed`. O modelo é bom, mas a semântica do ecossistema em torno desses eventos ainda precisa ser estabilizada.

### Hardening

1. Formalizar lista de `event_type` canônicos.
2. Definir payload mínimo por tipo de evento.
3. Documentar quando usar `OrderEvent`, quando usar `Directive`, quando usar `signal`.
4. Evitar sobreposição confusa entre evento persistido e evento efêmero.

### Prioridade

**Média**

---

## Itens que não devem ser tratados como problema

## D1. `Session` continuar sem `ref`

Decisão aceita.

Não tratar como bug.

A sessão continua sendo entidade transitória e mutável; `channel_ref + session_key` é suficiente.

## D2. `Directive` existir dentro do Orderman

Não propor extração prematura.

Faz sentido que a orquestração imediata do pedido gere suas próprias diretivas operacionais.

## D3. Lifecycle do pedido ser configurável por snapshot

Não tratar como problema.

É uma boa decisão de domínio e deve ser preservada.

---

## Sugestões arquiteturais

## A1. Padronizar identidade operacional no núcleo

### Recomendação

- `Order`: **uuid + ref**
- `Fulfillment`: avaliar **uuid + ref**
- `Session`: manter `session_key`
- linhas e eventos: sem `ref`

## A2. Aproximar Orderman do padrão transversal da suíte

Padronizar melhor:
- nomes de identidade
- contratos JSON mínimos
- envelopes de erro
- semântica de evento persistido vs ação assíncrona

## A3. Tratar Orderman como o núcleo mais crítico da suíte

Ele merece hardening acima da média porque conecta múltiplos bounded contexts.

---

## Priorização sugerida

### Prioridade 1
- H1 Imutabilidade estrutural do `Order`
- H2 Blindagem monetária
- H3 Política consistente entre `draft` e `commit`
- H6 `Order` com `uuid + ref`

### Prioridade 2
- H4 Fechamento do subsistema `Directive`
- H7 Schema explícito de checks/holds
- H8 Schema mínimo de `Session.data` / `Order.data`

### Prioridade 3
- H5 Identidade operacional de `Fulfillment`
- H9 Contrato canônico de eventos/sinais

---

## Síntese final

O **Orderman** já demonstra o melhor tipo de ambição da suíte: não apenas persistir pedido, mas organizar corretamente a passagem de intenção editável para compromisso canônico.

Isso é excelente.

Ao mesmo tempo, por ocupar esse papel central, ele precisa de hardening rigoroso:

- mais blindagem estrutural
- mais clareza de contratos
- mais disciplina de identidade e dados
- mais fechamento do subsistema assíncrono

Em termos estratégicos, ele merece tratamento de **núcleo crítico da suíte**.
