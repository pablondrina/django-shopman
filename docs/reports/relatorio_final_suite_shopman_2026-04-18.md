# Relatório final unificado da suíte Django-Shopman

Data: 2026-04-18

## Objetivo

Consolidar, em um único parecer final, os principais achados dos relatórios de análise da suíte inteira produzidos em 2026-04-18, com foco em:

- leitura transversal da arquitetura
- convergências e recorrências entre pacotes
- riscos sistêmicos mais relevantes
- prioridades objetivas para evolução

## Base consolidada

Relatório-mestre:

- [analise_suite_shopman_spec_2026-04-18.md](analise_suite_shopman_spec_2026-04-18.md)

Relatórios por pacote e recortes complementares:

- [analise_critica_shopman_shop_spec_2026-04-18.md](analise_critica_shopman_shop_spec_2026-04-18.md)
- [analise_orderman_spec_2026-04-18.md](analise_orderman_spec_2026-04-18.md)
- [doorman_spec_analysis_2026-04-18.md](doorman_spec_analysis_2026-04-18.md)
- [guestman_spec_analysis_2026-04-18.md](guestman_spec_analysis_2026-04-18.md)
- [analise_critica_offerman_2026-04-18.md](analise_critica_offerman_2026-04-18.md)
- [analise_critica_stockman_spec_2026-04-18.md](analise_critica_stockman_spec_2026-04-18.md)
- [analise_payman_spec_2026-04-18.md](analise_payman_spec_2026-04-18.md)
- [analise_craftsman_spec_2026-04-18.md](analise_craftsman_spec_2026-04-18.md)
- [utils_spec_analysis_2026-04-18.md](utils_spec_analysis_2026-04-18.md)
- [analise_nelson_spec_2026-04-18.md](analise_nelson_spec_2026-04-18.md)
- [analise_critica_codigo_2026-04-18.md](analise_critica_codigo_2026-04-18.md)

## Síntese executiva

O Django-Shopman já se sustenta como uma suíte de comércio tecnicamente séria, com densidade real de domínio e sinais claros de maturidade operacional. O conjunto não parece um e-commerce genérico com camadas superficiais; há contratos explícitos, transações tratadas com cuidado, preocupação com concorrência, idempotência, auditabilidade e separação real entre subdomínios.

O melhor ativo da suíte é a qualidade dos kernels. `orderman`, `stockman`, `payman`, `guestman`, `doorman`, `offerman` e `craftsman` já apresentam modelos, serviços e testes que apontam para uma arquitetura modular plausível. A decomposição por domínios não é cosmética.

Ao mesmo tempo, o principal freio da suíte não é falta de funcionalidade. É falta de fechamento de contrato entre intenção, superfície pública e implementação concreta. Repetidamente, os relatórios apontam o mesmo padrão: o domínio central é bom, mas a API, o admin, os DTOs, os fluxos de integração ou os artefatos de configuração ainda não endurecem totalmente o contrato prometido.

O retrato final é este:

- como suíte verticalizada para food/retail brasileiro, o sistema já é forte e crível
- como framework universal, enxuto e plenamente agnóstico, ainda está em transição

## O que a suíte faz bem

### 1. Modelagem por domínios

O repositório organiza responsabilidades de forma coerente:

- `orderman` concentra sessão, pedido, commit, fulfillment e diretivas
- `stockman` concentra ledger, saldo, hold, disponibilidade e planejamento de estoque
- `payman` concentra intent, transação, captura e refund
- `guestman` concentra cliente, identidade, contato, merge, loyalty e insights
- `doorman` concentra autenticação, OTP, magic links e confiança de dispositivo
- `offerman` concentra catálogo, bundle, listagem e projeções de oferta
- `craftsman` concentra receita, ordem de produção, output e desperdício
- `shopman/shop` concentra orquestração, lifecycle, UX, projeções e composição operacional

Essa divisão forma um desenho de suíte, não apenas um monólito repartido por pastas.

### 2. Robustez operacional

Os relatórios convergem em um ponto importante: o projeto é mais forte em robustez do que em minimalismo. Há disciplina real em:

- `transaction.atomic()`
- `select_for_update()`
- locks pessimistas nos pontos certos
- idempotência persistida
- trilha de auditoria
- ledgers imutáveis
- estados e transições explícitas
- proteção razoável contra replay
- HMAC para tokens e códigos sensíveis

Esse eixo é especialmente forte em `orderman`, `stockman`, `payman` e partes relevantes de `doorman` e `guestman`.

### 3. Testes com valor arquitetural

Os testes da suíte não servem apenas para cobrir CRUD. Eles também funcionam como documentação executável de contratos, concorrência, lifecycle, projeções, segurança e integrações entre pacotes. Isso aumenta a credibilidade do desenho geral.

### 4. Capacidade real de verticalização

A instância `nelson` mostra que o core já suporta uma operação realista com:

- múltiplos canais
- regras por canal
- D-1 e disponibilidade segmentada
- KDS
- caixa e fechamento
- notificações
- fidelidade
- precificação contextual

Isso reforça que a suíte já consegue sustentar um produto operacional, e não apenas uma arquitetura conceitual.

## Onde a suíte ainda perde força

### 1. Drift entre contrato e implementação

Esse é o problema estrutural mais recorrente nos relatórios.

Em vários pontos, a promessa do sistema não coincide perfeitamente com o que está endurecido no código. O domínio central frequentemente está bem resolvido, mas:

- a API pública expõe menos do que o core já sabe
- o admin assume atributos ou fluxos que o modelo não garante
- testes e bordas ainda refletem contratos antigos
- integrações usam convenções implícitas onde faltaria contrato explícito

