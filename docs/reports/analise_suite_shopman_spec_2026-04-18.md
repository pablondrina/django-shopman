# Análise mestra da suíte Django-Shopman

Data: 2026-04-18

## Escopo

Este documento consolida a leitura da suíte inteira com foco em extração de SPECs orientadas a reprodução por Spec-driven Development.

Domínios cobertos:

- `shopman/shop`
- `packages/orderman`
- `packages/doorman`
- `packages/guestman`
- `packages/offerman`
- `packages/stockman`
- `packages/payman`
- `packages/craftsman`
- `packages/utils`
- `instances/nelson`

Relatórios-base:

- [shopman/shop](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/analise_critica_shopman_shop_spec_2026-04-18.md)
- [orderman](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/analise_orderman_spec_2026-04-18.md)
- [doorman](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/doorman_spec_analysis_2026-04-18.md)
- [guestman](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/guestman_spec_analysis_2026-04-18.md)
- [offerman](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/analise_critica_offerman_2026-04-18.md)
- [stockman](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/analise_critica_stockman_spec_2026-04-18.md)
- [payman](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/analise_payman_spec_2026-04-18.md)
- [craftsman](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/analise_craftsman_spec_2026-04-18.md)
- [utils](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/utils_spec_analysis_2026-04-18.md)
- [instância Nelson](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/analise_nelson_spec_2026-04-18.md)

## Veredito executivo

O Django-Shopman já é uma suíte tecnicamente séria. O código mostra:

- modelagem por domínios real
- preocupação explícita com concorrência, idempotência e auditabilidade
- separação razoável entre kernels e orquestrador
- testes relevantes em quase todos os subdomínios
- capacidade concreta de sustentar uma operação comercial omnichannel

Mas a promessa arquitetural ainda está parcialmente à frente da implementação. Hoje, o sistema é mais convincente como suíte verticalizada para food/retail brasileiro do que como framework universal, enxuto e plenamente agnóstico para “qualquer comércio”.

Em termos de maturidade:

- os kernels principais já têm valor real
- o orquestrador funciona
- a extensibilidade existe
- o fechamento de contrato ainda está incompleto em pontos cruciais

## Leitura transversal

### 1. A suíte tem um desenho de domínio bom

O melhor acerto estrutural é a decomposição em domínios:

- `orderman`: sessão, pedido, diretivas, commit, auditoria
- `stockman`: ledger, saldo, hold, disponibilidade, planejamento
- `payman`: intent, transaction, refund, transições
- `craftsman`: receita, ordem de produção, output, desperdício
- `offerman`: catálogo, coleção, listagem, bundle, projeção
- `guestman`: customer, contact point, merge, loyalty, insights
- `doorman`: OTP, access link, trusted device, bridge para sessão Django
- `utils`: erros, monetário, telefone, helpers de admin

Essa separação não é decorativa. Os pacotes têm modelos, serviços, testes e contratos próprios.

### 2. O ponto forte da suíte é robustez operacional, não simplicidade

O código acerta justamente onde software comercial tende a falhar:

- `transaction.atomic()`
- `select_for_update()`
- idempotência persistida
- ledger imutável
- transições explícitas de estado
- replay protection
- HMAC e tokens não persistidos em plaintext

Isso vale especialmente para:

- `orderman`
- `stockman`
- `payman`
- partes de `guestman`
- partes de `doorman`

O sistema não é “simples” no sentido de minimalista. Ele é mais forte no eixo robustez do que no eixo elegância.

### 3. O principal desvio entre intenção e realidade está no fechamento de contrato

O padrão mais recorrente nos relatórios é:

- o desenho conceitual é bom
- a implementação central é boa
- a borda pública ainda não fecha completamente o contrato prometido

Exemplos:

- `orderman`: `OrderViewSet` promete lookup por `ref`, mas não alinha plenamente o contrato público; `contrib/refs` ainda não entra no commit canônico
- `stockman`: drift entre serviços, API e testes; escopo por canal ainda é stub; `Batch.active()` quebrado
- `payman`: `PaymentBackend` existe como protocolo, mas não como ponte de execução real; `expires_at` não é estado operacional; idempotência de comando ainda falta
- `guestman`: vários contratos fortes, mas alguns gates e fluxos de admin ainda não batem com a promessa
- `doorman`: boa base de auth, mas concorrência e semântica de erro ainda não endurecidas o suficiente
- `offerman`: domínio forte, borda de admin/API ainda sem mesma semântica do core
- `craftsman`: micro-MRP bom, mas payloads/meta ainda são por convenção
- `shopman/shop`: framework funcional, porém com muito comportamento implícito e alguma duplicação

### 4. O orquestrador ainda é pesado demais

`shopman/shop` continua sendo o principal gargalo arquitetural.

Ele concentra:

