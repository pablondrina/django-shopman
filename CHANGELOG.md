# Changelog

Todas as mudancas notaveis neste projeto serao documentadas aqui.
Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

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

**Framework Orquestrador (framework/)**
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
- Monorepo: packages/ (core apps) + framework/ (orquestrador) + instances/ (Nelson)
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
