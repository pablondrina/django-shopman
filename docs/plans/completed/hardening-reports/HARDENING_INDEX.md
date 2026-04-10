# HARDENING INDEX — Django Shopman Kernel Suite

## Escopo

Apps analisados:

- Stockman
- Craftsman
- Offerman
- Payman
- Guestman
- Doorman
- Orderman

Arquivos-base deste índice:

- `HARDENING_STOCKMAN.md`
- `HARDENING_CRAFTSMAN.md`
- `HARDENING_OFFERMAN.md`
- `HARDENING_PAYMAN.md`
- `HARDENING_GUESTMAN.md`
- `HARDENING_DOORMAN.md`
- `HARDENING_ORDERMAN.md`

---

## Resumo executivo

A suíte já mostra um desenho de domínio acima da média. O ponto forte mais claro é que os apps não parecem CRUDs genéricos: cada um tenta capturar um bounded context real.

O padrão geral encontrado foi este:

- **domínio e intenção arquitetural**: fortes
- **polimento de invariantes e contratos**: ainda desigual
- **agnosticidade**: boa em vários pontos, mas ainda com áreas híbridas
- **surface consistency**: naming, versionamento e contratos externos ainda precisam limpeza
- **produção séria**: alguns apps estão próximos; outros ainda precisam hardening importante

---

## Ranking qualitativo atual

### Mais maduros conceitualmente

1. **Craftsman**
2. **Orderman**
3. **Payman**
4. **Offerman**
5. **Guestman**
6. **Doorman**
7. **Stockman**

### Mais prontos para uso standalone

1. **Craftsman**
2. **Payman**
3. **Offerman**
4. **Doorman**
5. **Orderman**
6. **Guestman**
7. **Stockman**

### Mais críticos para endurecer primeiro

1. **Orderman** — efeito sistêmico sobre quase toda a suíte
2. **Stockman** — invariantes frágeis em domínio sensível
3. **Doorman** — auth exige rigor extra em segurança
4. **Payman** — pequenas falhas aqui têm impacto financeiro
5. **Guestman** — identidade e deduplicação precisam coerência
6. **Offerman** — principalmente polimento arquitetural
7. **Craftsman** — melhor base geral, precisa mais governança de integração do que reparos centrais

---

## Tabela mestre por app

| App | Papel | Estado geral | Principal força | Principal risco | Tipo de ação prioritária |
|---|---|---|---|---|---|
| Stockman | Estoque / reservas / quant / ledger | Promissor, mas ainda frágil | Modelo conceitual bom de ledger + quant + hold | Invariantes críticas ainda não totalmente blindadas | Hardening estrutural de domínio e banco |
| Craftsman | Produção / micro-MRP | Forte | Núcleo enxuto e elegante | Modo integrado ainda permissivo demais | Tornar políticas operacionais explícitas |
| Offerman | Catálogo / oferta | Bom | Bom bounded context de oferta | Adapter e fronteiras de escopo ainda híbridos | Polimento arquitetural e possível repartição conceitual |
| Payman | Lifecycle de pagamento | Muito bom como núcleo mínimo | Modelo pequeno e claro | Invariantes financeiras ainda insuficientes | Blindagem de valores e semântica de estados |
| Guestman | Identidade de cliente multicanal | Muito promissor | Modelo de identidade relacional forte | Cache vs source of truth ainda inconsistente | Fechar política de identidade e refs |
| Doorman | Auth phone-first / access link | Bom | Bom recorte de auth e desacoplamento via adapter | AccessLink menos seguro do que o restante do pacote | Hardening criptográfico e limpeza de duplicidades |
| Orderman | Kernel de pedidos omnichannel | Muito promissor e estratégico | Boa separação sessão → pedido → evento | Centro nervoso da suíte ainda sem todas as blindagens | Hardening sistêmico e invariantes operacionais |

---

## Classificação: bug real vs decisão de design

### 1. Stockman

**Bug / problema real**

