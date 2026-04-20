# Refatoração da Camada Orquestradora `shopman/shop`

Data: 2026-04-20

## Objetivo

Consolidar uma proposta prática para evoluir a camada orquestradora `shopman/shop` em direção a uma arquitetura:

- semanticamente clara
- simples sem ser simplista
- robusta sob mudança
- elegante na composição com os kernels
- mais fiel aos parâmetros de design da suíte

Este relatório também responde a três questões centrais:

1. até que ponto vale reorganizar por intenção arquitetural
2. como tornar essa organização mais simples, robusta e elegante
3. como montar um mecanismo auditável de leitura integral por arquivo/LOC para reduzir pontos cegos em análises futuras

## Estado atual reavaliado

No estado atual do repositório, `shopman/shop` continua sendo uma camada de composição poderosa, mas densa. O desenho já acerta em pontos importantes:

- lifecycle declarativo em vez de subclasses de flow
- `ChannelConfig` como eixo de política operacional por canal
- início de separação entre read side e write side por meio de projections
- testes de invariantes arquiteturais relevantes
- bom aproveitamento dos kernels da suíte

Mas ainda há um conjunto claro de drifts:

- boot/wiring muito concentrado em `apps.py` e `handlers/__init__.py`
- workflow de pedidos ainda grande demais em `lifecycle.py`
- controllers e helpers ainda fazem trabalho que deveria ser de workflow/read model
- contratos de config e JSON operacional ainda são permissivos demais
- fronteira entre framework, produto e instância continua borrada

## Pergunta central: vale organizar por intenção arquitetural?

## Resposta curta

Sim, mas com disciplina. Organizar por intenção arquitetural tende a ser muito melhor para o caso do Shopman do que a organização puramente por tipo técnico. Porém, isso só gera ganho real quando a semântica e as regras de dependência são explícitas e estáveis. Caso contrário, vira apenas redistribuição cosmética de arquivos.

## Onde essa mudança realmente ajuda

### 1. Reduz ambiguidade de responsabilidade

Hoje, em muitos pontos, não está totalmente claro se um módulo:

- monta read model
- executa caso de uso
- resolve integração
- adapta HTTP
- aplica política

Organizar por intenção arquitetural força a responder essa pergunta corretamente.

### 2. Aumenta legibilidade de longo prazo

Em uma suíte modular com múltiplos kernels, a pergunta correta quase nunca é “em qual pasta técnica está isso?”, mas sim:

- isso é política?
- isso é caso de uso?
- isso é projeção?
- isso é adaptação?
- isso é entrada HTTP/API/admin?

Essa forma de leitura envelhece melhor.

### 3. Diminui drift entre design e implementação

Hoje a suíte já fala em:

- composição
- políticas por canal
- orquestração entre kernels
- read models
- adapters

Organizar a camada segundo essas mesmas ideias aproxima a topologia do código da linguagem arquitetural real.

### 4. Facilita testes mais corretos

Casos de uso, policies e read models ficam mais fáceis de testar de forma direta, sem inflar testes de controller e sem depender de cenários grandes demais para validar semântica básica.

## Onde essa mudança pode falhar

Ela falha quando:

- os nomes são vagos
- os limites entre módulos não são impostos
- cada feature cria sua própria microarquitetura
- a equipe usa “intenção arquitetural” como justificativa para excesso de abstração

O risco real não é a ideia em si. O risco é cair em um design ornamental, com muitos diretórios conceituais e pouca disciplina concreta.

## Benchmark de mercado: o que os bons sistemas fazem

Os melhores benchmarks não apontam para um único padrão universal, mas para uma convergência:

- Domain-Driven Design em sistemas de negócio densos
- Clean Architecture ou Ports and Adapters quando há muitas integrações e múltiplas superfícies
- Vertical Slice Architecture quando a clareza do caso de uso é mais importante do que camadas genéricas
- CQRS leve quando read side e write side têm ritmos e formas diferentes

Exemplos de referência conceitual:

- Shopify, Medusa, Saleor e commercetools no eixo commerce modular
- sistemas financeiros modernos no uso de ledgers, workflows explícitos e anti-corruption layers
- plataformas SaaS maduras que separam entrypoints, use cases, projections e integration adapters

O padrão mais adequado para o Shopman não é um “clean architecture puro” nem um “DDD acadêmico”. O melhor ajuste aqui é:

- kernels de domínio fortes
- camada orquestradora como composition/application layer
- vertical slices para superfícies operacionais
- CQRS leve para separar workflow e read model
- ports/adapters para estabilizar a fronteira com kernels e gateways

## Recomendação: organização híbrida, não dogmática

A melhor solução para o Shopman não é uma reorganização por intenção arquitetural em toda a árvore de forma uniforme e rígida. O melhor é um modelo híbrido:

- a espinha dorsal da camada organizada por intenção arquitetural
- as superfícies operacionais organizadas por vertical slice
- os kernels mantidos onde já estão

Em termos práticos:

### Núcleo da orquestração

- `composition/`
- `workflows/`
- `read_models/`
- `ports/`
- `entrypoints/`

