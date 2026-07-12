# Changelog

Todas as mudanças notáveis neste projeto serão documentadas aqui.
Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

Entre releases, este arquivo registra **marcos** (não commit-a-commit). O estado
factual detalhado vive em [docs/status.md](docs/status.md); o corte da próxima
release (v1 / go-live) está em
[docs/plans/GO-LIVE-READINESS-PLAN.md](docs/plans/GO-LIVE-READINESS-PLAN.md).

## [Unreleased] — marcos desde 0.1.0-alpha (abril → julho/2026)

### Arquitetura
- **Cutover headless completo**: os apps Django `storefront`/`backstage` deixaram de
  renderizar HTML e passaram a servir API JSON + projections; as superfícies vivas
  são 6 apps Nuxt 4 SSR (`surfaces/`: loja, hub, POS, KDS, gestor, produção) + a
  layer compartilhada `operator-kit`, falando com o Django via BFF Nitro e cookie de
  sessão cross-subdomínio (ADR-012/ADR-014).
- **Django 6** como contrato canônico (`>=6.0,<6.1`); PostgreSQL 16 + Redis 7 como
  runtime canônico, com Runtime Gate no CI (sem skips) e Surfaces Gate (typecheck Nuxt).
- **Tempo real SSE-first** site-wide (ADR-016): push por SSE sobre fetch canônico,
  poll só como fallback.
- **Core expandido para 11 pacotes**: novos `shopman-refs` (refs tipadas),
  `shopman-buyman` (compras, Fase 1) e `shopman-fiscalman` (classificação NFC-e).
- Suite de testes cresceu de ~1.900 para **~5.000** (~2.150 cores + ~2.870 framework).

### Superfícies de operador
- POS Nuxt desktop-first (tabs, turno, caixa, fire-to-kitchen, impressão), KDS com
  estações e painel de retirada, Gestor de pedidos (fila, cardápio, showcases),
  Produção/fornadas (kiosk Solari) e Central de Apps; login 1× cross-subdomínio,
  lock por operador (PIN/crachá) com autoatendimento de PIN e reset por gerente.
- Fechamento do dia com reconciliação financeira diária; checklists operacionais.

### Cliente e canais
- Storefront Nuxt no apex (mobile-first, theming, SEO técnico, PWA-ready).
- **Auth WhatsApp-first por access link** (`NB-XxXx`); reverse-OTP aposentado;
  SMS fallback, magic links, device trust.
- **iFood direto** (polling + sync de catálogo) em staging; **Machine** (logística
  externa/courier) integrada aguardando credenciais; zonas de entrega + geocoding
  em cascata.
- **Copy omotenashi**: registro `OmotenashiCopy` como fonte única configurável;
  burndown fechado com backlog zerado.

### Fiscal e compras
- Fiscalman S0–S4: classificação NFC-e por produto, emissão via Focus NFe (homolog).
- Buyman Fase 1: materiais, fornecedores, custos; guardrail de disponibilidade de
  insumo ligado na produção (`INVENTORY_BACKEND`).

