# Status — Django Shopman

> Última atualização: 2026-05-05

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
| shopman-payman | `shopman-payman` | 0.2.0 | coleta global | Beta | Pagamentos, PIX, Stripe, reconciliação cumulativa — cobertura parcial |

**Último gate local completo:** `make test` em SQLite/LocMem, 2026-05-05:
`1829 passed`, `13 skipped`, `3 warnings`, `14 subtests`.

**Gate runtime real:** `make test-runtime` criado em 2026-05-05 para
PostgreSQL + Redis. Ele falha se PostgreSQL/Redis não estiverem acessíveis ou
se qualquer teste sensível for pulado. Evidência registrada no PR #3:
`Runtime Gate` `25375581090` passou em 2026-05-05, com `PostgreSQL + Redis
runtime stress gate` verde em 1m29s.

**CI sem Docker local:** workflow `Runtime Gate` criado em 2026-05-05. Ele
builda a imagem Docker no GitHub Actions, sobe PostgreSQL/Redis, roda a suite
completa e executa `make test-runtime`; o operador local nao precisa rodar
Docker. No run `25375581090`, a job `Docker deploy image` passou em 1m28s.

**Deploy encapsulado:** `Dockerfile`, compose profiles e targets `make deploy-*`
existem para build/release/web/worker sem exigir comandos Docker manuais.

**Observabilidade operacional:** logs JSON opcionais por `SHOPMAN_JSON_LOGS`,
eventos estruturados para reconciliação/webhooks e alertas `webhook_failed` /
`payment_reconciliation_failed` no Backstage.

**Django 6:** o contrato canônico agora é `Django>=6.0,<6.1`. O canário local
em ambiente isolado validou Django 6.0.5 com `django-unfold 0.92.0`, DRF
3.17.1, `django-import-export 4.4.1`, `django-filter 25.2`, `redis 7.4.0` e
suite completa após atualizar o inventário Unfold canônico.

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

**Total do último gate local completo:** `1829 passed`, `13 skipped`,
`3 warnings`, `14 subtests`.

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

- **Gateways sandbox** — validar EFI/Stripe/iFood com eventos duplicados,
  atrasados e fora de ordem.
- **Reconciliação financeira** — provar rotina diária para pedido, intent,
  transações, gateway, refund e fechamento.
- **Observabilidade** — logs estruturados, health/readiness, monitoramento de
  webhooks e alertas operacionais.
- **QA manual Omotenashi** — mobile cliente, tablet KDS e desktop gerente.

Ver [ROADMAP.md](ROADMAP.md) e `docs/plans/` para itens de UX/operação:

- **R3-R8** — Storefront: empty states, feedback de erros, responsividade mobile
- **Django 6** — migrado para `Django>=6.0,<6.1`; manter matrix de dependências
  atualizada a cada bump de Unfold/DRF/Django.

---

## Compatibilidade

| Requisito | Versão |
|-----------|--------|
| Python | ≥ 3.12 |
| Django | ≥ 6.0, < 6.1 |
| Node.js | ≥ 18 (build Tailwind CSS) |
| Banco de dados | PostgreSQL 16+ no dev canônico/staging/prod; SQLite só fallback local |
| Cache/realtime | Redis 7+ no dev canônico/staging/prod; LocMem só fallback local |

Ver contrato completo em [runtime-dependencies.md](reference/runtime-dependencies.md).