- lifecycle
- config
- branding
- UX do storefront
- onboarding
- tracking
- checkout
- POS
- KDS
- regras
- notificações
- webhooks
- adapters
- projeções

Isso reduz a clareza da fronteira entre:

- framework
- produto
- verticalização

O resultado é um sistema poderoso, mas não enxuto.

### 5. A agnosticidade é parcial

A suíte é agnóstica o suficiente para extensão interna, mas ainda não totalmente neutra.

Marcas fortes de verticalização:

- PIX/EFI/Stripe
- ManyChat/WhatsApp
- iFood
- NFC-e/fiscal
- CEP/ViaCEP
- DDD/E.164 BR
- KDS
- balcão/comanda
- estoque D-1

Ou seja:

- como suíte para food/retail BR: muito plausível
- como framework universal de comércio: ainda não

## Leitura por pacote

### `shopman/shop`

Força:

- orquestrador coeso
- lifecycle explícito
- `ChannelConfig` como contrato forte
- projeções frozen para UI
- omotenashi/contexto temporal
- UX claramente mobile/WhatsApp-first

Fragilidade:

- core pesado
- validação rasa de config
- duplicação entre views/helpers/projections
- imports de integração mais profundos do que o ideal
- verticalização forte

Achado crítico:

- bug concreto em `lifecycle.py`: `ensure_payment_captured()` trata `config.payment` como `dict`, embora seja dataclass

Relatório:

- [analise_critica_shopman_shop_spec_2026-04-18.md](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/analise_critica_shopman_shop_spec_2026-04-18.md)

### `orderman`

Força:

- kernel forte de ordering
- boa disciplina transacional
- imutabilidade de `Order`
- commit idempotente
- audit trail sólido

Fragilidade:

- `channel_config` ainda chega de forma lateral e incompleta
- admin assume contratos não presentes no modelo
- `contrib/refs` ainda não está amarrado ao commit principal

Relatório:

- [analise_orderman_spec_2026-04-18.md](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/analise_orderman_spec_2026-04-18.md)

### `doorman`

Força:

- auth modelado com maturidade
- HMAC em tokens e OTP
- trusted device
- magic links
- bridge bem desenhado para `User`

Fragilidade:

- dependência prática de `guestman`
- concorrência/rate limit ainda sem endurecimento máximo
- UX funcional, mas longe de omotenashi-first plena

Relatório:

- [doorman_spec_analysis_2026-04-18.md](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/doorman_spec_analysis_2026-04-18.md)

### `guestman`

Força:

- bom núcleo de CRM/customer
- `ContactPoint` como source of truth
- gates explícitos
- merge com audit e undo
- loyalty e insights como extensão rica

Fragilidade:

- não totalmente agnóstico
- fluxo ManyChat ainda domina mais do que um core enxuto ideal
- inconsistências em admin/merge/insights

Relatório:

- [guestman_spec_analysis_2026-04-18.md](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/guestman_spec_analysis_2026-04-18.md)

### `offerman`

Força:

- kernel real de catálogo/oferta
- modelos coerentes
- bundles, collections, listings, pricing tiers
- projeção e contratos úteis

Fragilidade:

- borda de admin e API ainda não respeita totalmente a semântica do domínio
- contratos públicos ainda menores do que o produto já sabe

Relatório:

- [analise_critica_offerman_2026-04-18.md](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/analise_critica_offerman_2026-04-18.md)

### `stockman`

Força:

- `Move` como ledger
- `Quant` como cache de saldo
- holds e concorrência bem pensados
- bom motor técnico de inventory

Fragilidade:

- drift entre SPEC, API, serviços e testes
- escopo por canal ainda não implementado de verdade
- bug em `Batch.active()`
- shelf-life perde semântica em alguns fluxos por `sku` string

Relatório:

- [analise_critica_stockman_spec_2026-04-18.md](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/analise_critica_stockman_spec_2026-04-18.md)

### `payman`

Força:

- núcleo pequeno e bem definido
- `PaymentIntent` + `PaymentTransaction`
- transições claras
- refund parcial bem modelado

Fragilidade:

- fronteira de gateway ainda não integrada
- expiração sem estado operacional
- API só leitura
- idempotência de comando, chargeback e scoping ainda faltam

Relatório:

- [analise_payman_spec_2026-04-18.md](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/analise_payman_spec_2026-04-18.md)

### `craftsman`

Força:

- micro-MRP coerente
- `WorkOrder`, `WorkOrderEvent` e `WorkOrderItem` bem desenhados
- planejamento, execução e ledger material consistentes

Fragilidade:

- falta scoping por domínio/canal/tenant
- `payload` e `meta` ainda por convenção
- integrações externas ainda podem falhar de forma ambígua
- UX muito admin/API-first

Relatório:

- [analise_craftsman_spec_2026-04-18.md](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/analise_craftsman_spec_2026-04-18.md)

