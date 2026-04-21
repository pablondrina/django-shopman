# Análise Profunda — Django Shopman Orquestrador + Apresentação

Data: 2026-04-21
Base: estado pós-split (shop/storefront/backstage) + SPLIT-HARDENING-PLAN pendente
Autor: Dispatch (agente Cowork)

> Objetivo: identificar o que separa o orquestrador e as superfícies do nível de maturidade dos kernels.
> Método: leitura estrutural completa de shop/, storefront/, backstage/, config/, docs/, tests/.
> Pesquisa: 5 agentes paralelos (arquitetura, UX/omotenashi, segurança, domínio, code quality) + síntese.

---

## Veredito

Os kernels (orderman, stockman, offerman, craftsman, payman, guestman, doorman) são estado-da-arte para o domínio. São densos, bem tipados, com contratos explícitos, state machines robustas e testes que cobrem edge cases reais.

O orquestrador e as superfícies ainda não estão nesse nível. Não por incompetência — por juventude. O split foi feito há 1 dia. A arquitetura é correta. Mas há lacunas que, se não fechadas, impedem o Shopman de ser o que promete: uma suíte operacional de comércio que resolve de verdade.

A seguir, os achados organizados em 8 dimensões, com nível de impacto e proposta de ação.

---

## 1. Arquitetura do Orquestrador

### 1.1 Lifecycle dispatch é sólido — mas frágil no tratamento de falha parcial

`lifecycle.py` faz o dispatch config-driven correto: `dispatch(order, phase)` → resolve `ChannelConfig` → chama serviços por fase. Mas:

- **Sem recovery em falha parcial.** Se `on_committed` faz stock hold + payment + notification, e a notification falha, não há compensação. O pedido fica com hold + payment mas sem aviso ao cliente.
- **Sem pre/post hooks.** Não há evento emitido antes/depois de cada fase. Debugging de fluxo multi-serviço exige instrumentar 10+ módulos. Falta observabilidade estrutural.
- **`production_lifecycle.py` não tem rollback.** `SubcontractFlow.on_planned` reserva materiais sem compensação se falhar depois.

**Proposta:** Result type explícito para cada fase (success/partial/failed) + compensating actions + lifecycle event emitter para observabilidade.

### 1.2 Métodos de pagamento offline são constantes Python, não config

`lifecycle.py` define `_OFFLINE_PAYMENT_METHODS = {"dinheiro", "debito", "credito"}` como constante. Adicionar um novo método (Apple Pay, vale-refeição) exige mudança de código.

**Proposta:** Migrar para `ChannelConfig.payment.offline_methods: list[str]`. Mesma prática de fulfillment e notification.

### 1.3 Handler registry não filtra por canal

`handlers/__init__.py` ALL_HANDLERS é uma lista flat. `ConfirmationTimeoutHandler` dispara independente do `confirmation.mode` do canal. Se um canal marketplace usa `mode="external"`, o handler cria directive de timeout desnecessário.

**Proposta:** Adicionar `channel_filter` ao registro de handlers; validar no `fire()`.

### 1.4 Rules engine sem isolamento por canal

`rules/engine.py` carrega regras em cache global. `get_active_rules(channel=None)` filtra em Python. Cache invalidation entre canais pode causar regra de um canal vazando para outro.

**Proposta:** Cache key por canal; invalidação atômica no `RuleConfig.save()`.

### 1.5 Adapter registry falha silenciosa

`get_adapter()` retorna `None` para adapter ausente. Serviços tratam isso de formas inconsistentes: alguns logam warning, outros continuam com dados parciais.

**Proposta:** Raise `AdapterNotConfigured` explícito. Fail early. Health check em `apps.py` no boot.

### 1.6 Contratos de serviço inconsistentes

Alguns services retornam dict, outros mutam order in-place, outros criam Directive async. `availability.decide()` retorna dict; `stock.hold()` muta; `notification.send()` cria Directive.

**Proposta:** Formalizar `ServiceResult` dataclass em `protocols.py`. Padronizar retorno.

### 1.7 ChannelConfig não tem extensibilidade

8 aspectos fixos (confirmation, payment, fulfillment, stock, notifications, pricing, editing, rules). Adicionar um 9º (analytics, subscriptions, bundles) exige código.

**Proposta:** `config.extensions: dict[str, Any]` para comportamento instance-specific. Documentar em ADR.

---

## 2. UI/UX — Omotenashi, Mobile-first, WhatsApp-first

### 2.1 Omotenashi é estrutural mas incompleto

`storefront/omotenashi/context.py` congela contexto temporal (madrugada, manhã, almoço, tarde, fechando, fechado) e pessoal (audience tier, birthday, recency) em `OmotenashiContext`. Isso é correto — hospitality é estrutura, não copy.