- `fulfill()` precisa reforçar internamente a rejeição de hold expirado
- constraint de unicidade de `Quant` com campos nullable precisa correção
- inconsistências no subsistema de batch
- arestas em materialização de holds / produção

**Decisão de design válida, mas a endurecer**

- uso de string refs em vez de FK para agnosticidade
- organização por serviços especializados

### 2. Craftsman

**Bug / problema real**

- mismatch de versão
- assimetria entre capacidade do kernel e da API
- alguns drifts de naming

**Decisão de design válida, mas a endurecer**

- graceful degradation em integrações externas
- heurística simples para profundidade/ciclo de BOM
- `WorkOrder.code` tende arquiteturalmente a `ref`, mas a necessidade de identificador operacional humano é legítima

### 3. Offerman

**Bug / problema real**

- adapter de catálogo com verificação de protocolo defeituosa
- alguns drifts de superfície e contratos implícitos demais

**Decisão de design válida, mas a endurecer**

- fallback de preço base quando listing falha
- união de product + listing + collection + bundles no mesmo app, desde que assumido como bounded context amplo de oferta

### 4. Payman

**Bug / problema real**

- falta blindagem suficiente para valores não positivos
- mismatch de versão

**Decisão de design válida, mas a endurecer**

- captura parcial única com status `captured`
- refund parcial entrar em regime `refunded`
- modelo mínimo sem multi-capture / multi-phase complexa

### 5. Guestman

**Bug / problema real**

- geração de `Customer.ref` fragmentada
- drift de configuração legado
- inconsistência prática entre cache e source of truth

**Decisão de design válida, mas a endurecer**

- `Customer.phone/email` como cache rápido
- arquitetura core + contrib constellation
- merge service avançado dentro do ecossistema Guestman

### 6. Doorman

**Bug / problema real**

- `AccessLink.token` em plaintext
- drift de naming (`Shopman Auth` vs `Doorman`)
- duplicação entre service e adapter em alguns fluxos

**Decisão de design válida, mas a endurecer**

- janela curta de reuso de access link para prefetch
- resolver por protocolo em vez de FK direta
- `User` do Django como mero mecanismo de sessão

### 7. Orderman

**Bug / problema real**

- ainda falta blindagem forte de imutabilidade do pedido
- invariantes monetárias merecem constraints adicionais
- app central demais para continuar com ambiguidades de superfície

**Decisão de design válida, mas a endurecer**

- sessão mutável + pedido selado
- directives como mecanismo assíncrono at-least-once
- lifecycle baked no snapshot
- manutenção de `session_key` como identidade da sessão

---

## Prioridade por severidade

### Prioridade P0 — atacar primeiro

#### Orderman

Porque ele é o ponto de convergência operacional da suíte.

Foco:
- imutabilidade estrutural do `Order`
- invariantes monetárias
- clareza dos contratos draft/commit
- identidade operacional de aggregates principais
- fechamento melhor do subsistema de directives

#### Stockman

Porque estoque e reservas não toleram invariantes frouxas.

Foco:
- `fulfill()` seguro
- unicidade real de `Quant`
- regras de saldo e concorrência mais fechadas
- coerência do subsistema de batches

#### Doorman

Porque auth sempre exige rigor maior.

Foco:
- hash de access link
- revisão da janela de reuso
- limpeza de duplicações e contratos de segurança

### Prioridade P1 — endurecer em seguida

#### Payman

Foco:
- positividade e constraints financeiras
- clarificar partial capture / partial refund
- consolidar uma única superfície canônica para transições

#### Guestman

Foco:
- unificar geração de ref
- fechar política cache ↔ source of truth
- consolidar estratégia de identidade/deduplicação

### Prioridade P2 — polimento arquitetural

#### Offerman

Foco:
- adapter/protocol
- limpeza de naming e contratos
- separar conceitualmente PIM x oferta x pricing/promotions

#### Craftsman

Foco:
- tornar explícito strict mode vs graceful mode
- alinhar API com kernel
- consolidar política de identidade operacional (`ref`)

