# Prompt conciso e afiado: reorganização da camada orquestradora Shopman

Analise a camada `shopman/shop` do projeto Django-Shopman e proponha a melhor reorganização arquitetural possível para ela.

## O problema

`shopman/shop` é a camada orquestradora de uma suíte modular com kernels fortes para:

- pedidos
- estoque
- pagamentos
- catálogo
- clientes
- autenticação
- produção

Hoje ela concentra composição, lifecycle, handlers, adapters, controllers, read models, webhooks, regras por canal e experiências como web, POS, totem, tracking e operações internas.

Ela funciona, mas ainda parece pesada, difusa e semanticamente ambígua.

## O objetivo

Quero uma proposta arquitetural para reorganizar essa camada de forma:

- simples
- robusta
- elegante
- semanticamente inequívoca
- fácil de manter
- fácil de evoluir
- fácil de explicar

Sem camadas ornamentais. Sem nomenclaturas infladas. Sem abstração por vaidade.

## Restrições e intenções

Leve em conta estas intenções, mas sem assumi-las como solução final:

- existe um contexto operacional claro, frequentemente associado a canal
- existe uma camada de caso de uso/fluxo que coordena a ação
- existe uma fronteira entre orquestração e kernels/integrações
- a saída para a experiência precisa ser estável
- implementações de UX/UI precisam ser intercambiáveis, especialmente para web, POS, totem e A/B
- wiring opaco e contratos implícitos devem ser evitados
- semântica importa mais que aderência dogmática a padrões

Uma formulação útil que surgiu internamente foi algo próximo de:

`contexto -> caso de uso -> fronteira de acesso -> backend -> retorno estável -> implementação da experiência`

Avalie isso criticamente. Refine ou substitua se necessário.

## O que quero na resposta

1. Diga qual é a essência correta dessa camada.
2. Diga quais são os conceitos mínimos indispensáveis.
3. Diga quais conceitos parecem bonitos, mas devem ser descartados.
4. Proponha o fluxo canônico da camada.
5. Proponha uma estrutura de organização concreta.
6. Explique como essa estrutura sustenta UX intercambiável sem bagunça.
7. Compare 2 ou 3 alternativas e recomende uma.

## Requisitos

- Seja crítico.
- Seja direto.
- Seja concreto.
- Use benchmarks e padrões da indústria apenas como referência crítica, não como muleta.
- Priorize KISS, DRY, semântica forte e robustez real.
- Se houver trade-offs, diga claramente.

## Formato desejado

1. essência da camada
2. conceitos mínimos
3. fluxo canônico
4. alternativas de organização
5. recomendação final

