# HARDENING_GUESTMAN.md

## Escopo
Análise de hardening do pacote `django-shopman/packages/guestman`.

Foco:
- simplicidade
- robustez
- elegância
- core enxuto vs ecossistema contrib
- agnosticidade / standalone readiness
- onboarding / adoção
- segurança
- documentação
- consistência arquitetural com a suíte

---

## Veredito executivo

O Guestman tem uma ideia de domínio forte: ser o núcleo de identidade relacional multicanal da suíte.

Seu centro conceitual é bom:
- `Customer` como aggregate root
- `ContactPoint` como camada de contatos verificáveis por canal
- `ExternalIdentity` como vínculo com provedores externos
- `CustomerGroup` como segmentação comercial
- `CustomerAddress` como endereçamento estruturado
- `ProcessedEvent` como proteção persistente contra replay

O problema principal não é “domínio ruim”.
O problema principal é **coerência interna incompleta** entre as peças do próprio domínio e a tensão entre:
- core essencial
- contribs opcionais
- decisões que hoje ainda vivem na camada de aplicação

Em resumo:
- **como núcleo de identidade multicanal**: promissor
- **como app standalone amplo de customer management**: bom, porém largo
- **como kernel já plenamente endurecido e semanticamente fechado**: ainda não

---

## Pontos fortes a preservar

### 1. Modelo de domínio melhor que um CRM simplista
O Guestman acerta ao não tratar cliente como apenas nome + telefone.

A separação entre:
- `Customer`
- `ContactPoint`
- `ExternalIdentity`
- `CustomerIdentifier` (contrib)

é forte e arquiteturalmente correta.

### 2. `ref + uuid` no aggregate root
`Customer` já adota o padrão correto da suíte:
- `ref` operacional
- `uuid` técnico

Isso deve ser preservado.

### 3. Gates bem pensados
A camada `Gates` é uma boa decisão arquitetural.
Especialmente:
- autenticidade de webhook
- replay protection
- merge safety

Ela dá ao Guestman um nível de seriedade acima de um simples app de cadastro.

### 4. Replay protection persistente
`ProcessedEvent` como nonce persistido em DB é uma boa decisão para ambiente distribuído.

### 5. Arquitetura core + contrib
A divisão entre core e contribs é promissora.
O problema hoje não é a existência dela, e sim a falta de nitidez operacional em algumas fronteiras.

---

## Principais problemas e ações de hardening

## G-1 — Formalizar de vez a relação entre `Customer.phone/email` e `ContactPoint`

### Problema
A documentação declara que:
- `Customer.phone/email` são cache rápido
- `ContactPoint` é source of truth

Mas o comportamento real ainda é híbrido:
- lookups principais usam `Customer.phone/email`
- sync atual é majoritariamente `Customer -> ContactPoint`
- não há uma política igualmente forte de `ContactPoint -> Customer`
- mudança de primário em `ContactPoint` não garante atualização do cache em `Customer`

### Risco
- divergência entre cache e source of truth
- lookup inconsistente
- bugs silenciosos de deduplicação / resolução de cliente

### Decisão a tomar
Escolher explicitamente um dos dois modelos:

#### Opção A — `ContactPoint` é realmente source of truth
- `Customer.phone/email` continuam existindo apenas como cache derivado
- todo lookup canônico passa por `ContactPoint`
- alterações em primário refletem no cache automaticamente
- cache nunca é usado como fonte de escrita canônica

#### Opção B — `Customer.phone/email` continuam primeiro-class
- `ContactPoint` deixa de ser source of truth pleno
- vira camada complementar para verificação / multicanal / histórico

### Recomendação
**Preferir Opção A.**

### Ações
- Definir formalmente a política “source of truth”.
- Mover `get_by_phone()` e `get_by_email()` para lookup primário via `ContactPoint`, com fallback transitório para cache legado.
- Criar rotina explícita de ressincronização `ContactPoint primary -> Customer.phone/email`.
- Garantir que `set_as_primary()` atualize o cache do aggregate.
- Garantir política explícita para remoção/substituição de contato primário.
- Adicionar testes de consistência bidirecional.

### Prioridade
**Alta**

---

## G-2 — Unificar a geração de `Customer.ref`

### Problema
Hoje existem múltiplas estratégias de geração de `Customer.ref` espalhadas:
- API gera `CUST-<sha256(phone+time)>`
- `IdentifierService` gera `CUST-<md5(identifier)>`

### Risco
- refs semanticamente inconsistentes
- políticas duplicadas em bordas diferentes
- dificuldade futura para rastreabilidade, observabilidade e integração

