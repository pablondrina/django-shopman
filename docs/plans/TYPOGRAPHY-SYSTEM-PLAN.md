# TYPOGRAPHY-SYSTEM-PLAN — Sistema tipográfico storefront-wide

> **Prompt auto-contido.** Faça pela TIPOGRAFIA (tamanho, peso, entrelinha,
> tracking, hierarquia) o que os arcos de COR e de LAYOUT fizeram pela cor e pelo
> espaço: estabelecer uma **gramática única**, torná-la a fonte da verdade, e
> aplicá-la consistente em TODA a superfície — tela a tela, verificada ao vivo,
> commit por tela.

## Missão

A superfície `surfaces/storefront-uithing-nuxt` (Nuxt 4 + UI-Thing/reka-ui 2.x +
Tailwind v4) já tem COR e ESPAÇO unificados (`shopThemeCss` / `.shop-stack-*`). A
tipografia, porém, está **meio-sistematizada**: existe uma escala documentada no
comentário de `app/assets/css/tailwind.css` (12/14/16/20/30, pesos 400/600), mas ela
**não é a fonte da verdade** — as telas ainda escolhem `text-*`/`font-*`/`leading-*`/
`tracking-*` ad-hoc, e a própria regra de pesos é violada. O objetivo é eliminar essa
deriva com um **sistema tipográfico** — uma escala de tamanhos, um conjunto fechado de
pesos, entrelinhas e trackings com **papéis semânticos** — consumido por todas as telas,
do jeito que `TOKEN_TO_CSS_VAR`/`shopThemeCss` unificaram a cor e `.shop-stack-*`
unificou o ritmo.

NÃO é um redesenho. É **hierarquia + legibilidade + ritmo tipográfico**: a mesma
"régua" de texto em todo lugar, níveis previsíveis, leitura confortável (idosos =
persona first-class, [[feedback_accessibility_omotenashi_first_class]]).

## Princípio (o paralelo com cor e layout)

| Cor (feito) | Layout (feito) | Tipografia (este arco) |
|---|---|---|
| Tokens semânticos (`--primary`…) | Escala de espaço (`.shop-stack-*`) | **Papéis tipográficos** (`.shop-title`, `.shop-body`…) |
| Fonte única (`brand_tokens.py` → `shopThemeCss`) | Primitivas únicas (`.shop-container`/`.shop-section`) | **Escala única** (size·weight·leading·tracking) no `tailwind.css` |
| Base neutro + override reversível | Base mobile-first + ajustes previsíveis | Base legível + ajustes responsivos previsíveis (fluido por breakpoint) |
| Aplicado em todas as superfícies, guardrailed | Auditado tela a tela, guardrailed | Auditado tela a tela, guardrailed |
| `?theme=neutral` prova reversibilidade | Auditoria 375px **e** desktop prova consistência | Auditoria 375px **e** desktop, claro/escuro, prova hierarquia |

Onde hoje há número mágico (`text-lg` numa tela, `text-2xl` na irmã para o mesmo papel;
`font-medium` (500) contra a regra; `leading-[14px]`/`leading-[1.08]`/`leading-4`
avulsos; `text-[11px]`), passa a haver **um papel da escala** com significado
("título de página", "título de seção", "corpo", "metadado", "kicker") — e o nível
muda por **peso OU cor**, nunca por tamanhos vizinhos.

## A deriva já observável (motiva o arco — confirmar na auditoria)

- **Pesos fora da regra**: a escala diz "somente 400 e 600 (500 reservado ao chrome dos
  componentes Ui)", mas telas autorais usam `font-medium` (500) em **~33 lugares** e há
  `font-bold` (700) solto. Contagem hoje: `semibold` 82 · `medium` 33 · `normal` 15 ·
  `bold` 1. → colapsar 500/700 nos pesos sancionados.
- **Tamanhos fora da escala documentada** (12/14/16/20/30 = xs/sm/base/xl/3xl):
  aparecem `text-lg` (18), `text-2xl` (24), `text-4xl`/`text-5xl` (hero) e um
  `text-[11px]` mágico. → decidir quais degraus são canônicos e abolir os avulsos.
- **Entrelinhas avulsas**: convivem `leading-5`/`leading-6` (bom) com
  `leading-[14px]`, `leading-[1.08]`, `leading-4`, `leading-none`. → amarrar leading a
  cada papel.
- **Tracking sem regra clara**: `tracking-wide` (kickers) e `tracking-tight` (headings
  grandes) usados por intuição. → tracking é função do papel/tamanho, não escolha avulsa.
