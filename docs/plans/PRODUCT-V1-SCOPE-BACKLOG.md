# PRODUCT-V1-SCOPE-BACKLOG — Frentes de produto em aberto antes do go-live

> Registro vivo das frentes de **produto** (features/UX) que ainda faltam, para
> que o escopo do **v1 público da Nelson** seja uma decisão consciente — não um
> esquecimento. Este doc é o **gate de escopo** do [GO-LIVE-READINESS-PLAN](GO-LIVE-READINESS-PLAN.md):
> o go-live real só dispara quando o "deve entrar no v1" abaixo estiver fechado.

**Status**: 🟢 Corte v1 decidido pelo Pablo (2026-06-26). v1 é **amplo** — ver nota de sequenciamento no fim.

---

## Relação com o go-live

- O **GO-LIVE-READINESS-PLAN** cuida do *como* publicar com segurança (gateways,
  migrations-freeze, runbooks, auth, QA).
- Este doc cuida do *o que* publicar (escopo de produto).
- **Importante**: o **Lote A** (WP-GAP-07 prep) **não conflita** com desenvolver
  estas frentes — ele é tooling/docs e só congela schema no go-live. Logo, dá
  para tocar produto e Lote A em paralelo. O que espera este backlog é o
  **go-live em si** (bloqueios externos + reset final).

---

## Frentes (corte v1 decidido em 2026-06-26)

### ✅ v1 — deve entrar antes do go-live

| Frente | O que falta | Origem |
|---|---|---|
| **Gestor de pedidos ao estado da arte** | Aprofundar a superfície operacional de pedidos (board/fila) ao benchmark; o item central do operador | Pablo (2026-06-26) + [SURFACE-CONVERGENCE-PLAN](SURFACE-CONVERGENCE-PLAN.md) |
| **Canal: Loja online (retirada)** | Base pronta; manter no escopo | existente |
| **Canal: PDV / balcão** | Base pronta; manter no escopo | existente |
| **Canal: Entrega / delivery** | Ativa a frente de **endereço canônico** (busca/geo/ajuste no mapa); taxa por distância já existe | [ADDRESS-UX-PLAN](ADDRESS-UX-PLAN.md) |
| **Canal: WhatsApp conversacional (ManyChat)** | Webhook ManyChat → session → confirmação **não reimplementado** — trabalho real | ROADMAP "Dívida Viva" |
| **Sincronização com catálogos externos** | **NOVA frente (Pablo).** Feed de produtos → Google Merchant, Meta/Instagram Shopping, WhatsApp Catalog. Greenfield, sem plano dedicado | Pablo (2026-06-26) |
| **Media persistente (Spaces/S3)** | Operador sobe fotos em prod → storage durável; filesystem efêmero perde imagem em redeploy | ROADMAP "Dívida Viva" |
| **Shelf life perecível** | Validade por produto/receita sem ambiguidade (`OffermanSkuValidator`/alias) | ROADMAP "Dívida Viva" |
| **Revisão reversa do PDV (Fase C)** | Auditoria de qualidade do POS antes de operar sob pressão | `project_storefront_gaps_review` |
| **Surface convergence** | Matar POS-HTMX legado; definir alvo do KDS (Nuxt vs HTMX) | [SURFACE-CONVERGENCE-PLAN](SURFACE-CONVERGENCE-PLAN.md) |
| **Playwright E2E como gate** | Tornar a suite E2E obrigatória no CI antes do piloto | ROADMAP "Dívida Viva" |

### ⏭️ pós-v1 — fica para depois do go-live

| Frente | Motivo |
|---|---|
| **Agentes de atendimento (Agentic)** | Pilar greenfield grande; loja + PDV + WhatsApp cobrem o launch |
| **Endereço — teleporte (WP-11 slice 3)** | Bloqueado em URL/campos do serviço; o fluxo base de endereço já cobre entrega |
| **Customer rating** | Nice-to-have; hoje há `Order.data.customer_rating` mínimo |
| **Mudar número de telefone** | Feature de borda ([CHANGE-PHONE-NUMBER-PLAN](CHANGE-PHONE-NUMBER-PLAN.md)) |

---

## Nota de sequenciamento (honesta)

O v1 ficou **amplo** — 11 frentes, várias greenfield (ManyChat conversacional,
catálogos externos) ou dependentes de infra/credencial externa. Isso é legítimo,
mas o go-live só dispara quando **todas** as ✅ estiverem entregues, então a
ordem importa para não travar tudo numa só. Sugestão de ondas dentro do v1:

1. **Operação núcleo** (sem dependência externa): Gestor de pedidos ao estado da
   arte, Revisão reversa do PDV, Surface convergence, Shelf life. São os que mais
   dependem só de código — começar por aqui rende valor cedo.
2. **Infra de produto**: Media persistente (Spaces/S3), Playwright como gate.
3. **Canais externos** (dependem de credencial/conta — andam junto com os
   bloqueios do Pablo no [GO-LIVE-READINESS-PLAN](GO-LIVE-READINESS-PLAN.md)):
   Entrega/endereço, WhatsApp/ManyChat, Sincronização de catálogos externos.

Cada frente ✅ precisa virar (ou já tem) plano executável antes de entrar.

---

## Próxima ação

1. ✅ Corte v1 decidido (2026-06-26).
2. Transformar cada frente ✅ em plano executável (ou reusar o existente),
   seguindo as ondas de sequenciamento acima.
3. O go-live (no GO-LIVE-READINESS-PLAN) só dispara com **todas** as ✅ entregues.

---

## Referências

- [GO-LIVE-READINESS-PLAN](GO-LIVE-READINESS-PLAN.md)
- [docs/plans/README.md](README.md) — índice de planos
- [docs/ROADMAP.md](../ROADMAP.md) — dívida técnica viva
