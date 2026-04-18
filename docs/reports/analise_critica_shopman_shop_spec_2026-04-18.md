# Análise crítica de `shopman/shop`

Escopo: somente `shopman/shop` em `/Users/pablovalentini/Dev/Claude/django-shopman`.
Fora de escopo: `instances/nelson`, comunidade, estrelas/forks e deploy.

## Parecer executivo

`shopman/shop` já é mais do que um "framework de loja": ele funciona como um orquestrador de comércio orientado a eventos, com lifecycle explícito, adapters, projections e leitura forte de contexto operacional. O desenho é sério, tem boa robustez transacional e uma intenção clara de ser omnichannel.

O principal freio hoje é outro: o "core enxuto" ainda não está enxuto. O pacote concentra muita coisa de framework, produto e experiência em um mesmo lugar: configuração, branding, copy, PWA, onboarding, carrinho, checkout, tracking, POS, KDS, notificações, regras e integrações. A agnosticidade é boa na superfície, mas o código ainda carrega um vocabulário muito específico de food retail brasileiro, WhatsApp, PIX, ManyChat, iFood, CEP, NFC-e e operação de balcão.

## SPECS extraídas

### 1) Contrato de bootstrap e composição

- O pacote inicializa handlers, regras e sinais no `AppConfig.ready()`, não por importação implícita. A entrada de composição é `shopman/shop/apps.py`.
- `register_all()` é a lista autoritativa de handlers, modifiers, validators e sinais. A ideia é que o framework suba pronto, sem wiring manual espalhado.
- O sistema usa `Directive` como barramento de efeitos assíncronos, em vez de acoplamento direto entre eventos e side effects.

Referências: [apps.py](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/apps.py), [handlers/__init__.py:68](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/handlers/__init__.py:68)

### 2) Configuração canônica por canal

- `ChannelConfig` é o contrato central. Ele modela confirmação, pagamento, fulfillment, estoque, notificações, pricing, editing, rules, lifecycle e UX de handle.
- A cascata é `defaults hardcoded → Shop.defaults → Channel.config`.
- O contrato é deliberadamente permissivo: campos ausentes herdam, campos explícitos sobrescrevem.
- O design assume que o canal pode ser remoto, POS, marketplace, web ou WhatsApp, mas o comportamento é sempre derivado de configuração, não de classes de flow.

Referências: [config.py:13](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/config.py:13), [config.py:191](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/config.py:191), [channel.py:13](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/models/channel.py:13)

### 3) Lifecycle de pedidos

- O lifecycle é event-driven e faseado: `on_commit`, `on_confirmed`, `on_paid`, `on_preparing`, `on_ready`, `on_dispatched`, `on_delivered`, `on_completed`, `on_cancelled`, `on_returned`.
- O fluxo não usa classes `Flow`; usa `_PHASE_HANDLERS`, o que reduz acoplamento estrutural.
- `on_commit` faz: garantir cliente, checar disponibilidade opcional, reservar estoque, registrar decisão de disponibilidade, aplicar loyalty, iniciar pagamento e/ou fulfillment conforme timing, e agendar `order_received`.
- `on_confirmed` inicia pagamento pós-commit ou libera fulfillment em pagamento externo.
- `on_paid` trata corrida de cancelamento com refund e alerta.
- `on_completed` consolida loyalty e fiscal.
- `on_cancelled` e `on_returned` fazem reversões explícitas de stock, payment, fiscal e notificação.

Referência: [lifecycle.py:157](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/lifecycle.py:157)

### 4) Regras e policy engine

- `rules.engine` carrega `RuleConfig` do banco, cacheia e registra validadores dinamicamente.
- O modelo mental é bom: handlers são estáticos; rules são operacionais e alteráveis em runtime.
- Na prática, a migração para rules está incompleta: pricing modifiers ainda são registrados fora do ciclo DB-driven, e o engine hoje cobre validators com prioridade maior do que modifiers.

Referência: [rules/engine.py:1](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/rules/engine.py:1)