- **Sem fonte de marca**: `--font-sans` = `ui-sans-serif, system-ui…`; existe
  `--font-display--font-feature-settings` (cv02/03/04/11) mas **nenhuma família
  `--font-display` real**. Decisão aberta (ver abaixo).

## Eixos a sistematizar (a gramática)

1. **Escala de tamanho** — definir os degraus canônicos e o papel de cada um. Ponto de
   partida = a escala já documentada (12/14/16/20/30), estendida com honestidade para o
   que as telas realmente precisam (ex.: o `text-4xl/5xl` do hero, o `text-3xl` do título
   de página). Mínima variação, níveis claros; nada de tamanhos vizinhos disputando o
   mesmo papel.
2. **Pesos fechados** — **somente 400 e 600** nas telas (500 fica reservado ao chrome das
   primitivas Ui; sem 700 autoral). No mesmo tamanho, o nível sobe por **peso OU cor** —
   nunca por um tamanho intermediário.
3. **Entrelinha (leading) por papel** — leading apertado para títulos grandes
   (`tight`/~1.1), confortável para corpo (~1.5). Cada papel carrega seu leading; abolir
   `leading-[...]` mágico.
4. **Tracking por papel** — negativo sutil em títulos grandes, normal no corpo, `wide`
   só em kickers uppercase. Função do papel, não avulso.
5. **Papéis semânticos (apelidos)** — `.shop-title` (h1), `.shop-heading` (h2 de seção),
   `.shop-item-title` (título de card/linha), `.shop-body` (corpo/controles),
   `.shop-meta` (metadados muted), `.shop-price` (valores tabular-nums) + os já
   existentes `.shop-kicker` e `.shop-muted`. Telas consomem o papel, não `text-*`
   avulso.
6. **Medida de leitura (measure)** — largura de linha confortável (~60–75ch) para blocos
   de prosa; amarrar às larguras de leitura já definidas no LAYOUT
   (`.shop-container`/`max-w-*`). Texto de leitura não estica no desktop.
7. **Legibilidade & omotenashi** — tamanho mínimo legível (corpo nunca abaixo de 14;
   metadados 12 só para o que é realmente secundário), contraste alto (já garantido pela
   cor), entrelinha generosa. Idosos em mente, conferido em 375px
   ([[feedback_accessibility_omotenashi_first_class]]).
8. **Tabular-nums e ritmo de preço** — preços/valores/contadores com `tabular-nums` e
   peso/tamanho coerentes por contexto (preço de card vs preço em destaque na PDP).
9. **Ritmo responsivo** — comportamento mobile-first → desktop previsível: quais papéis
   crescem por breakpoint (ex.: `.shop-title` 30→ maior no desktop) e quais ficam fixos.
   Sem "saltos" entre telas irmãs.

## Decisões a aprovar ANTES de aplicar (espelham as decisões de cor/layout)

Apresentar ao Pablo e **aprovar antes de aplicar** ([[feedback_iterative_analysis]]):

- **D1 — Fonte de marca vs system.** Manter `system-ui` (consistência atual, zero
  custo, "não é redesenho") **ou** introduzir uma família real (ex.: uma sans com cv
  features para corpo, e/ou uma **display serif** para H1/marca, coerente com a
  identidade Nelson Boulangerie — padaria francesa, logo SVG próprio). Trade-off:
  webfont = peso/FOUT/decisão de marca; system = neutro. *Default sugerido: corpo
  system; avaliar UMA display para títulos — decisão do Pablo.*
- **D2 — Degraus canônicos da escala.** Confirmar o conjunto fechado (ex.:
  12/14/16/18?/20/24?/30/36/48) e o papel de cada um; decidir se `lg`(18)/`2xl`(24)
  entram como degraus sancionados ou são abolidos.
- **D3 — Forma da fonte única.** Classes utilitárias de papel em `@layer components`
  (`.shop-title`…) — **espelhando a escolha do LAYOUT** — ou tokens `--text-*`. *Default
  sugerido: classes de papel (greppável, mesma técnica do `.shop-stack-*`).*

## Processo (idêntico a cor/layout)

**PROPOR → APLICAR → VERIFICAR AO VIVO → COMMIT POR TELA.**

1. **Auditoria primeiro (não editar nada ainda)**: varrer todas as telas
   (`app/pages/**` + componentes de composição, excluir `app/components/Ui/**`) e
   **catalogar a deriva** — tabela "papel × (size/weight/leading/tracking) usados".
   Comparar irmãs (mesmo papel, tamanhos diferentes). Destilar a régua-alvo a partir do
   que já é bom e do comentário existente. Registrar a tabela **neste plano** antes de
   editar. Apresentar a gramática + decisões D1–D3 e **aprovar**.