**Mas falta a camada de antecipação:**
- `days_since_last_order` é computado mas nunca consumido. Nenhuma view sugere reorder.
- `favorite_category` existe no slot mas retorna `None`. Nenhuma lógica popula.
- Nenhum sinal de geolocalização → "delivery rápida hoje".
- Nenhuma urgência temporal → "últimos 30 min do slot de pickup".

**Proposta:** Wiring real: popular `favorite_category` via order history; sugestão de reorder na home se `days_since_last_order > 7`; "fechamos em Xmin" como badge, não como texto estático.

### 2.2 Checkout não é projection-driven

`checkout.py` `_checkout_page_context()` monta contexto inline (78L) em vez de chamar `build_checkout()`. Mistura recuperação de dados, formatação e lógica de negócio na view. Contrasta com catalog.py que usa projections corretamente.

**Proposta:** `build_checkout_context(request, channel_ref)` como projection completa. View só renderiza.

### 2.3 Cart não detecta expiração proativamente

`cart.py` detecta sessão expirada só no POST do checkout. Um cliente pode navegar o menu inteiro com cart stale, adicionar itens silenciosamente em uma sessão nova, e perder tudo no checkout.

**Proposta:** Middleware ou context_processor que injeta `cart_session_stale: bool`. Toast no menu se stale.

### 2.4 SSE sem fallback de polling

`SkuStateView` envia badges de estoque via SSE. Se a conexão cair (rede ruim, celular), badges congelam no último estado. Sem "atualizado há X min" e sem polling automático.

**Proposta:** Client-side timeout (30s sem evento → polling a cada 2min). Badge "•" de staleness.

### 2.5 Address picker não é mobile-optimized

Checkout carrega TODAS as addresses + shop location de uma vez no Alpine. Em mobile deveria ser "selecionar salvo" → "ou novo" como stepper, não modal com tudo junto.

**Proposta:** Stepper progressivo: 1) lista salva 2) "outro endereço" → formulário. Carousel no mobile.

### 2.6 KDS e Backstage sem otimização touch/a11y

KDS views usam projections (correto), mas:
- Nenhuma referência a tamanho mínimo de toque (44×44px)
- Sem indicadores color-blind-safe (status por cor apenas)
- Sem urgência sonora (ticket parado >10 min)

**Proposta:** Design tokens para backstage: `min-touch: 44px`, status dual (cor + ícone), alerta sonoro/haptic via Tone.js ou Notification API.

### 2.7 PWA/Offline superficial

Service worker cacheia `/menu/` (stale-while-revalidate) e statics. Mas:
- Imagens de produto são network-only
- Sem lista de "favoritos" offline
- Página offline (`/offline/`) é genérica — deveria sugerir "Fale com a gente pelo WhatsApp"

**Proposta:** Cache de imagens do catálogo em SW; lista de favoritos via IndexedDB; offline page com deep link WhatsApp.

---

## 3. Segurança

### 3.1 Cart qty sem validação de tipo

`cart.py` faz `int(request.POST.get("qty", 1))` sem try-except. Input não-numérico → ValueError → 500. Vetor de DoS trivial.

**Proposta:** `try: qty = max(1, int(…)) except (ValueError, TypeError): qty = 1`

### 3.2 Checkout address sem ownership check explícito

`checkout.py:317-334`: `saved_address_id` é usado para buscar endereço sem verificar ownership explicitamente no fluxo. O ORM escopa por customer (mitigação), mas inconsistente com account.py que faz a verificação.

**Proposta:** Chamar `address_service.get_address(customer_ref, address_id)` que já filtra.

### 3.3 Notes e Name sem max_length

`checkout.py:237`: `notes = request.POST.get("notes", "").strip()` sem limite de tamanho. Pode injetar strings gigantes no `order.data`.

**Proposta:** `notes[:500]`, `name[:200]` — truncar server-side.

### 3.4 Webhooks são exemplares

EFI (mTLS + HMAC), Stripe (signature verify), iFood (HMAC + dedup por external_ref). Sem modo skip-signature. Idempotência em todos. Este é o nível que o resto deveria ter.

### 3.5 LGPD bem implementada

DataExportView exporta tudo (perfil, endereços, pedidos, preferências, consentimentos, loyalty). AccountDeleteView anonimiza (hash phone, revoga consentimentos, deleta endereços, is_active=False). ConsentService com base legal.

---

## 4. Robustez e Concorrência

### 4.1 Sem circuit breaker para APIs externas

Geocoding, payment gateways, ManyChat — todos chamados diretamente sem circuit breaker. Se a API de geocoding cai, cada request de checkout trava esperando timeout.

**Proposta:** Adapter wrapper com circuit breaker (tenacity ou custom). Fallback gracioso.