### 5) Omotenashi-first e UX contextual

- O sistema trata copy como dado de produto: `OmotenashiCopy` permite override por `key + moment + audience`.
- `OmotenashiContext` calcula momento do dia, abertura/fechamento, audiência, aniversário, dias desde o último pedido e categoria favorita.
- `storefront_context` materializa sugestões vivas: popularidade, happy hour, minimum order progress, upsell e pricing hints.
- Há esforço real de `WhatsApp-first` e `mobile-first`: WhatsApp via ManyChat, onboarding leve, PWA, service worker, HTMX, partials e SSE.

Referências: [omotenashi/context.py:57](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/omotenashi/context.py:57), [omotenashi/copy.py:281](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/omotenashi/copy.py:281), [services/storefront_context.py:46](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/services/storefront_context.py:46), [adapters/notification_manychat.py:1](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/adapters/notification_manychat.py:1), [web/views/pwa.py:18](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/web/views/pwa.py:18)

### 6) Projections como read models

- As projections são frozen dataclasses e seguem uma disciplina clara de leitura: não expor modelos mutáveis na template layer.
- `CatalogProjection`, `CartProjection`, `CheckoutProjection`, `OrderTrackingProjection`, `PaymentProjection`, `KDSBoardProjection`, `DashboardProjection`, `CustomerProfileProjection` e `ProductionBoardProjection` já existem como contratos de UI.
- A ideia é boa: views ficam finas e a inteligência vai para builders/testáveis.
- O problema é que parte dessa inteligência ainda se duplica entre view layer, helpers e projection layer.

Referências: [projections/catalog.py:110](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/projections/catalog.py:110), [projections/cart.py:160](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/projections/cart.py:160), [projections/order_tracking.py:132](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/projections/order_tracking.py:132), [projections/payment.py:78](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/projections/payment.py:78)

## Análise por entidade

### `Shop` singleton

`Shop` é o centro de identidade visual e operacional: endereço, contatos, horários, branding, cores, tipografia, social links, copy de tracking, defaults e integrações. Isso torna o onboarding prático, mas também transforma o model em um quasi-god object.

Pontos fortes:
- um único ponto de verdade para marca e operação;
- supporta temas e design tokens;
- simplifica bootstrap de novas lojas.

Pontos fracos:
- mistura CMS, brand system, defaults operacionais e integrações;
- `NotificationTemplate.save()` ainda tem `TODO` de invalidation;
- `defaults` e `integrations` são `JSONField` com schema implícito, não validado em profundidade.

Referências: [models/shop.py:89](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/models/shop.py:89), [models/shop.py:399](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/models/shop.py:399), [models/shop.py:435](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/models/shop.py:435)

### `Channel`

O model `Channel` representa canal de venda por `ref` e `kind`, com `config` próprio e vínculo opcional com `Shop`. O `ref` é o identificador agnóstico. O `kind` ainda parece mais documental do que funcional dentro de `shopman/shop`.

Sinal de intenção:
- canal como unidade de comportamento;
- `config` por canal;
- convenção de nomes para ligar catálogo/listing/canal.

Ganho real:
- flexibilidade de operação multi-canal;
- transporte do contrato por `ref`.

Gaps:
- o `kind` não dirige o lifecycle em `shopman/shop`;
- o contrato é mais por convenção do que por schema.

Referência: [models/channel.py:13](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/models/channel.py:13)

### Rules, Promotion, Coupon, DeliveryZone, KDS, CashRegister, Alerts, Closing

O conjunto de models administrativos mostra uma plataforma de operação, não só checkout:
- `Promotion`, `Coupon`, `RuleConfig` cobrem pricing e promoções;
- `DeliveryZone` modela entrega por CEP/bairro;
- `KDSInstance` e `KDSTicket` modelam cozinha e despacho;
- `CashRegisterSession` e `CashMovement` modelam caixa;
- `OperatorAlert` dá canal de alerta;
- `DayClosing` formaliza fechamento e auditoria.