2. **Estabelecer a fonte única**: degraus + papéis em `app/assets/css/tailwind.css`
   (`@theme`/`@layer components`), substituindo o comentário-escala por primitivas
   reais. Uma tela-piloto adota e vira referência.
3. **Aplicar tela a tela**, na ordem de maior impacto: home, menu, busca, PDP, carrinho,
   checkout, conta (hub + sub-páginas), tracking, pagamento, login.
4. **Verificar AO VIVO** a cada tela: **375px (mobile) E desktop**, claro/escuro, marca
   on (`/`) e `?theme=neutral`. Screenshots + `preview_inspect` para medir
   `font-size`/`line-height` reais (não confiar só no screenshot). Console limpo.
5. **Commit por tela** com gates verdes.

## Convenções e armadilhas (NÃO violar)

- **Mobile-first**; storefront ≠ POS (POS é desktop-first, isto não).
- **Vue/reka**, não HTMX/Alpine — regras de `onclick`/`classList` do CLAUDE.md são do
  Django; aqui é estado Vue.
- **Sem lib de componente externa** ([[feedback_no_external_component_lib]]); usar as
  primitivas UI-Thing/reka e tokens. Canônico > classe copiada. **Não retipografar o
  chrome interno das primitivas `Ui/`** (peso 500 vive ali de propósito) — o arco é das
  telas autorais.
- **Tailwind**: só usar degraus que o sistema define; nada de `text-[11px]`/
  `leading-[1.08]` avulso ([[feedback_tailwind_only_existing_classes]]). Degrau novo →
  acrescentar à escala (fonte única), não inline.
- **Régua dupla, herança do LAYOUT**: papéis tipográficos amarram size+weight+leading+
  tracking juntos; telas consomem o papel. Onde um `text-*` solto for legítimo (ajuste
  pontual), tem que cair num degrau da escala.
- **Pesos**: 400/600 nas telas; 500/700 autoral é deriva a eliminar (500 só no chrome Ui).
- **Guardrails**: `tests/surfaceGuardrails.test.ts` fixa invariantes. Atualizar JUNTO
  (re-expressar, não só apagar) e **adicionar** o guardrail de tipografia (papéis
  existem; sem peso 500/700 autoral; sem `text-[..px]`/`leading-[..]` mágico; corpo ≥14).
- **Gates por tela** (DE DENTRO da superfície, senão pega o POS e quebra o alias `~`):
  `cd surfaces/storefront-uithing-nuxt && npx vitest run && npx nuxt build`.
- **Zero-residual** ([[feedback_zero_residuals]]): ao trocar um tamanho/peso mágico pelo
  papel, remover o antigo; nada de classes mortas.
- **HMR acumula estado**; verificar em reload limpo. **Preview por `127.0.0.1:3000`,
  nunca `localhost`** ([[reference_preview_ipv4_gotcha]]). Sessão = Pablo Teste
  (+55 43 99988-7766); conta/checkout exigem login (OTP na tela em dev).
- **Full-bleed/hero** mantém sua escala display declarada — não "normalizar" para dentro
  da escala de corpo.

## Entregáveis

- `app/assets/css/tailwind.css` com a **escala tipográfica + papéis** documentados
  (apelidos semânticos), fonte única — o comentário-escala vira primitivas reais.
- Cada tela do storefront consumindo a gramática (sem `text-*`/`font-*`/`leading-*`/
  `tracking-*` mágico avulso; sem peso 500/700 autoral).
- Guardrails atualizados fixando as invariantes tipográficas (papéis existem, pesos
  sancionados, sem leading/size mágico, corpo ≥14, tabular-nums em preços).
- Auditoria inicial (tabela da deriva) registrada neste plano antes de editar.
- vitest + nuxt build verdes; verificação ao vivo 375px+desktop, claro/escuro, por tela.

## Ordem sugerida

Auditoria → decisões D1–D3 aprovadas → gramática na fonte única → piloto (home) →
menu/busca → PDP → carrinho → checkout → conta → tracking/pagamento → login → guardrail.
Commit por tela; nada de big-bang.

---

## Auditoria da deriva (registrada 2026-06-16, antes de editar)

Varredura de `app/pages/**` + componentes de composição (excluindo `app/components/Ui/**`).

### Contagens brutas