### 4.2 Sem validação de startup

Nenhuma verificação automática no boot de que:
- `HOLD_TTL_MINUTES > PIX_TIMEOUT_MINUTES + buffer`
- Payment gateway keys estão configuradas
- Notification backend está alcançável
- Adapters obrigatórios resolvem

**Proposta:** Django system checks em `apps.py`. Deploy falha se invariante quebra.

### 4.3 Error handling inconsistente entre camadas

- Services: `try/except Exception` + `logger.error()` + armazena em `order.data` → consistente
- Storefront views: `try/except Exception:` + `logger.exception()` → swallows, sem re-raise
- Backstage views: `except InvalidTransition` (específico) + `except Exception` (genérico) → mais consistente

**Proposta:** Padronizar: exceptions de domínio (catch específico) vs. operacionais (log + render error). Nunca swallow silencioso.

---

## 5. Multi-canal: Distância entre promessa e realidade

### 5.1 WhatsApp é canal de notificação, não de pedido

ChannelConfig suporta `kind="whatsapp"`. ManyChat adapter envia mensagens. Mas:
- Não há ingestão de mensagens (inbound)
- Não há state machine de conversa (menu → adicionar → checkout)
- Não há geração de link de pagamento para enviar no chat
- Não há catálogo interativo (product cards, botões)

**O WhatsApp hoje é 1-way: sistema → cliente. Não existe cliente → sistema.**

**Proposta:** `adapters/channel_whatsapp.py` com `route_message(phone, text)` → parser de intenção → `ModifyService` / `CommitService`. Webhook `/api/webhooks/whatsapp/`. Zero mudança nos kernels.

### 5.2 Marketplace é shallow

iFood ingest cria Order a partir de payload. Mas:
- Catálogo não sincroniza bi-direcional (preço muda no Shopman, iFood não atualiza)
- Aceitação/rejeição do operador não notifica iFood via callback
- Taxas do marketplace não são descontadas (receita mostra bruto, não líquido)
- Zero suporte Rappi/Uber Eats

**Proposta:** Adapter genérico `MarketplaceAdapter` com `sync_catalog()`, `accept_order()`, `reject_order()`, `report_ready()`. iFood como primeira implementação.

### 5.3 API insuficiente para app mobile e chatbot

A API storefront é session-cookie-based. Para mobile:
- Sem auth token flow (JWT/device token)
- Sem push notification endpoint (Firebase)
- Sem batch endpoints (10 produtos em 1 call)
- Sem sparse fieldsets

Para chatbot:
- Sem endpoint de "favoritos/mais pedidos"
- Sem "posso pedir isso amanhã?" (availability com target_date)
- Sem one-click reorder

**Proposta:** API v2 com token auth, batch support, push registration, reorder endpoint.

---

## 6. Gaps de Domínio — O que falta para operação real

### 6.1 Delivery & Logistics (CRÍTICO)

DeliveryZone calcula taxa estática. Não existe:
- Gestão de entregadores/motoristas
- Rastreamento em tempo real
- Estimativa de tempo de entrega
- Integração com transportadoras (Loggi, Lalamove)
- SLA de entrega

**Impacto:** Bloqueio para qualquer operação além de pickup ou delivery própria.

### 6.2 Inventory Planning (CRÍTICO)

StockMan gerencia holds e availability. Não existe:
- Previsão de demanda
- Rastreamento de desperdício (perecíveis!)
- Par levels automáticos (compra automática quando estoque baixo)
- Multi-local (warehouse + loja)
- Gestão de fornecedores / PO

**Impacto:** Comércio de alimentos perde controle de custo sem rastreamento de desperdício.

### 6.3 Refund incompleto

PayMan faz refund do intent. Mas:
- Pontos de loyalty ganhos NÃO são revertidos
- Estoque NÃO é re-adicionado automaticamente
- NFC-e de cancelamento NÃO gera débito fiscal automático

**Proposta:** `CancellationService.on_refund()` que orquestra: refund + loyalty reversal + stock release + fiscal reversal.

### 6.4 Caixa simplista

DayClosing é snapshot. Faltam:
- Over/short (diferença contado vs. sistema)
- Histórico de transações por turno
- Reconciliação automática
- Sangria/reforço com rastreio de quem

**Proposta:** `CashRegisterService` com event log (abertura, venda, sangria, reforço, fechamento) e conferência.

### 6.5 Analytics inexistente

DashboardProjection tem KPI cards básicos (pedidos hoje, receita). Faltam:
- Top 10 produtos (qty/receita)
- Margem por produto (custo não existe)
- Ticket médio, itens por pedido
- Análise de horário de pico
- Taxa de cancelamento por canal/motivo
- Eficiência do KDS (tempo pedido → pronto)