### Superfícies verticais

- `operations/storefront/`
- `operations/pos/`
- `operations/kds/`
- `operations/account/`
- `operations/production/`
- `operations/closing/`

Essa combinação tende a ficar mais simples do que uma organização puramente conceitual.

## Estrutura recomendada

```text
shopman/shop/
  composition/
    bootstrap/
    policies/
    runtime/
    channels/
  workflows/
    orders/
    checkout/
    payments/
    notifications/
    fulfillment/
    production/
  read_models/
    catalog/
    checkout/
    tracking/
    payment/
    account/
    dashboard/
    pos/
    kds/
  ports/
    internal/
    external/
  entrypoints/
    web/
    api/
    admin/
    webhooks/
    commands/
  operations/
    storefront/
    pos/
    account/
    kds/
    production/
    closing/
  models/
    shop.py
    channel.py
    rules.py
```

## Regras de dependência

Essa parte é mais importante do que o nome das pastas.

- `entrypoints` só chamam `workflows` e `read_models`
- `workflows` usam `ports` e `composition.policies`
- `read_models` usam `ports` e `composition.policies`
- `adapters` concretizam `ports`
- `models` de composição não conhecem detalhes de HTTP/UI
- `entrypoints` não falam diretamente com kernels
- nenhum helper de view pode concentrar semântica de domínio

## O que deve sair de `shopman/shop`

Nem tudo precisa continuar vivendo nessa camada.

Deveria sair ou ser reduzido:

- conhecimento incidental demais de catálogo em helpers web
- lógica operacional pulverizada em views
- shape manual de payloads em múltiplos pontos
- wiring monolítico de handlers
- boot global “flat” de tudo em um único registrador

## O que deve permanecer

Deve continuar na camada:

- resolução de política por canal/loja/instância
- workflows cross-kernel
- projections/read models
- webhooks e adaptadores específicos do produto
- superfícies operacionais do produto

## Semântica como requisito de primeira classe

Se a semântica é fundamental, então o código precisa explicitar semanticamente:

- o que é policy
- o que é capability
- o que é workflow
- o que é command
- o que é read model
- o que é snapshot
- o que é projection
- o que é gateway
- o que é entrypoint

Hoje existe uma parte disso, mas ainda com sobreposição entre:

- `services`
- `helpers`
- `handlers`
- `adapters`
- `projections`

O refinamento semântico recomendado é:

- `workflows`: coordenação de caso de uso
- `ports`: contratos consumidos
- `adapters`: implementação de contrato
- `read_models`: modelo de leitura para UI/API
- `policies`: resolução declarativa de comportamento
- `entrypoints`: HTTP/admin/webhook/command

## Principal tese deste relatório

O Shopman melhora quando sua camada orquestradora deixa de ser “o app central que conhece tudo” e passa a ser “a camada de aplicação e composição da suíte”.

Essa troca de semântica é o salto mais importante.

## Refatoração proposta por fases

## Fase 1: estabilizar semântica e contratos

- corrigir narrativas/documentação que ainda falam em Flow classes
- definir glossário arquitetural canônico
- criar regras formais de dependência entre módulos
- elevar testes de arquitetura para `workflows`, `read_models`, `entrypoints` e `ports`

Entregável:

- ADR de arquitetura da camada orquestradora
- suite de invariantes expandida

## Fase 2: resolver policies e runtime

- extrair `ChannelPolicyResolver`
- transformar `ChannelConfig` em contrato mais forte
- introduzir `schema_version`
- separar policy operacional de UX/config incidental
- parar de espalhar `ChannelConfig.for_channel()` em múltiplos lugares sem mediação

Entregável:

- `composition/policies/`
- objeto de runtime estável por canal

## Fase 3: extrair workflows

- decompor `lifecycle.py` em workflows de fase
- centralizar pré-condições, transições e side effects em casos de uso claros
- formalizar runtime para pedidos

Entregável:

- `workflows/orders/on_commit.py`
- `workflows/orders/on_confirmed.py`
- `workflows/orders/on_paid.py`
- `workflows/orders/on_cancelled.py`
- `workflows/orders/on_returned.py`

## Fase 4: limpar entrypoints

- views e APIs passam a chamar workflow/read model
- eliminar lógica de domínio relevante em `web/views/_helpers.py`
- manter controller fino e previsível

Entregável:

- `entrypoints/web/`
- `entrypoints/api/`
- helpers reduzidos a adaptação HTTP

## Fase 5: consolidar read side

- toda tela crítica passa a depender de builder canônico
- catálogo, checkout, tracking, account, payment, POS e KDS usam projections/read models oficiais
- remover recomputações paralelas em views

Entregável:

- `read_models/` como fonte oficial de leitura

## Fase 6: encapsular JSON operacional

- criar envelopes tipados para `order.data`, `session.data`, `shop.defaults`, `channel.config`
- um único ponto de leitura/escrita por envelope
- deixar de manipular JSON bruto em múltiplos módulos

Entregável:

- `PaymentSnapshot`
- `AvailabilityDecision`
- `CheckoutPayload`
- `LoyaltySnapshot`
- `ManualDiscountSnapshot`
- equivalentes para config/versionamento