| Eixo | Valores encontrados (contagem) |
|---|---|
| **Pesos** | `font-semibold` 83 · `font-medium` (500) **30** · `font-normal` 6 · `font-bold` (700) **0** (já limpo) |
| **Tamanhos** | `text-sm` 104 · `text-xs` 61 · `text-base` 16 · `text-3xl` 9 · `text-xl` 8 · `text-2xl` 8 · `text-lg` (18) **5** · `text-5xl` 1 · `text-4xl` 1 |
| **Leading** | `leading-5` 13 · `leading-6` 10 · `leading-tight` 3 · `leading-4` **2** · `leading-none` **1** · `leading-[14px]` **1** · `leading-[1.08]` **1** |
| **Tracking** | `tracking-wide` 14 · `tracking-tight` 7 |
| **Tabular-nums** | 32 usos (preços/valores) |

### Deriva qualitativa (papel × tamanho usado — irmãs divergentes)

| Papel | Tamanhos hoje (irmãs divergentes) | Alvo |
|---|---|---|
| **Título de página (h1)** | `text-3xl` (cart, login, tracking, pagamento, PDP) **vs** `text-2xl` (account: index/perfil/pedidos/preferencias/seguranca/enderecos) **vs** `text-2xl sm:text-3xl` (checkout) | **`.shop-title` = 30/3xl·600** (unifica — conta sobe de 24→30) |
| **Hero display** | `text-4xl sm:text-5xl` + `leading-[1.08]` + `tracking-tight` (HomeHeroThing) | **`.shop-display`** (mantém escala display; leading vira papel, sem `[..]` mágico) |
| **Título de seção (h2)** | `text-lg` (seguranca ×2) **vs** `text-xl md:text-2xl` (index whatsapp) | **`.shop-heading` = 20/xl·600** (abole lg/18 e 2xl/24 como heading) |
| **Título de item (card/linha)** | `text-base leading-5` (ProductTile, ProductListItem) | **`.shop-item-title` = 16/base·400 leading-5** |
| **Corpo / controles** | `text-sm` (×104), leadings variados | **`.shop-body` = 14/sm·400 leading-6** |
| **Metadado muted** | `text-xs` + `leading-[14px]`/`leading-4`/`leading-5` avulsos | **`.shop-meta` = 12/xs·400** (leading do papel; mata `[14px]`/`leading-4`) |
| **Preço de card** | `text-sm font-semibold tabular-nums` | **`.shop-price` = 14/sm·600 tabular-nums** |
| **Preço/total em destaque** | `text-lg` (checkout sticky, CartSummary) **vs** `text-3xl` (checkout sidebar, fidelidade) **vs** `text-xl` | **`.shop-price-strong` = 20/xl·600 tabular** + total-grande mantém 3xl pontual |
| **Kicker uppercase** | `text-xs font-semibold uppercase tracking-wide text-muted-foreground` (14×) **vs** `.shop-kicker` CSS = `tracking-normal text-primary` (só 2 usos) | **`.shop-kicker` = xs·600 uppercase tracking-wide muted** (corrige a regra: wide, não normal; cor override pontual) |

### `font-medium` (500) — 30 ocorrências a colapsar (telas autorais)

Distribuídas em: `tracking/[ref].vue` (8), `checkout.vue` (12), `account/index.vue` (3),
`account/enderecos.vue` (1), `account/pedidos.vue` (1), `account/perfil.vue` (1),
`pedido/[ref]/pagamento.vue` (2), `CartSummaryBreakdown.vue` (2). Quase todas são
**ênfase de valor/rótulo** que deve subir por **peso 600** (`.shop-price`/`font-semibold`)
ou ser **corpo 400** (`.shop-body`) conforme o papel — nunca 500 autoral.

### Leading/size mágicos a eliminar

- `HomeHeroThing.vue:282` — `leading-[1.08]` → papel `.shop-display`.
- `ProductListItem.vue:31` — `text-xs leading-[14px]` → `.shop-meta`.
- `product/[sku].vue:152` — `text-sm leading-4` → `.shop-body`/`.shop-meta`.
- `account/index.vue:78` — `text-3xl … leading-none` (saldo de pontos) → papel de número.
- `ShopHeader.vue:112` — `text-xs leading-4` (chrome do header; avaliar se autoral).

---

> Referências do que já foi feito (mesmos termos, mesma execução): a COR em
> [[project_color_system_plan]]/[[project_nelson_brand_palette]] e o ESPAÇO em
> [[project_layout_system_done]] (`docs/plans/LAYOUT-SYSTEM-PLAN.md`). Este arco fecha o
> tripé **cor · espaço · tipografia** da superfície.
