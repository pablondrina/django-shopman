# Status — Django Shopman

> Última atualização: 2026-05-04

Retrato factual do que está implementado e funcionando. Não é um plano — é o estado atual.
Para gaps e roadmap, ver [ROADMAP.md](ROADMAP.md) e os planos ativos em `docs/plans/`.

---

## Core Apps (packages/)

| Package | Pip | Versão | Testes | Status | Notas |
|---------|-----|--------|--------|--------|-------|
| shopman-utils | `shopman-utils` | 0.3.0 | coleta global | Estável | Monetário, phone, formatting, admin mixins |
| shopman-refs | `shopman-refs` | 0.1.0 | coleta global | Estável | Registro de refs tipadas, rename/audit, fields |
| shopman-offerman | `shopman-offerman` | 0.3.0 | coleta global | Estável | Catálogo, preços, listings, bundles, coleções |
| shopman-stockman | `shopman-stockman` | 0.3.0 | coleta global | Estável | Estoque, holds, moves, posições, alertas |
| shopman-craftsman | `shopman-craftsman` | 0.3.0 | coleta global | Estável | Produção, receitas, work orders, BOM |
| shopman-orderman | `shopman-orderman` | 0.1.0 | coleta global | Estável | Pedidos, sessions, directives, channels |
| shopman-guestman | `shopman-guestman` | 0.1.0 | coleta global | Estável | CRM, clientes, loyalty, RFM, consent |
| shopman-doorman | `shopman-doorman` | 0.1.0 | coleta global | Estável | Auth OTP, device trust, bridge tokens |
| shopman-payman | `shopman-payman` | 0.2.0 | coleta global | Beta | Pagamentos, PIX, Stripe — cobertura parcial |

**Coleta atual:** 717 testes (`pytest --collect-only -q`, 2026-04-26).

---

## Framework (framework/)

| Módulo | Status | Detalhe |
|--------|--------|---------|
| **Lifecycle** (pedidos) | Estável | dispatch funcional config-driven via `ChannelConfig` e signal `order_changed`; sem classes `Flow` |
| **Services** | Estável | 13 services (checkout, payment, stock, customer, loyalty, etc.) |
| **Adapters** | Estável | 8 adapters (EFI/PIX, Stripe, ManyChat, email, console, stock interno, mock) |
| **Handlers** | Estável | 15 handlers de directives (stock, payment, notification, fulfillment, etc.) |
| **Rules engine** | Estável | Promotions, coupons, modifiers — configurável via admin |
| **Storefront (web/API)** | Beta | App próprio `shopman/storefront/`, views/projections/templates/API v1 |
| **Admin (Unfold)** | Estável | Dashboard, shop config, pedidos, KDS operacional, produção, fechamento e alertas |
| **Runtime operacional** | Beta | POS e KDS de produção como superfícies próprias, fora do Admin por necessidade operacional |

**Total geral coletado: 717 testes**

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

Ver [ROADMAP.md](ROADMAP.md) para gaps conhecidos e plano de correção:

- **C1** — blocos `except Exception` silenciosos remanescentes fora do escopo WP-02
- **C2** — Thread safety no adapter EFI + cobertura de testes baseline
- **C4** — Security headers (CSP, HSTS) ausentes
- **C5** — Queries N+1 no storefront (catalog, cart, tracking)
- **C6** — Testes de concorrência (stock, payment, work orders)
- **C7** — Payman: cobertura de testes insuficiente
- **C8** — Checkout dedup: lógica duplicada fora do CommitService

Ver [ROADMAP.md](ROADMAP.md) e `docs/plans/` para itens de UX/operação:

- **R3-R8** — Storefront: empty states, feedback de erros, responsividade mobile
- **R14** — Rate limiting (OTP, login, checkout) — concluído em WP-C3
- **R17** — Security headers

---

## Compatibilidade

| Requisito | Versão |
|-----------|--------|
| Python | ≥ 3.12 |
| Django | ≥ 5.2, < 6.0 — upgrade coordenado para 6.0 planejado |
| Node.js | ≥ 18 (build Tailwind CSS) |
| Banco de dados | PostgreSQL 16+ no dev canônico/staging/prod; SQLite só fallback local |
| Cache/realtime | Redis 7+ no dev canônico/staging/prod; LocMem só fallback local |

Ver contrato completo em [runtime-dependencies.md](reference/runtime-dependencies.md).