Isso é robusto, mas também confirma que o pacote é altamente verticalizado em operação de comércio físico/food.

Referências: [models/rules.py](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/models/rules.py), [models/delivery.py](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/models/delivery.py), [models/kds.py](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/models/kds.py), [models/cash_register.py](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/models/cash_register.py), [models/alerts.py](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/models/alerts.py), [models/closing.py](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/models/closing.py)

### Adapters

Os adapters são o principal mecanismo de agnosticidade:
- payment: mock, Stripe, EFI;
- notification: ManyChat, SMS, email, console;
- catalog, stock, customer, production delegam para kernels externos.

Isso é bom porque reduz acoplamento de aplicação com infraestrutura. Mas a agnosticidade é incompleta: o pacote ainda conhece nomes e semânticas específicas de kernel em vários pontos.

Referências: [adapters/__init__.py](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/adapters/__init__.py), [adapters/payment_mock.py](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/adapters/payment_mock.py), [adapters/payment_stripe.py](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/adapters/payment_stripe.py), [adapters/payment_efi.py](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/adapters/payment_efi.py), [adapters/notification_manychat.py](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/adapters/notification_manychat.py)

## UI/UX: Omotenashi, Mobile, WhatsApp

- A experiência é pensada para decisão rápida e baixa fricção: carrinho com substitutos, checkout com progressão mínima, tracking acionável, login por telefone/OTP, confirmação de nome e notificações pelo canal preferido.
- `ManyChat` é a concretização do `WhatsApp-first`; a implementação diz explicitamente que WhatsApp sempre passa por ManyChat.
- `PWA` e `service worker` mostram uma aposta real em mobile/offline.
- `WelcomeView` é uma boa peça de onboarding: nome limpo, proteção contra open redirect, retomada do fluxo onde o usuário parou.
- `Auth` e `CustomerLookup` protegem PII e evitam exposição desnecessária.

Referências: [web/views/auth.py:53](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/web/views/auth.py:53), [web/views/welcome.py:41](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/web/views/welcome.py:41), [web/views/pwa.py:62](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/web/views/pwa.py:62), [web/views/tracking.py:1](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/web/views/tracking.py:1)

## Robustez, segurança e higiene arquitetural

### O que está bem

- `dispatch()` é explícito e sem flows legadas.
- `payment_svc.get_payment_status(order)` é o caminho canônico; há invariants testando isso.
- Há testes de segurança para headers no storefront.
- Webhooks de pagamento validam assinatura ou fazem delegação para validação no adapter.
- O checkout tem rate limit, idempotency key e validação de telefone/nome.
- O lookup de cliente só expõe PII quando a identidade está verificada.

Referências: [tests/test_invariants.py:99](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/tests/test_invariants.py:99), [tests/test_conformance.py:12](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/tests/test_conformance.py:12), [tests/test_security_headers.py](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/tests/test_security_headers.py), [webhooks/stripe.py:27](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/webhooks/stripe.py:27), [web/views/checkout.py:113](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/web/views/checkout.py:113), [web/views/auth.py:209](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/web/views/auth.py:209)

### O que está frágil

#### 1) Bug concreto em `ensure_payment_captured`

Em `lifecycle.py`, o bypass para pagamento externo tenta tratar `config.payment` como `dict`:

```python
if (config.payment or {}).get("timing") == "external":
```

Mas `config.payment` é dataclass, não dict. O `except` engole o erro e o guard pode não funcionar como esperado. Isso é um defeito de correção, não só de estilo.

Referência: [lifecycle.py:107](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/lifecycle.py:107)

#### 2) Validação de config ainda é rasa

`ChannelConfig.validate()` cobre enums básicos, mas não valida profundamente `lifecycle`, `notifications.routing`, `rules`, nem a forma completa do JSON de `Shop.defaults` e `Channel.config`.

Referência: [config.py:229](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/config.py:229)

#### 3) Cache e invalidation incompletos