### Confiabilidade (hardening pré-alpha, 2026-07-11)
- 16 PRs (#53–#69) a partir de
  [docs/reports/analise_pre_alpha_2026-07-11.md](docs/reports/analise_pre_alpha_2026-07-11.md):
  gate transacional de estoque no commit (anti-oversell), dialeto canônico de erro
  `{detail, field, errors}`, directives com dedupe garantido e observabilidade,
  correções tz-aware, POS anti-fraude de preço, suíte hermética, rotas de operador
  e chaves de projection em inglês, baseline selado do Orderman com cópias.

### Infra
- Staging na DigitalOcean App Platform (ingress por subdomínio, Managed
  PostgreSQL 16 + Valkey, release job + directive worker); deploy encapsulado
  por `make deploy-*`.

## [0.1.0-alpha] — 2026-04-06

Primeira release alpha. Inclui o ecossistema completo: 8 core apps independentes,
framework orquestrador, storefront, POS, KDS e instancia Nelson Boulangerie.

### Adicionado

**Core Apps (packages/)**
- 8 apps pip-instalaveis independentes: offerman (catalogo), stockman (estoque), craftsman (producao), omniman (pedidos), guestman (clientes), doorman (auth), payman (pagamentos), utils (utilitarios)
- Offerman: produtos, precos, listings, colecoes, bundles
- Stockman: quants, moves, holds, posicoes, alertas, planejamento de estoque
- Craftsman: receitas, work orders, BOM, sugestao de producao
- Omniman: sessions, orders, channels, directives, fulfillment com handler registry e retry
- Guestman: customers, contatos, grupos, loyalty, segmentacao RFM
- Doorman: OTP via WhatsApp/SMS, device trust, bridge tokens, magic links, rate limiting
- Payman: payment intents, transactions, service com transicoes de estado

**Framework Orquestrador (shopman/shop/)**
- Flows: BaseFlow, LocalFlow, RemoteFlow, MarketplaceFlow com dispatch por signal
- 11 services: stock, payment, customer, checkout, pricing, confirmation, fiscal, accounting, notifications, returns, catalog
- 8 adapters swappable: payment_efi, payment_stripe, notification (WhatsApp/SMS/email), stock_internal
- Rules engine: regras configuraveis via admin com RuleConfig no DB
- CommitService: contrato Session para Order com propagacao de chaves
- Directive dispatch com management command e handler registry
- Webhooks para Efi e Stripe
- Channel presets com post_commit_directives

**Storefront Web (HTMX + Alpine.js)**
- Catalogo com listagem de produtos e busca
- Carrinho com descontos visiveis (D-1, employee, happy hour)
- Checkout completo com PIX e cartao (Stripe)
- Checkout dual-mode: seamless para logados, phone-first para anonimos
- Tracking de pedidos em tempo real
- Alternativas quando produto esgotado
- Loyalty: resgate de pontos no checkout
- Delivery zones com calculo de taxa por regiao
- PWA: offline, cache routing, push stubs

**POS (Ponto de Venda)**
- Layout dedicado com design tokens Oxbow
- Atalhos de teclado para operacao rapida
- Desconto manual e observacao por item
- Badge D-1 e desconto funcionario visual
- Resumo de turno e gestao de caixa
- Cancelamento de pedidos

**KDS (Kitchen Display System)**
- Dispatch por estacao com timers e controle de status

**Integracao Plena**
- Vendas, producao, estoque e CRM integrados end-to-end
- Confirmacao otimista de pedidos (auto-confirm se operador nao cancela)

**Auth e Seguranca**
- PhoneOTPBackend com login/logout e WhatsApp-first com fallback SMS
- Middleware request.customer com dual-write
- Device management com admin
- Fallback chain para endereco de entrega
- Security headers: CSP, HSTS, X-Frame-Options, nosniff
- Rate limiting para OTP e checkout
- CSRF trusted origins para ngrok/acesso externo

**Admin**
- StorefrontConfig: branding configuravel via Admin
- Notification templates DB-driven com fallbacks hardcoded
- HappyHour times, PIX expiry, ProcessedEvent cleanup configuraveis
- Dashboard, alertas, KDS, fechamento de caixa, regras

**Instancia Nelson Boulangerie**
- Seed command para popular banco com dados de padaria artesanal

**Infraestrutura**
- Monorepo: packages/ (core apps) + shopman/shop/ (orquestrador) + config/ + instances/ (Nelson)
- ~1.900 testes (1.531 core + 370 framework) incluindo integracao, e2e e stress tests
- OpenAPI via drf-spectacular
- Documentacao completa: guias, ADRs, glossario, referencia de schemas

### Corrigido

- Carrinho preservado across login e logout (protecao contra session flush)
- Endereco de entrega estruturado propagado via CommitService
- Metodo de entrega passado corretamente ao sender (era hardcoded whatsapp)
- Redirect apos 'Trocar conta' volta ao checkout, nao ao homepage
- Clientes persistidos em checkout anonimo
- Queries N+1 eliminadas em _annotate_products() com batch queries
- Thread safety em servicos compartilhados
- Logging adicionado a todos os blocos except silenciosos em views
- Testes de concorrencia para stock, payment e work orders

### Alterado

- Nomenclatura interna unificada: `ref` em vez de `code` (exceto Product.sku)
- Valores monetarios em centavos com sufixo `_q`
- Views refatoradas em package views/ (split de arquivo monolitico)
- Renaming completo das apps internas (Craftsman->Crafting, Stockman->Stocking, Offerman->Offering)
- Services stock->inventory e customer->identification no orquestrador
- Estrutura monorepo: shopman-core->packages, shopman-app->framework+instances
- App unico shopman/ consolidado (channels/+shop/ -> shopman/)

### Removido

- Diretorio contrib/ — handlers migrados para AppConfig de cada modulo
- Diretorios legados apos reestruturacao monorepo
- Aliases de backward-compat (projeto novo, zero consumidores externos)