Esse drift aparece com intensidade em `orderman`, `stockman`, `payman`, `offerman`, `doorman` e também no orquestrador `shopman/shop`.

### 2. Orquestrador pesado demais

`shopman/shop` é hoje o maior ponto de tensão arquitetural. Ele concentra:

- bootstrap
- lifecycle
- storefront
- onboarding
- POS
- KDS
- branding
- tracking
- regras
- adapters
- notificações
- projeções
- várias integrações de produto

Isso torna o sistema poderoso, mas aumenta acoplamento e reduz a nitidez da fronteira entre framework, produto e verticalização.

### 3. Agnosticidade parcial

O discurso arquitetural sugere um framework de comércio amplo, mas os relatórios mostram uma realidade mais específica. A suíte ainda carrega vocabulário e escolhas muito marcados por operação brasileira e food/retail:

- PIX, EFI e Stripe
- WhatsApp e ManyChat
- iFood
- NFC-e e fiscal
- CEP e ViaCEP
- telefone BR e DDD
- KDS, balcão e comanda
- estoque D-1

Isso não é um problema para o produto real. O problema é apenas semântico: a universalidade prometida ainda não está totalmente conquistada.

### 4. Scoping ainda insuficiente

Um gap transversal importante é a falta de scoping mais explícito por tenant, loja, domínio operacional ou namespace de referência. Em vários kernels, o isolamento ainda depende mais de convenção do que de contrato formal forte.

### 5. Uso excessivo de schema implícito

Há diversos `JSONField` e estruturas sem schema formal suficientemente endurecido. Isso acelera evolução, mas enfraquece:

- reproduzibilidade da SPEC
- validação profunda
- previsibilidade entre versões
- clareza de contrato para terceiros

## Achados consolidados mais relevantes

### Achados de maior impacto imediato

- `shopman/shop` contém um bug concreto no lifecycle: `ensure_payment_captured()` trata `config.payment` como `dict`, embora o contrato seja dataclass.
- `stockman` apresenta drift relevante entre SPEC, serviço, API e testes, além de um bug em `Batch.active()`.
- `payman` tem um boundary de gateway/protocolo promissor, mas ainda não fecha a ponte operacional completa entre backend e execução real.
- `orderman` tem um kernel forte, porém partes da superfície pública ainda não alinham completamente `ref`, `channel_config`, admin e `contrib/refs`.
- `doorman` tem base sólida de autenticação, mas ainda precisa endurecer concorrência, granularidade de erro e semântica de alguns fluxos.
- `craftsman`, `offerman` e `guestman` têm domínios fortes, mas com partes públicas, administrativas ou de integração ainda menores do que o potencial do core.

### Padrões recorrentes entre pacotes

- domínio interno mais forte do que a borda pública
- boa semântica operacional com contrato insuficientemente formalizado
- extensibilidade existente, mas ainda muito apoiada em convenção
- presença de interfaces promissoras sem fechamento total do loop de execução
- diferença entre “funciona internamente” e “é reproduzível como SPEC por terceiros”

## Leitura final por maturidade

### O que já está maduro

- o núcleo transacional de pedidos
- o motor de estoque baseado em ledger e holds
- a modelagem base de pagamentos e refunds
- o domínio de cliente/CRM e resolução de identidade
- o subsistema de autenticação com OTP e trusted device
- a estrutura de produção para micro-MRP
- a capacidade de compor canais e verticalizar operação

### O que está funcional, mas ainda incompleto

- contratos públicos dos kernels
- schemas operacionais em JSON
- scoping multi-tenant/store mais formal
- fronteiras de integração externas
- UX operacional dos domínios não-storefront
- desacoplamento efetivo do orquestrador

### O que mais ameaça a evolução saudável

- drift silencioso entre narrativa arquitetural e comportamento exposto
- acoplamento excessivo concentrado em `shopman/shop`
- excesso de convenção implícita em pontos que deveriam virar contrato

## Prioridades recomendadas

### Prioridade 1: correções e fechamento de contrato

- corrigir bugs concretos já identificados nos relatórios
- alinhar APIs, admin e serviços aos contratos reais dos kernels
- endurecer DTOs, validações e superfícies públicas
- transformar invariantes importantes em contrato testado e explícito

### Prioridade 2: formalização e isolamento

- introduzir scoping mais forte por tenant/store/domain onde fizer sentido
- formalizar schemas críticos de `JSONField`
- reduzir dependência de side effects, convenções implícitas e wiring lateral
- fechar o ciclo entre protocolo e implementação em `payman`, `stockman` e integrações relacionadas

### Prioridade 3: refino arquitetural

- emagrecer `shopman/shop`
- separar melhor framework base, verticalização e produto operacional
- modularizar instâncias de referência como `nelson`
- elevar a UX operacional de domínios internos ao mesmo nível do storefront

## Conclusão final

O Django-Shopman já passou do ponto em que a discussão principal é “se existe substância”. Existe. A suíte tem densidade técnica, domínio real e sinais claros de software comercial maduro.

O ponto central agora é outro: transformar uma arquitetura forte, porém parcialmente implícita, em uma plataforma com contratos mais duros, bordas mais claras e menor distância entre intenção e implementação.

Hoje, o sistema já é convincente como suíte verticalizada para food/retail brasileiro. O próximo salto de maturidade depende menos de adicionar features e mais de:

- fechar contratos
- reduzir drift
- formalizar schemas
- melhorar isolamento
- aliviar o peso do orquestrador

Se essa etapa for executada com disciplina, a suíte deixa de ser apenas um produto vertical robusto e passa a se aproximar, com mais legitimidade, de um framework modular de comércio de primeira linha.
