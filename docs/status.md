# Status — Django Shopman

> Última atualização: 2026-07-11

Retrato factual do que está implementado e funcionando. Não é um plano — é o estado atual.
Para gaps e roadmap, ver [ROADMAP.md](ROADMAP.md) e os planos ativos em `docs/plans/`.

---

## Arquitetura atual (headless)

O cutover headless está **completo**: os apps Django `storefront` e `backstage` não
renderizam HTML de superfície — servem **API JSON + projections** (`/api/v1/` e
`/api/v1/backstage/`). As superfícies vivas são os apps Nuxt 4 SSR em `surfaces/`,
falando com o Django via BFF Nitro (cookie de sessão cross-subdomínio `.boulangerie`):

| Superfície | App | Porta dev | Papel |
|------------|-----|-----------|-------|
| Loja do cliente | `surfaces/storefront-nuxt` | :3000 | apex, mobile-first, branded |
| Central de Apps | `surfaces/hub-nuxt` | :3001 | hub do operador |
| PDV | `surfaces/pos-nuxt` | :3002 | desktop-first, tabs, turno, caixa |
| Cozinha (KDS) | `surfaces/kds-nuxt` | :3003 | prep, picking, expedição, painel de retirada |
| Gestor de pedidos | `surfaces/orders-nuxt` | :3004 | fila, cardápio, showcases |
| Produção/fornadas | `surfaces/production-nuxt` | :3005 | kiosk Solari (plan/mise-en-place/expedite/board) |
| — layer | `surfaces/operator-kit` | — | Nuxt layer compartilhada dos apps de operador (httpError, retry, connectivity, OperatorLock/PIN, telemetria) |