---

## Temas transversais da suíte

### 1. Política de identidade: `uuid + ref`

Direção consolidada:

- aggregates relevantes devem tender a **`uuid + ref`**
- `ref` é identidade operacional humana/canônica da suíte
- `uuid` é identidade técnica estável
- quando existir identificador natural forte, ele pode ser o `ref`

Aplicações já alinhadas ou propostas:

- `Product.ref == sku`
- `slug` tende a virar `ref` quando o papel for de identidade externa/navegável
- `WorkOrder.code` tende arquiteturalmente a `WorkOrder.ref`
- `Order` merece `uuid + ref`
- `Payment`, `Listing` e possivelmente `Fulfillment` também merecem a mesma dupla
- `session_key` permanece como identidade da sessão

### 2. Ref generation compartilhado

Há forte argumento para extrair geração de refs legíveis para uma capacidade comum em `shopman-utils`, algo como:

- `RefGenerator`
- `RefSequence`
- `RefFormat`

Recomendação:
- lógica compartilhada em `shopman-utils`
- persistência/sequence storage por app, não necessariamente centralizada logo de início

### 3. Strict mode vs graceful mode

Tema transversal muito claro.

Vários apps hoje fazem fallback silencioso ou degradação elegante. Isso é ótimo para adoção standalone, mas perigoso em operação integrada.

Recomendação de suíte:
- explicitar **modo standalone/degradado** vs **modo integrado/estrito**
- não deixar decisões operacionais críticas dependerem apenas de “silêncio gracioso”

### 4. Naming e versionamento

Tema recorrente:
- nomes antigos ainda vazando em títulos, URLs, descrições ou settings
- `pyproject` e `__version__` divergindo em alguns apps

Recomendação:
- rodada única de limpeza de naming e versionamento em toda a suíte

### 5. Constraints de banco para invariantes críticas

Outro tema recorrente.

Em vários apps, as invariantes estão bem pensadas no domínio, mas ainda não totalmente blindadas no banco.

Recomendação:
- revisar sistematicamente `CheckConstraint`, `UniqueConstraint` e casos com `NULL`
- em especial nos apps financeiros, de estoque e de pedidos

### 6. App core vs app ecossistema

Tema mais visível em Guestman e Offerman.

Recomendação:
- separar melhor o que é **kernel essencial** do que é **overlay opcional / contrib / projeção de aplicação**
- isso melhora adoção, onboarding e confiança de uso standalone

---

## Roadmap sugerido

### Fase 1 — blindagem de núcleo

1. Orderman
2. Stockman
3. Doorman
4. Payman

Objetivo:
- corrigir riscos mais sensíveis de operação real

### Fase 2 — consolidação de identidade e contratos

5. Guestman
6. Craftsman
7. Offerman

Objetivo:
- fechar política de `ref`
- limpar naming/versionamento
- consolidar strict mode vs graceful mode
- alinhar APIs e adapters com o domínio

### Fase 3 — harmonização da suíte

Objetivo:
- extração de `RefGenerator` para `shopman-utils`
- limpeza de drifts de nomenclatura
- revisão geral de constraints críticas
- definição oficial do que é core, contrib e camada de aplicação

---

## Recomendação final

Se a meta é transformar a suíte em um conjunto de apps realmente confiáveis e reutilizáveis, a melhor ordem de ataque é:

1. **endurecer os kernels sistêmicos** (`Orderman`, `Stockman`, `Doorman`, `Payman`)
2. **fechar a política global de identidade** (`uuid + ref`, geração de refs, naming)
3. **refinar fronteiras de domínio** (`Guestman`, `Offerman`, partes do `Craftsman`)
4. **padronizar strict mode vs graceful mode** em todos os apps que interagem com outros bounded contexts

A base conceitual da suíte já é forte. O principal ganho agora não é “inventar mais domínio”; é **consolidar, endurecer e limpar as bordas**.