## Fase 7: modularizar bootstrap e integrações

- substituir registrador monolítico por bootstrap por capacidade
- manter falhas configuradas como visíveis e localizadas
- organizar ports/adapters para kernels e gateways externos

Entregável:

- `composition/bootstrap/`
- `ports/internal/`
- `ports/external/`

## Avaliação da hipótese do usuário sobre “ler tudo”

## Resposta direta

Você não está errado ao apontar que leituras parciais ou amostrais deixam passar falhas. Isso de fato acontece. Mas há uma nuance importante:

- ler todas as linhas é condição útil para rigor
- ler todas as linhas não é garantia de encontrar todo erro

Erros podem continuar invisíveis mesmo após leitura integral por:

- complexidade semântica
- dependências indiretas
- fluxo temporal
- contratos implícitos entre módulos
- bugs só revelados por execução concorrente ou dados reais

Portanto:

- sem leitura integral, o risco de omissão sobe bastante
- com leitura integral, o risco cai, mas não zera

## Mecanismo recomendado: cobertura auditável de leitura

Sim, é possível criar um mecanismo melhor do que a simples confiança na análise. O mais correto é combinar:

### 1. Manifesto de cobertura por arquivo

Arquivo gerado com:

- caminho
- hash
- LOC
- linguagem/tipo
- status de revisão
- agente responsável
- data/hora
- foco da análise
- achados encontrados

Exemplo:

```json
{
  "path": "shopman/shop/lifecycle.py",
  "sha256": "...",
  "loc": 492,
  "review_status": "fully_read",
  "reviewed_by": "agent-x",
  "review_pass": "orchestrator-v1",
  "focus": ["workflow", "contracts", "drift", "coupling"]
}
```

### 2. Ledger por faixa de linhas

Em vez de marcar só “arquivo lido”, marcar intervalos:

- linhas `1-120`
- linhas `121-240`
- etc.

Isso é mais auditável e menos sujeito a autoengano.

### 3. Múltiplas passagens com objetivos distintos

Uma única leitura total ainda é fraca. O ideal é:

- Pass 1: estrutura e dependências
- Pass 2: contratos e semântica
- Pass 3: concorrência e idempotência
- Pass 4: API/view/projection drift
- Pass 5: testes e cobertura de comportamento

### 4. Index local do codebase

Um índice pode ajudar muito:

- árvore de arquivos
- LOC por módulo
- símbolos exportados
- imports cruzados
- hotspots de acoplamento
- lista de arquivos não revisados

### 5. Relatório de lacunas explícitas

Toda análise deveria terminar com:

- arquivos lidos integralmente
- arquivos lidos parcialmente
- arquivos não lidos
- tipos de verificação realizados
- o que ainda pode escapar

Sem isso, o relatório parece mais conclusivo do que realmente é.

## O que eu recomendaria como mecanismo concreto

Criar um pipeline local de auditoria arquitetural com três artefatos:

### Artefato 1: `inventory.json`

- lista completa dos arquivos alvo
- LOC
- hashes
- linguagem
- módulo/dominio

### Artefato 2: `review_ledger.jsonl`

Uma linha por revisão de arquivo ou bloco:

- arquivo
- linha inicial/final
- agente/modelo
- timestamp
- tipo de análise
- resultado

### Artefato 3: `gap_report.md`

- arquivos sem revisão
- arquivos com revisão parcial
- áreas com maior densidade de achados
- prioridade de nova passagem

## Limite importante

Mesmo com esse mecanismo, não existe garantia honesta de “todo e qualquer erro foi localizado”. O que existe é:

- garantia auditável de cobertura da leitura
- melhora radical da disciplina de inspeção
- redução do risco de omissão silenciosa

Essa é a promessa correta.

## Alternativa ou complemento

Além do ledger de leitura, a melhor alternativa complementar é combinar:

- leitura integral auditável
- testes de arquitetura
- testes de invariantes
- métricas de acoplamento
- busca sistemática por contratos duplicados
- mutation testing em fluxos críticos
- diff review por semântica, não só por arquivo

Em outras palavras:

- leitura integral melhora detecção
- testes e invariantes aumentam garantia
- métricas e índices reduzem pontos cegos

## Recomendação final

Para o Shopman, eu recomendo fortemente:

1. refatorar a camada orquestradora como application/composition layer
2. usar organização híbrida: intenção arquitetural na espinha dorsal + vertical slices nas superfícies
3. tratar semântica como requisito de design, não como detalhe de nomenclatura
4. criar um mecanismo auditável de cobertura de leitura por arquivo e LOC
5. não confundir leitura total com garantia total

## Definição de sucesso

Essa camada estará muito mais próxima de primeira classe quando:

- controllers forem finos
- workflows forem o lugar oficial dos casos de uso
- read models forem a fonte única de leitura
- policies forem fortes e versionadas
- JSON operacional estiver encapsulado
- wiring for modular
- semântica arquitetural for visível no código
- a análise futura puder provar o que foi revisado e o que ainda não foi

