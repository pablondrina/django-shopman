# Prompt aberto para LLM externo: reorganização da camada orquestradora Shopman

Preciso de uma proposta arquitetural para reorganizar a camada orquestradora `shopman/shop` do projeto Django-Shopman.

Não quero uma resposta dogmática, nem baseada em nomenclaturas pré-fechadas. Quero uma solução arquitetural realmente adequada ao problema, guiada por semântica forte, simplicidade, robustez, elegância e capacidade de evolução.

## Contexto

O projeto é uma suíte modular de commerce/retail com múltiplos kernels/subdomínios fortes, incluindo pedidos, estoque, pagamentos, catálogo, clientes, autenticação e produção.

A camada `shopman/shop` funciona hoje como orquestradora/composition layer do sistema, conectando esses kernels e implementando experiências como:

- e-commerce web
- POS
- totem
- marketplace
- tracking
- conta do cliente
- operações internas

Essa camada já possui conceitos como:

- configuração por canal
- lifecycle declarativo
- handlers
- adapters
- projections/read models
- views/controllers web e API
- webhooks
- regras operacionais por canal

Mas ela ainda parece pesada, difusa e parcialmente ambígua em sua organização.

## Problema

Quero uma proposta de reorganização estrutural e semântica da camada orquestradora.

O objetivo é chegar a uma arquitetura:

- simples sem ser simplista
- robusta sob mudança
- elegante
- semanticamente inequívoca
- fácil de explicar para devs
- e, quando necessário, fácil de narrar também para operadores e produto

Quero evitar:

- camadas ornamentais
- diretórios conceituais demais
- wiring opaco
- contratos implícitos demais
- controllers/helpers inchados
- duplicação de semântica entre UI, orchestration e backend
- acoplamento oculto entre camada de experiência e detalhes dos kernels

## Ideias e tensões que surgiram internamente

Quero que você considere criticamente, sem assumir como corretas, as seguintes intuições:

### 1. O sistema pode ser visto como um fluxo encadeado

Uma formulação forte que surgiu foi algo próximo de:

`contexto/canal -> caso de uso -> fronteira de acesso -> backend -> retorno estável -> implementação da experiência`

Ou seja:

- existe um contexto operacional claro
- existe um caso de uso/caminho de orquestração
- existe uma fronteira para falar com kernels/integrações
- existe um retorno formal/estável
- existe uma implementação de experiência/UX/UI sobre esse retorno

Quero que você avalie se essa é uma boa abstração e como refiná-la.

### 2. O contexto de canal parece central

Surgiu a hipótese de que o “canal” pode ser mais do que apenas configuração.

Talvez ele possa concentrar:

- contexto operacional
- políticas/capabilities
- e até a implementação da experiência daquele contexto

Mas isso traz dúvidas:

- até que ponto isso é bom?
- quando isso confunde contexto de domínio com entrada técnica?
- quando faz sentido manter elementos fora do “canal”?

### 3. O caso de uso precisa ser explícito

Surgiu com força a ideia de que o sistema deve ter uma camada explícita de casos de uso/fluxos/caminhos de orquestração.

Ela poderia representar aquilo que o sistema “sabe fazer”, por exemplo:

- submeter checkout
- carregar catálogo
- confirmar pedido
- carregar tracking
- cancelar pedido

Quero que você avalie qual a melhor forma de modelar isso sem cair em sobreengenharia.

### 4. A fronteira com kernels e integrações precisa ser clara

Também surgiu a noção de uma camada intermediária entre a orquestração e os kernels/integradores.

Essa camada teria como papel:

- traduzir acesso
- esconder detalhes dos kernels
- estabilizar contratos
- evitar que a camada de experiência fale diretamente com backend interno/externo

Quero que você diga se essa separação faz sentido, como deveria ser desenhada, e com qual grau de formalização.

### 5. A saída precisa ser estável para permitir UX intercambiável

Uma preocupação forte é que implementações de UX/UI para e-commerce web, POS, totem etc. precisam ser:

- intercambiáveis
- testáveis
- fáceis de trocar
- fáceis de evoluir
- compatíveis com A/B testing
- sem surpresas

Ou seja, a camada de experiência precisa consumir algo estável, em vez de depender do shape bruto do backend.

Quero que você proponha a forma mais simples e robusta de fazer isso:

- read model?
- projection?
- result?
- view model?
- outra solução?

Mas sem assumir que qualquer uma dessas nomenclaturas seja a correta.

### 6. Semântica impecável é mais importante que aderência dogmática a padrões

Não quero uma resposta que imponha, por exemplo, “Clean Architecture” ou “Hexagonal” por obrigação.

Quero que você use os melhores benchmarks e padrões da indústria apenas como referência crítica, por exemplo:

- DDD
- Application Layer
- Service Layer
- Vertical Slice
- Ports and Adapters / Hexagonal
- CQRS leve
- patterns de plataformas de commerce e sistemas de negócio complexos

Mas a resposta deve nascer do problema concreto, não do template mental do padrão.

## O que eu quero de você

### 1. Diagnóstico semântico

Explique qual é, na sua visão, a essência arquitetural correta da camada orquestradora do Shopman.

Quero que você responda:

- o que essa camada realmente é
- o que ela não deve ser
- quais são as entidades conceituais mínimas necessárias
- quais conceitos são excesso

### 2. Proposta de organização

Proponha uma reorganização estrutural da camada.

Mas faça isso:

- sem depender de nomenclaturas rígidas pré-impostas
- escolhendo os nomes/conceitos que você julgar mais corretos
- justificando semanticamente cada escolha

Quero que você deixe claro:

- o que precisa ser pasta/categoria principal
- o que pode ser só conceito interno
- o que não vale a pena destacar

### 3. Fluxo canônico da camada

Descreva o fluxo canônico da camada orquestradora de forma simples e precisa.

Quero um fluxo que explique:

- como a interação entra
- como o contexto é resolvido
- como o caso de uso atua
- como os kernels são acessados
- como o retorno é estabilizado
- como a experiência final é montada

### 4. UX intercambiável

Explique como desenhar essa arquitetura para permitir:

- múltiplas implementações de UX por contexto
- troca de interface sem reescrever semântica
- A/B testing
- estabilidade de manutenção

### 5. Trade-offs

Quero que você me diga:

- onde simplificar mais
- onde simplificar demais seria perigoso
- quais categorias conceituais são indispensáveis
- quais parecem bonitas, mas atrapalham

### 6. Estrutura final sugerida

Proponha uma estrutura de diretórios/módulos final.

Pode trazer mais de uma alternativa, por exemplo:

- uma minimalista
- uma equilibrada
- uma mais formal

Mas recomende claramente uma delas.

## Requisitos da resposta

- Seja crítico.
- Seja concreto.
- Seja semanticamente rigoroso.
- Não use jargão sem necessidade.
- Não trate mais categorias como automaticamente melhores.
- Prefira a solução mais simples que preserve robustez e elegância.
- A solução precisa ser fácil de compreender e defender.

## Formato desejado

1. essência da camada
2. conceitos mínimos necessários
3. fluxo canônico
4. arquitetura proposta
5. como ela sustenta UX intercambiável
6. trade-offs
7. estrutura final recomendada