### Recomendação
Centralizar a geração de ref da entidade `Customer` em uma única capacidade.

### Ações
- Introduzir gerador canônico de refs da suíte em `shopman-utils` ou em uma camada padronizada compartilhada.
- Guestman deve usar apenas um ponto oficial para gerar `Customer.ref`.
- API e contribs não devem inventar suas próprias políticas locais.
- Manter compatibilidade com refs já emitidos.

### Observação arquitetural
Isso está alinhado com a diretriz maior da suíte:
- aggregate roots relevantes com `uuid + ref`
- `ref` gerado por política central, não por views/contribs soltos

### Prioridade
**Alta**

---

## G-3 — Limpar a política híbrida de unicidade / deduplicação

### Problema
A deduplicação hoje está distribuída entre:
- `Customer.phone` com constraint parcial
- `ContactPoint(type, value_normalized)` único globalmente
- `CustomerIdentifier`
- `ExternalIdentity`
- gates de unicidade

### Risco
- redundância de regras
- dificuldade para entender qual tabela “manda” em qual resolução
- edge cases de conflito entre cache, contato e identificador

### Recomendação
Formalizar a matriz de identidade da suíte.

### Ações
- Definir explicitamente o papel de cada camada:
  - `Customer.ref` = identidade operacional interna
  - `ContactPoint` = identidade de contato verificável
  - `ExternalIdentity` = identidade do provedor externo
  - `CustomerIdentifier` = lookup cross-channel opcional
- Revisar se `Customer.phone` deve continuar com `UniqueConstraint` própria após `ContactPoint` virar source of truth real.
- Evitar regras duplicadas sem propósito.
- Documentar a ordem oficial de resolução de identidade.

### Prioridade
**Alta**

---

## G-4 — Corrigir drift de configuração legado (`ATTENDING` vs `GUESTMAN`)

### Problema
`conf.py` lê `GUESTMAN`, mas `guestman_test_settings.py` ainda usa `ATTENDING`.

### Risco
- testes que não refletem configuração real
- falsa confiança em defaults
- bug de renomeação ainda não totalmente concluído

### Ações
- Corrigir settings de teste para `GUESTMAN`.
- Rodar bateria completa após ajuste.
- Procurar resíduos de nomenclatura antiga em docs, fixtures e testes.

### Prioridade
**Alta**

---

## G-5 — Clarificar a fronteira entre core, contrib e aplicação

### Problema
O Guestman tem core + contribs, o que é bom, mas hoje parte da política ainda está distribuída em lugares que parecem “aplicação”:
- geração de ref na API
- imports opcionais tratados nas views
- retornos como “feature not available” embutidos em endpoints

### Risco
- acoplamento entre API e presença/ausência de contribs
- semântica do pacote menos previsível
- experiência de integração menos limpa

### Recomendação
Deixar explícito o que é:
- core obrigatório
- contrib opcional
- política da aplicação/framework

### Ações
- Reduzir lógica de domínio dentro da API.
- Evitar geração de ref e decisões de identidade na view.
- Encapsular detecção de contribs em adapters/feature services, não diretamente em endpoints.
- Definir contratos públicos estáveis para ausência/presença de contribs.

### Prioridade
**Média/Alta**

---

## G-6 — Endurecer `provider_event_authenticity()` para produção

### Problema
Quando o secret está vazio, G4 aceita qualquer payload com warning.

### Leitura correta
Isso pode ser uma decisão de design aceitável para dev/local.
Não é bug por si só.

### Problema real
Falta política explícita para impedir esse comportamento em produção.

### Ações
- Introduzir modo estrito para produção.
- Falhar no boot ou marcar erro forte quando secret obrigatório não estiver configurado em ambiente produtivo.
- Documentar claramente o comportamento dev vs prod.

### Prioridade
**Média/Alta**

---

## G-7 — Rever o quanto `MergeService` pertence ao núcleo público do pacote

### Problema
O merge é bem sofisticado e poderoso, mas já é funcionalidade avançada de identity resolution / CRM.

### Leitura correta
Não é erro. Pode ser um diferencial valioso.

### Ponto de atenção
Talvez o Guestman precise declarar melhor que:
- merge é contrib avançado
- não é requisito do core mínimo

### Ações
- Posicionar merge explicitamente como capability avançada.
- Rever se toda a superfície de undo, loyalty merge, snapshot, etc. deve ficar no mesmo nível de exposição pública do core.
- Garantir documentação forte dessa fronteira.

### Prioridade
**Média**

---

## G-8 — Consolidar a política de `uuid + ref` para aggregate roots relevantes