### `utils`

Força:

- pequeno e útil
- `BaseError`, monetário e telefone são bons primitives

Fragilidade:

- parte admin/Unfold menos agnóstica do que parece
- alguns contratos/documentação ainda frouxos

Relatório:

- [utils_spec_analysis_2026-04-18.md](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/utils_spec_analysis_2026-04-18.md)

### `instances/nelson`

Força:

- prova real de extensibilidade
- especializa canais, modifiers, D-1, loyalty, KDS, caixa e notificações sem tocar no core

Fragilidade:

- especialização muito concentrada em `seed.py`
- onboarding ainda manual
- exemplo forte de demo/operação, mas ainda não de SPEC limpa e reproduzível por terceiros

Relatório:

- [analise_nelson_spec_2026-04-18.md](/Users/pablovalentini/Dev/Claude/django-shopman/docs/reports/analise_nelson_spec_2026-04-18.md)

## Áreas que o software deveria cobrir melhor

### 1. Scoping explícito por domínio/tenant/store

Esse é um dos maiores gaps sistêmicos.

Hoje muitos contratos assumem implicitamente:

- um domínio operacional
- uma loja
- um espaço de nomes de refs suficientemente controlado

Para uma suíte realmente universal, faltam:

- `tenant_id`/`store_id`/`business_ref` em mais kernels
- isolamento forte em API, idempotência e refs

### 2. Schemas formais para JSONs operacionais

A suíte usa muito `JSONField` com schema implícito:

- `Shop.defaults`
- `Channel.config`
- `Order.snapshot`
- `Order.data`
- `RuleConfig.params`
- `WorkOrderEvent.payload`
- `meta` em vários lugares

Isso acelera evolução, mas reduz reproduzibilidade exata.

Falta uma camada clara de:

- schema versionado
- validação profunda
- documentação contratual sincronizada com o código

### 3. Contratos públicos mais duros

Vários pacotes já têm domínio forte, mas expõem APIs públicas mais pobres ou mais frouxas do que deveriam.

O sistema precisa endurecer:

- APIs públicas
- protocolos
- DTOs canônicos
- validação de create/update

### 4. UX operacional especializada por domínio

O `shopman/shop` tem UX boa para storefront, mas nem todos os domínios internos têm superfície operacional equivalente.

Exemplos:

- `craftsman` é bom como backend de produção, mas ainda não como experiência de operação
- `doorman` é bom como auth core, mas ainda não como UX sofisticada de login omnichannel

## Falhas fundamentais ainda pouco visíveis

### 1. O maior risco sistêmico é drift silencioso entre contrato e implementação

Essa é a falha estrutural mais importante.

Não é ausência de código. É o fato de que, em vários pontos:

- o domínio sabe uma coisa
- o service faz outra
- a API promete outra
- o admin assume outra
- os testes às vezes cobrem uma interface antiga

Esse drift é mais perigoso do que bugs triviais porque induz terceiros a reproduzir o sistema errado.

### 2. O sistema depende demais de convenção implícita

Há muita inteligência em:

- import side effects
- settings
- campos JSON
- refs string
- relações sem FK entre domínios

Isso funciona internamente, mas é frágil como SPEC portável.

### 3. A universalidade prometida ainda não foi conquistada

O projeto já é bom o bastante para sua vertical principal.

O risco é tentar vendê-lo mentalmente como framework universal antes de:

- separar melhor kernels e verticalização
- endurecer scoping
- formalizar schemas
- simplificar `shopman/shop`

## Recomendações prioritárias

### Prioridade 1

- Corrigir bugs concretos já identificados: `shopman/shop/lifecycle.py`, `stockman.Batch.active()`, drift em APIs e admins
- Endurecer contratos públicos dos kernels
- Formalizar schemas de `JSONField` mais críticos

### Prioridade 2

- Introduzir scoping explícito por domínio/tenant/store nos subdomínios onde fizer sentido
- Reduzir acoplamento implícito do orquestrador com kernels
- Fechar o loop entre protocolo e implementação em `payman` e partes de `stockman/craftsman`

### Prioridade 3

- Modularizar melhor instâncias de referência como `nelson`
- Melhorar UX operacional dos domínios não-storefront
- Remover drift entre narrativa, docs, admin e API

## Conclusão

O Django-Shopman já tem densidade técnica real e vários elementos de software comercial maduro. A suíte consegue sustentar, com credibilidade, uma operação de comércio omnichannel em seu domínio principal.

O maior desafio agora não é “ter mais features”. É fechar contratos, emagrecer o orquestrador e reduzir a distância entre:

- intenção arquitetural
- semântica pública
- implementação concreta

Se isso for feito, a suíte deixa de ser apenas uma solução vertical forte e passa a ter chance real de virar um framework de comércio modular de primeira linha.