**Proposta:** Módulo `analytics/` com projections agregadas. Dashboard backstage com filtros.

### 6.6 Segmentação de clientes inexistente

LoyaltyService é transacional (1 ponto/R$1, resgate). Não existe:
- Segmentação por frequência/valor (VIP, regular, one-time)
- Detecção de churn (último pedido >30 dias)
- Campanhas (SMS para "regulares que não pediram em 2 semanas")
- Tiered loyalty (bronze/silver/gold)
- Referral program

**Proposta:** `guestman.contrib.segmentation` com RFM scoring + segment triggers.

---

## 7. Documentação e Developer Experience

### 7.1 Documentação boa mas com gaps críticos

Existe e é boa:
- `CLAUDE.md` — completo
- `docs/guides/lifecycle.md` — 10 fases claras
- `docs/reference/data-schemas.md` — inventário exaustivo de JSONFields
- `docs/reference/glossary.md` — 92 termos

Falta:
- **Production Checklist** — env vars obrigatórias, Redis, PostgreSQL, CSRF origins, Sentry
- **Error Codes Reference** — decisão tree para mensagens client-facing vs. system
- **Adapter Contracts** — quais são prod-ready vs. mock; fallback chain ordering
- **Handler Execution Order** — quem ganha se dois handlers escrevem no mesmo campo
- **"How to Add X" guides** — nova view, novo handler, novo adapter, nova fase

### 7.2 Testes: cobertura forte, gaps em edge cases

1.436 testes. Mas faltam:
- Cancelamento parcial (múltiplos itens, cancel mid-webhook)
- Payment timeout + duplicate webhook race
- Notification failure → OperatorAlert escalation
- DeliveryZone fallback quando geocoding offline
- iFood webhook out-of-order delivery

### 7.3 Sem Sentry/monitoring

`config/settings.py` não configura Sentry, Datadog, ou qualquer error tracking. Deploy sem observabilidade.

---

## 8. Falhas fundamentais que ninguém enxergou

### 8.1 O sistema não tem conceito de "promessa ao cliente"

Quando o checkout confirma, o que exatamente foi prometido? O sistema cria order + holds + payment intent, mas não existe um objeto `Promise` ou `Commitment` que congele:
- Preço prometido (se o preço mudar entre checkout e confirm)
- Horário prometido (se o slot expirar)
- Estoque prometido (se o hold for liberado por timeout)

Cada serviço gerencia sua parte, mas não há snapshot atômico de "o que o cliente espera receber".

**Proposta:** `OrderCommitment` snapshot criado no commit, imutável, referenciado em disputas/reclamações.

### 8.2 Não há plano B quando o sistema cai

Se Redis cai, rate limiting desliga silenciosamente. Se banco cai, nada funciona. Se ManyChat cai, notificação some.

Não existe:
- Degradação graceful documentada
- Playbook de incident response
- Fallback offline (operador imprimir pedido manualmente)
- Health check endpoint

**Proposta:** `/health/` endpoint; degradation matrix (se X cai, Y funciona assim); alerts para operador.

### 8.3 O modelo Shop é singleton — e isso limita tudo

`Shop.load()` retorna uma instância única. Multi-loja exige instâncias Django separadas. Sem:
- Consolidação financeira entre lojas
- Catálogo compartilhado multi-marca
- Dashboard de rede

Para um sistema que aspira ser "suíte de comércio", singleton é teto.

---

## Resumo: O que fazer?

### Impacto máximo / esforço moderado (próximo sprint)

1. **Validação de startup** — Django system checks em apps.py (4h)
2. **Cart qty safe parsing** + max_length em inputs (2h)
3. **Lifecycle Result type** + compensating actions (8h)
4. **Payment methods config-driven** (4h)
5. **Handler channel_filter** (4h)
6. **Omotenashi wiring** — reorder suggestion, favorite_category, urgência temporal (8h)
7. **SSE fallback polling** (4h)

### Impacto máximo / esforço alto (próximo mês)

8. **WhatsApp ordering adapter** — inbound + state machine + payment link (40h)
9. **Marketplace adapter genérico** — catalog sync, accept/reject (32h)
10. **Analytics module** — top products, ticket médio, KDS efficiency (40h)
11. **Customer segmentation** — RFM scoring, churn detection (24h)
12. **OrderCommitment snapshot** — freeze preço/slot/estoque no commit (16h)

### Transformacional (trimestre)

13. **Delivery orchestration** — entregadores, tracking real-time, ETA
14. **Inventory planning** — forecasting, waste, par levels, POs
15. **API v2** — token auth, batch, push, chatbot endpoints
16. **Multi-store** — Shop não-singleton, consolidação
