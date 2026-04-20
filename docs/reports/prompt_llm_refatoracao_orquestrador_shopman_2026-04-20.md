# Prompt para outros LLMs: refatoração da camada orquestradora Shopman

Analise a camada orquestradora `shopman/shop` do projeto Django-Shopman como uma application/composition layer que integra os kernels da suíte (`orderman`, `stockman`, `payman`, `offerman`, `guestman`, `doorman`, `craftsman`).

Seu objetivo é responder, com rigor arquitetural e pragmatismo de engenharia, como essa camada deveria ser refatorada para ficar:

- semanticamente clara
- simples, robusta e elegante
- mais alinhada aos princípios de design do projeto
- limpa, mantenível, atualizável e future-proof
- capaz de aproveitar da melhor forma tudo o que o backend já oferece

Quero uma análise profunda, crítica e concreta, não genérica.

## Contexto e foco

Considere que hoje a camada orquestradora já possui elementos como:

- lifecycle declarativo
- configuração por canal via `ChannelConfig`
- handlers, adapters e projections
- controllers web/api/admin
- forte integração com os kernels

Mas ainda sofre com sintomas como:

- orquestrador central pesado demais
- fronteiras borradas entre framework, produto e instância
- lógica operacional espalhada entre views, helpers, services e handlers
- contratos implícitos em JSON/config
- drift entre intenção arquitetural e implementação concreta
- wiring/boot excessivamente centralizado

## O que eu quero que você responda

### 1. Diagnóstico arquitetural

Explique qual é a função correta de uma camada como `shopman/shop` em uma suíte modular desse tipo.

Responda explicitamente:

- o que deveria estar nessa camada
- o que não deveria estar nela
- qual é a semântica correta dessa camada
- em que sentido ela deve ser “primeira classe”

### 2. Organização por intenção arquitetural

Avalie criticamente a hipótese de reorganizar a camada por intenção arquitetural, por exemplo separando em conceitos como:

- composition
- workflows/use_cases
- read_models/projections
- ports/adapters
- entrypoints
- policies/runtime

Responda sem dogmatismo:

- até que ponto isso realmente ajuda no nosso caso
- quais ganhos reais traria
- quais riscos e custos existem
- quando isso vira arquitetura ornamental
- se essa abordagem for boa, como deixá-la ainda mais simples, robusta e elegante
- se essa abordagem não for a melhor, qual abordagem seria superior para este caso

### 3. Benchmarking com padrões e mercado

Baseie sua resposta nos melhores benchmarks e padrões consolidados da indústria, incluindo quando relevante:

- DDD
- Clean Architecture
- Ports and Adapters / Hexagonal
- Vertical Slice Architecture
- CQRS leve
- Application Layer / Service Layer
- padrões usados em plataformas de commerce e sistemas operacionais de negócio complexos

Não quero uma aula genérica sobre padrões. Quero que você compare esses padrões com o caso do Shopman e diga o que realmente serve, o que não serve e como adaptar de forma prática.

### 4. Proposta de arquitetura-alvo

Proponha uma arquitetura-alvo para `shopman/shop`, incluindo:

- organização de módulos/pastas
- fronteiras de responsabilidade
- regras de dependência
- relação entre entrypoints, workflows, projections, policies, adapters e kernels
- como reduzir acoplamento sem cair em abstração excessiva

Se possível, proponha uma estrutura concreta de diretórios e regras de uso.

### 5. Semântica e contratos

A importância da semântica é absolutamente fundamental.

Explique:

- quais nomes/conceitos deveriam ser estabilizados
- como transformar a linguagem arquitetural em estrutura de código
- como evitar que o sistema continue misturando workflow, helper, service, projection e controller
- como endurecer os contratos de config e de JSON operacional

### 6. Estratégia de refatoração por fases

Proponha um plano incremental e pragmaticamente executável para migrar do estado atual para a arquitetura-alvo, sem reescrita irresponsável.

Quero fases claras, com:

- objetivo
- impacto
- risco
- critério de aceite

### 7. Auditoria de leitura integral e cobertura por arquivo/LOC

Também quero que você responda a esta provocação:

“Uma das grandes fontes de ineficiência das análises é o fato de o modelo não ler todas as linhas de todos os arquivos relevantes, fazendo apenas um apanhado geral e deixando erros passarem em branco.”

Responda com honestidade técnica:

- isso é verdadeiro?
- ler todas as linhas garante encontrar todos os erros?
- como criar um mecanismo auditável para aumentar muito o rigor da análise?

Quero que você proponha um mecanismo concreto para isso, por exemplo:

- inventário de arquivos
- hashes e LOC
- ledger de cobertura por arquivo e faixa de linhas
- múltiplas passagens com focos diferentes
- relatórios de lacuna
- índices de acoplamento e hotspots

Se houver alternativa melhor, proponha.

## Requisitos da resposta

- Seja crítico, preciso e específico.
- Não responda com clichês.
- Não trate “mais camadas” como sinônimo de “melhor arquitetura”.
- Diferencie clareza semântica de complexidade ornamental.
- Diga explicitamente quais compromissos de design você faria.
- Priorize simplicidade robusta e elegância real.
- Se usar listas, faça com conteúdo denso e concreto.
- Sempre que possível, conecte as recomendações aos problemas estruturais típicos de uma camada orquestradora de commerce modular.

## Formato desejado

Estruture a resposta em:

1. diagnóstico
2. avaliação da hipótese de organização por intenção arquitetural
3. benchmarks e padrões aplicáveis
4. arquitetura-alvo proposta
5. plano incremental de refatoração
6. proposta de mecanismo de cobertura auditável por arquivo/LOC
7. conclusão executiva

Se quiser, inclua também:

- trade-offs
- anti-patterns a evitar
- uma tabela comparativa entre opções arquiteturais