`NotificationTemplate.save()` ainda marca cache invalidation como `TODO`. Isso quebra o contrato implícito de copy editável em runtime.

Referência: [models/shop.py:435](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/models/shop.py:435)

#### 4) Acoplamento com kernel e imports profundos

Apesar do discurso de agnosticidade, ainda há imports profundamente específicos de integração. O caso mais sensível dentro do pacote é o carregamento de `shopman.craftsman.contrib.stockman.handlers` no bootstrap de sinais. Isso é um acoplamento de implementação, não apenas de contrato público.

Referência: [handlers/__init__.py:246](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/handlers/__init__.py:246)

#### 5) Duplicação de lógica de tracking

Tracking tem lógica na view e na projection, o que enfraquece a promessa de `view = renderização fina sobre read model`.

Referências: [web/views/tracking.py:90](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/web/views/tracking.py:90), [projections/order_tracking.py:132](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/projections/order_tracking.py:132)

#### 6) `kind` de canal não está operacionalizado

`Channel.kind` promete comportamento por tipo de canal, mas `shopman/shop` não usa essa chave como eixo real de despacho. O comportamento vem de config, refs e canais de adapter, não de uma taxonomia viva de `kind`.

Referência: [models/channel.py:23](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/models/channel.py:23)

## Distância entre intenção e realizado

### Intenção declarada

- core enxuto;
- framework agnóstico;
- separação entre core, rules, handlers e UI;
- solution standalone para coordenar domínios de comércio;
- omotenashi-first e phone-first.

### Realizado no código

- o core é forte, mas não enxuto;
- a agnosticidade existe, porém é perfurada por muitos atalhos de domínio;
- a separação entre layers é boa em projections e services, mas ainda há duplicação e imports cruzados;
- a solução é standalone para um tipo específico de comércio, não ainda para qualquer domínio comercial;
- a UX é realmente omotenashi/WhatsApp/mobile-first, mas com bias forte para o ecossistema brasileiro de food/retail.

## O que cobre bem

- orquestração de pedidos;
- reservas e liberação de estoque;
- múltiplos timings de pagamento e fulfillment;
- notificações omnichannel com fallback;
- tracking e pós-venda;
- POS e KDS;
- onboarding e login por telefone;
- copy temporal/personalizada;
- PWA e UX de baixa fricção;
- projeções para storefront, checkout, tracking, account, dashboard e produção.

## O que ainda falha ou falta

- validação de schema profunda para `Shop.defaults`, `Channel.config` e `lifecycle`;
- migração completa de pricing para o engine de rules;
- unificação da lógica de tracking para evitar drift entre view e projection;
- remoção de imports de integração mais profundos do que o necessário;
- observabilidade operacional do pipeline de directives;
- estratégia explícita para multi-tenant / multi-store, se o objetivo é ser solução universal;
- abstração mais genérica para canais além de WhatsApp/PIX/iFood;
- fechamento do ciclo de cache/invalidation de templates editáveis;
- correção do guard de pagamento externo em `lifecycle`.

## Veredito final

`shopman/shop` já serve como orquestrador standalone para um comércio omnichannel real, especialmente no recorte brasileiro de food retail e operações com balcão, WhatsApp, PIX, KDS e fiscal. Para esse domínio, ele está acima da média em robustez e intenção arquitetural.

Mas ele ainda não é um framework universal e enxuto de comércio. O pacote carrega muito produto junto com o core. Se a meta é agnosticidade de verdade, a próxima evolução precisa reduzir a superfície própria do framework, consolidar schemas e diminuir a duplicação entre view/service/projection.

## Resumo curto

- Robustez: alta.
- Simplicidade: média.
- Elegância: boa na estrutura, irregular na execução.
- Agnosticidade: parcial.
- Onboarding: bom para o domínio alvo, pesado para uso genérico.
- Segurança: acima da média para o estágio, com um bug crítico em `ensure_payment_captured`.
- Standalone: sim, mas ainda mais como solução vertical de comércio do que como base universal de qualquer domínio.
