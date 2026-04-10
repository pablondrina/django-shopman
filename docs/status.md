# Status — Django Shopman

> Última atualização: 2026-04-06

Retrato factual do que está implementado e funcionando. Não é um plano — é o estado atual.
Para gaps e roadmap, ver [CORRECTIONS-PLAN.md](../CORRECTIONS-PLAN.md) e [READINESS-PLAN.md](../READINESS-PLAN.md).

---

## Core Apps (packages/)

| Package | Pip | Versão | Testes | Status | Notas |
|---------|-----|--------|--------|--------|-------|
| shopman-utils | `shopman-utils` | 0.3.0 | 71 | Estável | Monetário, phone, formatting, admin mixins |
| shopman-offerman | `shopman-offerman` | 0.3.0 | 188 | Estável | Catálogo, preços, listings, bundles, coleções |
| shopman-stockman | `shopman-stockman` | 0.3.0 | 162 | Estável | Estoque, holds, moves, posições, alertas |
| shopman-craftsman | `shopman-craftsman` | 0.3.0 | 207 | Estável | Produção, receitas, work orders, BOM |
| shopman-orderman | `shopman-orderman` | 0.1.0 | 231 | Estável | Pedidos, sessions, directives, channels |
| shopman-guestman | `shopman-guestman` | 0.1.0 | 369 | Estável | CRM, clientes, loyalty, RFM, consent |
| shopman-doorman | `shopman-doorman` | 0.1.0 | 221 | Estável | Auth OTP, device trust, bridge tokens |
| shopman-payman | `shopman-payman` | 0.1.0 | 111 | Beta | Pagamentos, PIX, Stripe — cobertura parcial (WP-C7) |

**Total core:** 1.560 testes

---

## Framework (framework/)

| Módulo | Status | Detalhe |
|--------|--------|---------|
| **Flows** (lifecycle de pedidos) | Estável | 10 classes de flow, dispatch via signal `order_changed` |
| **Services** | Estável | 13 services (checkout, payment, stock, customer, loyalty, etc.) |
| **Adapters** | Estável | 8 adapters (EFI/PIX, Stripe, ManyChat, email, console, stock interno, mock) |
| **Handlers** | Estável | 15 handlers de directives (stock, payment, notification, fulfillment, etc.) |
| **Rules engine** | Estável | Promotions, coupons, modifiers — configurável via admin |
| **Storefront (web)** | Beta | 18 módulos de views, 80 templates — UX em polish (READINESS R3-R8) |
| **API REST (DRF)** | Beta | Endpoints core prontos; account/history incompletos |
| **Admin (Unfold)** | Estável | Dashboard, shop config, orders, KDS, alertas, fechamento de caixa |

**Framework:** 410 testes

**Total geral: 1.970 testes**

---

## Fluxos Validados

- Pedido local (POS): commit → confirmação otimista → KDS → fulfillment
- Pedido remoto (storefront): cart → checkout → PIX → polling → confirmação → tracking
- Notificações: WhatsApp (ManyChat), email, console — swappable por adapter
- Estoque: hold na criação → deduct na confirmação → release no cancelamento
- Produção: receitas → work orders → BOM → dedução de insumos
- Loyalty: acúmulo de pontos na confirmação, resgate no checkout
- Auth OTP: WhatsApp-first com fallback, device trust, magic links
- Fechamento do dia: sobras, D-1, apuração de caixa

---

## Gaps Conhecidos

Ver [CORRECTIONS-PLAN.md](../CORRECTIONS-PLAN.md) para o plano de correção ativo:

- **C1** — 42 blocos `except Exception` silenciosos nas views (sem logging)
- **C2** — Thread safety no adapter EFI + cobertura de testes baseline
- **C4** — Security headers (CSP, HSTS) ausentes
- **C5** — Queries N+1 no storefront (catalog, cart, tracking)
- **C6** — Testes de concorrência (stock, payment, work orders)
- **C7** — Payman: cobertura de testes insuficiente
- **C8** — Checkout dedup: lógica duplicada fora do CommitService

Ver [READINESS-PLAN.md](../READINESS-PLAN.md) para itens de UX/operação:

- **R3-R8** — Storefront: empty states, feedback de erros, responsividade mobile
- **R14** — Rate limiting (OTP, login, checkout) — concluído em WP-C3
- **R17** — Security headers

---

## Compatibilidade

| Requisito | Versão |
|-----------|--------|
| Python | ≥ 3.11 |
| Django | ≥ 5.2, < 6.0 |
| Node.js | ≥ 18 (build Tailwind CSS) |
| Banco de dados | SQLite (dev) / PostgreSQL (prod recomendado) |
