# Backstage Design System — o canon das superfícies de operador

> Contrato visual **canônico e guardrailado** das quatro superfícies de operador
> (`pos-nuxt`, `orders-nuxt`, `kds-nuxt`, `production-nuxt`) e da central
> **Central de Apps** (`hub-nuxt`). Objetivo: **familiaridade** entre os apps do
> operador — a mesma gramática visual, ergonomia e comportamento, para que quem opera
> um reconheça o outro de imediato.
>
> **O storefront (`storefront-nuxt`) fica de fora**: é uma superfície de cliente,
> branded (Nelson), com sistema tipográfico e de cor próprio. Não consome este canon.

Estado atual (auditado 2026-07-04): os quatro `tailwind.css` de operador já são
**token-idênticos** — este documento **promove** essa identidade de-facto a contrato
**documentado + testado** (guardrails), servido uma vez pelo Nuxt layer
`surfaces/operator-kit/` (ver
[BACKSTAGE-EXCELLENCE-HARDENING-PLAN §4](../plans/completed/BACKSTAGE-EXCELLENCE-HARDENING-PLAN.md)).

---

## 1. Filosofia

- **Neutro por design (disciplina Odoo/ERP).** A superfície do operador não tem matiz
  de marca; a cor só aparece com **significado**. A marca vive no storefront.
- **Densidade + confiança.** O operador trabalha rápido, sob pressão, às vezes à
  distância. Clareza, alvos generosos e feedback imediato ganham de estética.
- **Um canon, intenções por superfície.** Divergências são **declaradas** (KDS
  dark-first; produção board Solari; POS densidade desktop), nunca drift acidental.

## 2. Cor (OKLch)

Tokens em `:root` (idênticos nos quatro apps hoje; passam a viver no `operator-kit`):

| Token | Valor | Uso |
|---|---|---|
| `--background` | `oklch(0.99 0 0)` | fundo (near-white; invertido no dark) |
| `--foreground` | `oklch(0.18 0 0)` | texto |
| `--primary` | `oklch(0.27 0 0)` | ação/CTA — **cinza neutro, não é cor de marca** |
| `--destructive` | `oklch(0.577 0.245 27.325)` | destrutivo/erro (vermelho) |
| `--muted` / `--accent` / `--border` / `--input` / `--card` | cinzas OKLch | superfícies e chrome |

**Cores com significado (as únicas coloridas):**
- **Vermelho** (`--destructive`) = destrutivo / atrasado / erro.
- **Âmbar** = aviso / atenção / "não salvo".
- **Verde** = dinheiro / sucesso / pago / no-prazo.

**Regra guardrail:** nenhuma cor arbitrária fora dos tokens; verde/âmbar/vermelho só no
sentido acima. Seleção **não** usa `ring` colorido (usa fundo/borda de token).

## 3. Tipografia — 6 papéis

Fontes: **Inter** (sans) + **Fira Code** (mono, para números/timers — `tabular-nums`).

| Papel | Classe base | Uso |
|---|---|---|
| `display` | `text-7xl/8xl font-bold tabular-nums` | total de pagamento, número herói |
| `figure` | `text-3xl/4xl font-bold tabular-nums` | troco, valor de tender, timer grande |
| `title` | `text-lg font-semibold` | cabeçalho de tela/seção |
| `body` | `text-sm font-medium` | **workhorse** — conteúdo, rótulo de botão |
| `label` | `text-xs font-medium text-muted-foreground` | rótulo de campo, chip |
| `micro` | `text-xs text-muted-foreground` | dica, meta, sub-rótulo |

**Regra guardrail:** classes de tamanho de texto só através destes 6 papéis; sem
`text-2xl`/`text-[0.65rem]` avulsos (mesma dívida corrigida no storefront no WP-S0).

## 4. Escada de altura de controle (toque)

| Nível | Altura | Uso |
|---|---|---|
| xs | `h-7` (28px) | ícone inline, micro |
| sm | `h-9` (36px) | chip, botão inline |
| **md** | **`h-11` (44px)** | **campo, botão default — piso de toque-seguro** |
| lg | `h-14` (56px) | CTA, tecla de numpad, tile de produto |

**Regra guardrail:** alvos interativos (botão/tecla/tile/linha clicável) **≥ 44px** no
POS/KDS/produção. No POS (desktop-first, balcão) o default é generoso; leitura à
distância no KDS/produção favorece `lg`.

## 5. Espaçamento e raio

- **Gap:** `1.5` (cluster) · `2` (default) · `3` (seção) · `4`/`6` (região).
- **Padding:** card `p-3`, dialog `p-4`.
- **Raio:** `rounded-md` (0.5rem) default em botões/cards/inputs; `rounded-full` só em
  pílula (badge/avatar). **Sem** `rounded-lg/xl/2xl` avulso.

## 6. Ícone forte por app (familiaridade)

Ícones **Lucide** (via `@nuxt/icon` + `@iconify-json/lucide`), um por superfície:

| App | Ícone | Identidade |
|---|---|---|
| PDV (`pos-nuxt`) | `banknote` | balcão / venda |
| KDS (`kds-nuxt`) | `chef-hat` | cozinha / preparo |
| Gestor (`orders-nuxt`) | `clipboard-list` | fila de pedidos |
| Fournil (`production-nuxt`) | `croissant` | produção / fornada |
| Loja (config no Central) | `store` | loja online |
| Central de Apps (`hub-nuxt`) | `layout-grid` | central / launcher |

## 7. Intenção por superfície (declarada, não drift)

| Superfície | Color-mode | Ergonomia |
|---|---|---|
| POS | light | desktop-first, densidade de balcão, numpad `lg` |
| KDS | **dark** | back-of-house, leitura à distância, timers mono, semáforo SLA |
| Gestor | light | board de pedidos, countdown de deadline visível |
| Produção | light | board Solari (split-flap), poll visibility-aware |
| Central | light | grade de tiles com ícone forte, permission-aware |

## 8. Guardrails (testes de consistência)

Suíte vitest compartilhada no `operator-kit`, consumida pelos 4 apps (modelo:
`surfaceGuardrails` do storefront). Verifica, entre outros:

1. **Paridade de tokens** — os `tailwind.css` de operador têm o mesmo bloco de tokens
   canônicos (falha se um divergir dos outros).
2. **Escala tipográfica** — sem classes de texto fora dos 6 papéis.
3. **Raio/seleção** — sem `rounded-lg/xl` avulso; sem `ring` colorido em seleção.
4. **Toque** — alvos interativos ≥ 44px onde a regra se aplica.
5. **Ícone forte** — cada app declara e usa seu ícone de identidade.
6. **A11y** — input de crachá não é `aria-hidden` porém focável (WCAG 4.1.2); ordem de
   foco e rótulos presentes.

Dívidas conhecidas entram numa **allowlist** explícita que **só encolhe** — nunca cresce
(cada WP por app resolve as suas e as remove da lista).

## 9. Fora do canon

- **storefront-nuxt** — superfície de cliente, branded, sistema próprio (Instrument
  Sans + Fraunces, marrom quente, tokens semânticos `--shop-*`). Intencionalmente
  divergente; não consome o `operator-kit`.