### Situação atual
`Customer` já usa `uuid + ref`, o que é correto.
`CustomerGroup` usa `ref`, mas não `uuid`.
Algumas outras entidades usam UUID próprio ou identidade técnica específica.

### Recomendação
Padronizar melhor a suíte:
- aggregate roots relevantes -> `uuid + ref`
- entidades internas/join/ledger -> sem necessidade de `ref`

### Aplicação prática ao Guestman
#### Deve considerar `uuid + ref`
- `Customer`
- `CustomerGroup` (avaliar adicionar `uuid`)

#### Não precisa de `ref` próprio
- `ContactPoint`
- `ExternalIdentity`
- `ProcessedEvent`
- `CustomerAddress`

### Observação
`CustomerGroup.ref` já cumpre bem o papel de string ref.
Se ele for aggregate relevante para operação/admin/API, vale considerar adicionar `uuid` técnico também.

### Prioridade
**Média**

---

## G-9 — Melhorar a semântica de busca / resolução de cliente

### Problema
Hoje há múltiplos caminhos de busca:
- por phone/email direto no `Customer`
- por `CustomerIdentifier`
- por `ExternalIdentity`
- via API `LookupView`

### Risco
- resultados inconsistentes dependendo do caminho
- semântica diferente entre lookup rápido e resolução canônica

### Ações
- Definir um serviço canônico de resolução de cliente.
- Documentar a precedência oficial:
  1. external identity?
  2. contact point?
  3. identifier contrib?
  4. native cache fallback?
- Fazer as views consumirem essa política central.

### Prioridade
**Média/Alta**

---

## G-10 — Revisar qualidade da API como superfície pública do pacote

### Problema
A API funciona, mas hoje mistura:
- CRUD útil
- geração de ref
- feature detection de contrib
- mensagens de ausência de capability

### Ações
- Transformar a API em superfície mais fina sobre serviços realmente canônicos.
- Evitar lógica estratégica na view.
- Padronizar payloads de erro para ausência de contrib / capability.
- Rever se `CustomerViewSet.preferences` e `insights` pertencem ao mesmo namespace ou a endpoints de contrib.

### Prioridade
**Média**

---

## O que NÃO tratar como problema puro

### 1. Core + contrib constellation
Isso pode ser uma boa arquitetura.
O problema hoje não é existir; é a nitidez das fronteiras ainda não estar totalmente polida.

### 2. G4 aceitar tudo sem secret em dev
Aceitável como decisão de desenvolvimento, desde que produção fique protegida.

### 3. MergeService ser avançado
Não é um bug nem “excesso” automaticamente. Pode ser capability estratégica valiosa.
A questão é posicionamento e governança.

---

## Recomendações arquiteturais de médio prazo

### A. Definir o Guestman como “Identity & Relationship Kernel”
Isso daria ao app uma narrativa de produto mais forte do que “customer management”.

### B. Formalizar uma matriz de identidade
Sugestão:
- `Customer.ref` = identidade operacional interna
- `Customer.uuid` = identidade técnica
- `ContactPoint` = ponto de contato verificável
- `ExternalIdentity` = identidade do provider
- `CustomerIdentifier` = lookup cross-channel complementar

### C. Extrair geração de refs da borda
Alinhar Guestman com a diretriz maior da suíte para geração centralizada de refs.

### D. Deixar a API mais adaptadora e menos decisora
A API deve refletir capacidades do core/contrib, não inventar política local.

---

## Priorização sugerida

### P0
- G-1 Formalizar `Customer.phone/email` vs `ContactPoint`
- G-2 Unificar geração de `Customer.ref`
- G-4 Corrigir `ATTENDING` vs `GUESTMAN`

### P1
- G-3 Limpar política híbrida de unicidade/deduplicação
- G-5 Clarificar fronteira core/contrib/aplicação
- G-9 Definir resolução canônica de cliente

### P2
- G-6 Strict mode para autenticidade de webhook
- G-8 Consolidar `uuid + ref` nas aggregate roots relevantes
- G-10 Refinar a API pública

### P3
- G-7 Reposicionar/explicitar merge como capability avançada

---

## Síntese final

O Guestman tem um dos melhores potenciais de domínio da suíte.

Ele não pensa “cliente” como cadastro simples; pensa identidade, contato, provider, verificação, replay, merge e memória relacional. Isso é bom e valioso.

O hardening principal agora não é “inventar novas features”.
É **fechar semanticamente o que já existe**:
- quem é source of truth
- como refs são geradas
- como identidade é resolvida
- o que é core e o que é overlay opcional

Se isso for bem resolvido, o Guestman pode se tornar um componente muito forte da suíte.