Tempo real é **SSE-first** ([ADR-016](decisions/adr-016-sse-first-realtime.md)) com
poll como fallback calmo; proxy same-origin no BFF de cada app. Rotas de operador em
inglês com 301 das antigas (PR #68); chaves de projection em inglês (PR #67); dialeto
canônico de erro `{detail, field, errors}` ([reference/errors.md](reference/errors.md), PR #60).

---

## Core Apps (packages/)

Testes coletados em 2026-07-11 (`pytest --collect-only`):

| Package | Pip | Testes | Status | Notas |
|---------|-----|--------|--------|-------|
| shopman-utils | `shopman-utils` | 98 | Estável | Monetário, phone, formatting, admin mixins |
| shopman-refs | `shopman-refs` | 175 | Estável | Registro de refs tipadas, rename/audit, fields |
| shopman-offerman | `shopman-offerman` | 249 | Estável | Catálogo, preços, listings, bundles, coleções |
| shopman-stockman | `shopman-stockman` | 240 | Estável | Estoque, holds, moves, posições, alertas; shelf-life ligado (validator composto) |
| shopman-craftsman | `shopman-craftsman` | 245 | Estável | Produção, receitas, work orders, BOM; guardrail de insumos ativo (`INVENTORY_BACKEND`) |
| shopman-orderman | `shopman-orderman` | 289 | Estável | Pedidos, sessions, directives, channels; baseline selado com cópias (PR #69) |
| shopman-guestman | `shopman-guestman` | 390 | Estável | CRM, clientes, loyalty, RFM, consent |
| shopman-doorman | `shopman-doorman` | 279 | Estável | Auth OTP, device trust, access links, magic links |
| shopman-payman | `shopman-payman` | 151 | Estável | Pagamentos, PIX, Stripe, reconciliação cumulativa |
| shopman-buyman | `shopman-buyman` | 9 | Fase 1 | Compras: Material, Supplier, custo, shelf-life; Fases 2–4 pós-go-live |
| shopman-fiscalman | `shopman-fiscalman` | 22 | S0–S4 | Classificação NFC-e em Product.metadata; resta S5 (NF-e mod. 55) + validação do contador |

**Total cores:** ~2.150 testes. **Framework** (`make test-framework`): ~2.870 testes
(shop + storefront + backstage). **Suite completa (`make test`): ~5.000 testes.**

---

## Framework (shopman/)

| Módulo | Status | Detalhe |
|--------|--------|---------|
| **Lifecycle** (pedidos) | Estável | dispatch funcional config-driven via `ChannelConfig` e signal `order_changed`; durabilidade de fase (PR #62) |
| **Production lifecycle** | Estável | `dispatch_production()` para WorkOrders (fornadas) |
| **Services** | Estável | Orquestração: availability, cancellation, stock, payment, customer, etc. |
| **Adapters** | Estável | EFI/PIX, Stripe, ManyChat, email, SMS, console, stock, inventory, Machine (courier) |
| **Handlers** | Estável | Directive handlers com dedupe garantido e observabilidade (ADR-003, PR #62) |
| **Rules engine** | Estável | `RuleConfig` no DB; pricing (D-1/Happy Hour) genérico e config-driven |
| **Storefront (API)** | Estável | `api/` + `presentation/` + `intents/`; rate-limiting, delivery zones, favoritos, stock alerts |
| **Backstage (API)** | Estável | POS, KDS, produção, orders, closing, operator; guards e idempotência endurecidos (PR #58) |
| **Admin (Unfold)** | Estável | Unfold Canonical Gate (`make admin`); telas de produção e fechamento |
| **Fiscal** | Parcial | NFC-e via Focus NFe (S0–S4); e2e homolog + emissão em produção pendentes |
| **iFood direto** | Staging | Polling + sync de catálogo; homologação de produção pendente |
| **Machine (courier)** | Construído | pronto→corrida, status realtime, cotar/re-despachar/cancelar (PR #43); creds + homologação webhook pendentes |

---

## Hardening pré-alpha (2026-07-11)

Auditoria registrada em
[`reports/analise_pre_alpha_2026-07-11.md`](reports/analise_pre_alpha_2026-07-11.md)
originou 16 PRs mergeados no mesmo dia (#53–#69), incluindo:

- gate transacional de estoque no commit (anti-oversell, PR #65);
- dialeto de erro uniforme `{detail, field, errors}` (PR #60);
- directives: observabilidade, dedupe como garantia, durabilidade de fase (PR #62);
- lifecycle/SSE/pagamento: `on_commit`, PIX suficiente, SameSite, IP real (PR #57);
- POS: `price_overridden` derivado do preço canônico no servidor (PR #56);
- sweep tz-aware `date.today()`/`now().date()` → `timezone.localdate()` (PR #55);
- suíte hermética ao env do dev + cobertura do `maintenance_worker` (PR #59);
- surfaces: typecheck total + Surfaces Gate no CI (PRs #61, #63);
- rotas de operador em inglês com 301 (PR #68) e projection keys em inglês (PR #67);
- orderman: baseline selado guarda cópias (detecção de mutação in-place, PR #69).

---

## Autenticação e canais

- **Login WhatsApp = access link** (`NB-XxXx`): pivô mergeado no main (PR #45).
  Reverse-OTP aposentado. Resta F3 (fluxo ManyChat, lado do dono) + URLs de staging.
- **OTP SMS fallback** (Comtele creds ok), magic links, device trust.
- **Copy omotenashi**: burndown fechado, backlog de copy **zerado** (PRs #49–#53);
  toda copy de cliente é canônica em `OmotenashiCopy`/`OMOTENASHI_DEFAULTS` e chega
  à tela via projection.
- **Canais ativos**: balcão (POS), web (storefront), iFood direto (staging).
  ManyChat conversacional (pedido por chat) segue não reimplementado.

---

## Deploy / staging

- Staging na DigitalOcean App Platform (`shopman-staging`), ingress por subdomínio
  (apex→loja Nuxt, `api.`/`admin.`/demais superfícies), Managed PostgreSQL 16 +
  Valkey. Deploy de código é **manual** via `doctl ... apps create-deployment`
  (nunca `apps update --spec` do repo — apaga segredos do app live).
- Buildpack DO usa Node 22; apps pinam `engines.node "22.x"`.
- CI: Runtime Gate (PostgreSQL + Redis, sem skips), Surfaces Gate (typecheck dos
  apps Nuxt), gates de docs/copy (`test_copy_wiring_backlog`), `make admin`.

---

## Fluxos Validados

- Pedido local (POS): commit → confirmação otimista → KDS → fulfillment
- Pedido remoto (storefront Nuxt): cart → checkout → PIX → SSE/polling → confirmação → tracking
- Pedido marketplace (iFood direto): polling → fila do gestor → KDS (staging)
- Notificações: WhatsApp (ManyChat), email, SMS, console — swappable por adapter
- Estoque: hold na criação → deduct na confirmação (gate transacional) → release no cancelamento
- Produção: receitas → work orders → BOM → consumo de insumos via signal (`craftsman/contrib/stockman`)
- Compras: materiais/fornecedores (Buyman F1) → disponibilidade de insumo valida produção
- Loyalty: acúmulo na confirmação, resgate no checkout
- Auth: access link WhatsApp-first, SMS fallback, device trust, magic links
- Fechamento do dia: sobras, D-1, apuração de caixa, reconciliação financeira diária
- Entrega: zonas + geocoding em cascata; corrida Machine construída (aguarda creds)

---

## Gaps Conhecidos (dependem de humano/externo)

- **Fiscalman S5** — NF-e mod. 55 / itens resale; e2e homolog Focus NFe; contador
  valida NCMs/CSC/IBPT. DANFE NFC-e impresso no PDV é obrigação legal (pós-alpha).
- **Credenciais go-live** — WhatsApp Meta, Focus NFe produção, iFood homologação,
  Machine (courier) creds centrais.
- **Go-live Lote C** — 2FA/IP allowlist do Admin + corte v1 + QA (bloqueado no dono).
- **QA físico** — som/impressora térmica da produção; QA visual em dispositivo real.
- **ManyChat conversacional** — pedido inbound por chat não reimplementado.

---

## Compatibilidade

| Requisito | Versão |
|-----------|--------|
| Python | ≥ 3.12 |
| Django | ≥ 6.0, < 6.1 |
| Node.js | 22.x (apps Nuxt; buildpack DO) |
| Banco de dados | PostgreSQL 16+ no dev canônico/staging/prod; SQLite só fallback local |
| Cache/realtime | Redis 7+ no dev canônico/staging/prod; LocMem só fallback local |

Ver contrato completo em [runtime-dependencies.md](reference/runtime-dependencies.md).
