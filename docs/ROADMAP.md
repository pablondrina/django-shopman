# ROADMAP — Django Shopman

> Próximos passos e ideias futuras. Atualizado em 2026-03-25.

---

## Estado Atual

Planos completos (arquivados em `docs/plans/completed/`):
- **REFACTOR-PLAN** (WP-0 a WP-R5) — Reestruturação de 8 core apps
- **CONSOLIDATION-PLAN** (WP-C1 a WP-C6) — Consolidação pós-refatoração
- **HARDENING-PLAN** (WP-H0 a WP-H5) — Hardening arquitetural
- **BRIDGE-PLAN** (WP-B1 a WP-B7) — Alinhamento Core ↔ App
- **RESTRUCTURE-PLAN** / **WORKPACKAGES** — Planos originais de reestruturação

O App está funcional como MVP: storefront completo (menu → cart → checkout → PIX → tracking),
3 presets de canal, pipeline de pedidos flexível, ~1.878 testes.

---

## Próximos Passos (por prioridade)

### P1 — Disponibilidade + Alternativas no Storefront

Trazer o sistema de verificação de disponibilidade e sugestão de alternativas para a UI do cliente.

**O que já existe no backend:**
- `StockingBackend.check_availability()` + `get_alternatives()`
- `StockHoldHandler._build_issue()` com alternatives + actions
- `offering.contrib.suggestions.find_alternatives()` (scoring por keywords + coleção + preço)
- `_helpers.py` com `_get_availability()` e `_availability_badge()`
- Availability policies: `stock_only`, `planned_ok`, `demand_ok`
- Integração Crafting: holds planejados materializados via `holds_materialized` signal

**O que falta (UI):**
- PDP: feedback inline de disponibilidade antes de adicionar ao carrinho
- PDP: seção de alternativas (colapsável, expande quando indisponível)
- Carrinho: warnings inline por item com ações (Ajustar qty, Ver Alternativas, Remover)
- Pré-checkout: validação suave com resolução 1-click

**Referência:** `~/Dev/Claude/refs/shopman-demo/docs/AVAILABILITY_UX_ANALYSIS.md`

---

### P2 — Loyalty na UI

Ativar o sistema de fidelidade do Core no App.

**O que já existe no Core:**
- `LoyaltyAccount` (pontos, stamps, tiers automáticos BRONZE→PLATINUM)
- `LoyaltyTransaction` (ledger imutável: earn, redeem, stamp, adjust, expire)
- `LoyaltyService` (enroll, earn_points, redeem_points, add_stamp, com select_for_update)
- Admin completo, testes, config de tiers

**O que falta:**
- Instalar `shopman.customers.contrib.loyalty` no INSTALLED_APPS
- Handler que dá pontos ao completar pedido (ex: 1 ponto por R$1)
- Seção loyalty na conta do cliente (pontos, tier badge, stamps, histórico)
- Opcional: resgate de pontos como modifier no checkout

---

### P3 — Pagamento com Cartão no Storefront

**O que já existe:**
- `StripeBackend` (`payment_stripe.py`) funcional
- `StripeWebhookView` implementado
- `ChannelConfig.Payment` aceita `method="card"`

**O que falta:**
- Seletor de método de pagamento no checkout (PIX vs Cartão)
- Template com Stripe Elements para input de cartão
- Routing pós-confirmação por método (PIX → QR, Card → Stripe confirmation)

---

### P4 — Dashboard do Operador

Pedidos do dia, fila de produção, alertas de estoque. Sem isso, o operador depende do Django Admin puro.

**Opções:**
- Unfold admin customizado (mais rápido, dentro do Django)
- Views dedicadas mobile-first (mais trabalho, melhor UX)

---

### P5 — Notificações Transacionais Reais

Os backends de email/SMS/WhatsApp existem mas são stubs ou semi-implementados.

**Mínimo para produção:**
- Email transacional funcional (confirmação, tracking, PIX expirado)
- Stock alerts → notificação para operador

---

### P6 — API REST Completa

Expor catálogo, tracking, conta, histórico via REST para viabilizar mobile e integrações.

---

## Refatorações Estruturais

| Item | Descrição | Prioridade |
|------|-----------|------------|
| Promotions → core app | Promotion e Coupon hoje vivem em `shop/models.py` (app layer). São entidades de domínio puras com referências soft (JSONField) a SKUs e collections — sem FK cruzada. Mesmo padrão de Loyalty em `customers/`: modelos no core, lógica de aplicação (modifiers, pipeline) permanece no app. App se chamaria `promotions/` com Promotion + Coupon; `shop/modifiers.py` continuaria no app layer. | Baixa — funciona bem no app layer, mas ganha reutilização se promovido |

---

## Nice-to-Have (futuro)

| Item | Descrição |
|------|-----------|
| Variantes de produto | Tamanho, sabor, etc. (ex: Café P/M/G) |
| Assinaturas/recorrência | Pedido semanal automático |
| Gift cards | Crédito pré-pago |
| Reviews/ratings | Avaliação de produtos pelo cliente |
| Analytics/attribution | GA4, eventos de conversão |
| Newsletter | Cadastro + campanhas |
| Social proof | "12 pessoas compraram hoje" |
| i18n multi-idioma | Suporte além de pt-BR |
| Busca facetada | Filtros por preço, tags, atributos |
| Endereços salvos no checkout | Quick-select de endereços cadastrados |
| Reordenar pedido anterior | 1-click para repetir pedido |
| Devoluções (fluxo completo) | Handler existe, UI não |
| Push notifications | PWA stubs prontos, falta backend |
| Pagamento no balcão (counter) | UI para operador marcar como pago |
| Passkeys / WebAuthn | Auth device-bound, immune a SIM swap e phishing. Exige hardware compatível. Ideal quando base de clientes escalar e perfil de risco justificar. Complementa OTP phone-first como segundo fator ou substituto. |
| django-allauth phone adapter | Avaliar migração do auth custom para django-allauth com phone adapter. Ganha: social login, email+phone unificado, ecosystem de providers, manutenção comunitária. Custo: adaptar Customer↔User bridge, testar com storefront HTMX. |
