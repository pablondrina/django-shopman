# LAYOUT-SYSTEM-PLAN — Sistema de diagramação storefront-wide

> **Prompt auto-contido.** Faça pelo LAYOUT (diagramação, espaçamentos,
> alinhamentos) o que o arco de theming fez pela COR: estabelecer uma **gramática
> única**, torná-la a fonte da verdade, e aplicá-la consistente em TODA a
> superfície — tela a tela, verificada ao vivo, commit por tela.

## Missão

A superfície `surfaces/storefront-uithing-nuxt` (Nuxt 4 + UI-Thing/reka-ui 2.x +
Tailwind v4) está visualmente coerente em COR e tipografia, mas o **espaço** ainda
é ad-hoc: cada tela escolheu seus próprios `space-y-*`, `py-*`, `gap-*`, paddings de
card, larguras e alinhamentos. O objetivo é eliminar essa deriva com um **sistema de
layout** — uma escala de espaçamento e um conjunto de primitivas de composição —
consumido por todas as telas, do jeito que `TOKEN_TO_CSS_VAR`/`shopThemeCss`
unificaram a cor.

NÃO é um redesenho. É **consistência + ritmo + alinhamento**: a mesma "régua" em
todo lugar, respiros previsíveis, bordas que alinham, densidade coerente.

## Princípio (o paralelo com a cor)

| Cor (feito) | Layout (este arco) |
|---|---|
| Tokens semânticos (`--primary`, `--shop-header`…) | **Escala de espaço** (`--space-*` / rhythm tokens) |
| Fonte única (`brand_tokens.py` → `shopThemeCss`) | **Primitivas únicas** (`.shop-container`, `.shop-section`, stack/rhythm) |
| Base neutro + override reversível | Base mobile-first + ajustes responsivos previsíveis |
| Aplicado em todas as superfícies, guardrailed | Auditado tela a tela, guardrailed |
| `?theme=neutral` prova reversibilidade | Auditoria 375px **e** desktop prova consistência |

Onde hoje há número mágico (`space-y-5` numa tela, `space-y-6` na irmã; `p-4`
aqui, `p-5` ali; `gap-3` vs `gap-2.5`), passa a haver **um valor da escala** com
significado ("ritmo de seção", "stack interno de card", "gutter de lista").

## Eixos a sistematizar (a gramática)

1. **Escala de espaçamento** — definir os degraus canônicos e o que cada um
   significa (ex.: ritmo entre seções, stack interno, gutter de itens de lista,
   padding de card, padding de página). Hoje convivem `space-y-5/6`, `gap-2/2.5/3`,
   `py-2.5/3/4` sem regra. Escolher a régua (provavelmente a escala 4px do Tailwind,
   mas com **apelido semântico**) e documentá-la no `app/assets/css/tailwind.css`.
2. **Container** — `.shop-container` (largura máxima + padding horizontal). Garantir
   UMA largura de leitura e UM gutter lateral; conferir telas que escapam
   (full-bleed proposital da PDP/hero é exceção declarada, não acidente).
3. **Ritmo de seção** — `.shop-section` e o respiro entre header → breadcrumb →
   conteúdo → rodapé/bottom-nav. O padding-bottom precisa reservar a bottom-nav
   (mobile) sem buraco no desktop. Uma única regra de rhythm vertical por página.
4. **Alinhamento** — todas as bordas esquerdas do conteúdo na mesma linha; títulos,
   parágrafos, listas e cards compartilhando o mesmo eixo; hairlines (`border-b`)
   com o mesmo recuo. Caçar o "degrau" de 2–4px entre blocos vizinhos.
5. **Densidade / padding de card** — `bg-card` com padding coerente (p-4 vs p-5),
   raio (`rounded-xl` vs `rounded-2xl`) e gap interno padronizados por **tipo** de
   card (informacional, formulário, navegação).
6. **Alvos de toque & acessibilidade** — ≥40px (idosos = persona first-class,
   [[feedback_accessibility_omotenashi_first_class]]); espaçamento entre alvos
   clicáveis que evita toque errado. Conferir em 375px.
7. **Ritmo responsivo** — comportamento mobile-first → desktop previsível: quando
   vira 2 colunas, qual `max-w`, onde centra, onde estica. Sem "esticar" conteúdo de
   leitura no desktop (cf. POS é desktop-first, mas o **storefront é mobile-first**).
8. **Ritmo tipográfico** — margens de heading e `leading` já têm escala
   (12/14/16/20/30); alinhá-la ao novo espaçamento (sem inventar tamanhos).

## Processo (idêntico ao theming/cor)

**PROPOR → APLICAR → VERIFICAR AO VIVO → COMMIT POR TELA.**

1. **Auditoria primeiro (não editar nada ainda)**: varrer todas as telas
   (`app/pages/**` + componentes de composição) e **catalogar a deriva** — tabela de
   "tela × espaçamentos/paddings/larguras usados". Comparar irmãs (cart vs checkout
   vs account; menu vs busca). Destilar a régua-alvo a partir do que já é bom.
   Apresentar a gramática proposta ao Pablo e **aprovar antes de aplicar**
   ([[feedback_iterative_analysis]]).
2. **Estabelecer a fonte única**: degraus + primitivas em `app/assets/css/tailwind.css`
   (`@theme`/`@layer`), apelidos semânticos. Uma tela-piloto adota e vira referência.
3. **Aplicar tela a tela**, na ordem de maior impacto: home, menu, busca, PDP,
   carrinho, checkout, conta (hub + sub-páginas), tracking, pagamento, login.
4. **Verificar AO VIVO** a cada tela: **375px (mobile) E desktop**, claro/escuro,
   tema marca on (`/`) e `?theme=neutral`. Screenshots + `preview_inspect` para medir
   espaçamentos reais (não confiar só no screenshot). Console limpo.
5. **Commit por tela** com gates verdes.

## Convenções e armadilhas (NÃO violar)

- **Mobile-first**; storefront ≠ POS (POS é desktop-first, isto não).
- **Vue/reka**, não HTMX/Alpine — as regras de `onclick`/`classList` do CLAUDE.md são
  para o Django; aqui é estado Vue (`ref`, `v-show`, `<Transition>`). Botões reka só
  abrem via PointerEvent (eval), `UiButton @click` simples funciona.
- **Sem lib de componente externa** ([[feedback_no_external_component_lib]]); usar as
  primitivas UI-Thing/reka existentes e tokens. Canônico > classe copiada.
- **Tailwind**: só usar degraus que o sistema define; nada de número mágico avulso
  ([[feedback_tailwind_only_existing_classes]]). Se precisar de um degrau novo,
  acrescentar à escala (fonte única), não inline.
- **Guardrails**: `tests/surfaceGuardrails.test.ts` fixa strings exatas dos arquivos.
  Atualizar JUNTO com cada mudança (não só apagar — re-expressar a invariante).
- **Gates por tela** (DE DENTRO da superfície, senão pega o POS e quebra o alias `~`):
  `cd surfaces/storefront-uithing-nuxt && npx vitest run && npx nuxt build`.
- **Full-bleed proposital** (hero, foto da PDP mobile) é exceção declarada — não
  "consertar" para dentro do container.
- **Zero-residual** ([[feedback_zero_residuals]]): ao trocar um número mágico pelo
  token, remover o antigo; nada de classes mortas.
- **HMR acumula estado**; verificar em reload limpo. Limpar carrinho de teste ao fim.
- Sessão de preview = Pablo Teste (+55 43 99988-7766); conta/checkout exigem login
  (OTP aparece na tela em dev).

## Entregáveis

- `app/assets/css/tailwind.css` com a **escala de espaço + primitivas** documentadas
  (apelidos semânticos), fonte única.
- Cada tela do storefront consumindo a gramática (sem números mágicos avulsos).
- Guardrails atualizados fixando as invariantes de layout (container único, ritmo de
  seção, alvos ≥40px).
- Auditoria inicial (tabela da deriva) registrada neste plano antes de editar.
- vitest + nuxt build verdes; verificação ao vivo 375px+desktop por tela.

## Ordem sugerida

Auditoria → gramática aprovada → piloto (home) → menu/busca → PDP → carrinho →
checkout → conta → tracking/pagamento → login. Commit por tela; nada de big-bang.

---

## Auditoria da deriva (2026-06-16) — registrada antes de editar

Varredura de `app/pages/**` + componentes de composição (exclui `app/components/Ui/**`,
que são primitivas vendoradas UI-Thing). Contagem de ocorrências por classe.

### O que JÁ está bom (não mexer na estrutura)
- **Container único**: `.shop-container` (`max-w-6xl` + `px-4 sm:px-6 lg:px-8`) adotado em
  **18 arquivos**. UMA largura de leitura, UM gutter lateral. ✅
- **Ritmo de seção**: `.shop-section` (`py-6 sm:py-8 lg:py-10`) adotado em **15 arquivos**. ✅
- **Bottom-nav reserve**: `.shop-bottom-safe` (`pb: safe-area + 5.5rem`, zerado ≥768px). ✅
- Tipografia já tem escala documentada (30/20/16/14/12, pesos 400/600).

### A deriva real (números mágicos sem regra)

**1. Stack vertical (`space-y-*`)** — usado sem significado por degrau:
| degrau | usos | | degrau | usos |
|---|---|---|---|---|
| space-y-2 | 29 | | space-y-6 | 4 |
| space-y-4 | 20 | | space-y-2.5 | 1 |
| space-y-3 | 20 | | space-y-1.5 | 1 |
| space-y-5 | 18 | | space-y-0.5 | 2 |
| space-y-1 | 7 | | space-y-7/8 | 2 |

Telas-irmãs divergem: cart top-level mistura `2 / 2.5 / 3 / 5`; checkout `1/2/3/4/5`;
menu `0.5/1/2/4/5/7`; login só `5`; account/index `2/3/6`. **5 vs 6** e os meio-degraus
(`0.5/1.5/2.5`) são a poluição.

**2. Gaps (`gap-*`)**: gap-3 (58), gap-2 (50), gap-4 (17) dominam; ruído em
`gap-0.5 (12) / gap-1 (10) / gap-1.5 (7) / gap-5 (3)`.

**3. Padding de card (`bg-card` + p-\*)**: **p-4 (14)** é o de-facto; mas convivem
`p-3 (5)`, `px-4/py-3`, `py-2/py-4`. Card informacional vs row compacto sem regra.

**4. Raio (`rounded-*`)**: **rounded-lg (45)** é o raio de-facto de card/painel; porém a
primitiva `UiCard` nasce `rounded-xl` (8 usos) e há `rounded-md (14)` em elementos menores.
Divergência lg↔xl entre telas e a primitiva.

**5. Larguras de leitura internas**: dentro do container 6xl aparecem `max-w-2xl (6) /
xl (3) / md (3) / 4xl (3) / 3xl (1)` ad-hoc, sem papel definido (coluna de form vs prosa).

### Gramática-alvo proposta (destilada do que já é bom)

**Escala de ritmo vertical — 5 degraus semânticos** (snap dos meio-degraus e do 5→6):
| alias | valor | significado |
|---|---|---|
| `micro` | space-y-1 | kicker→título, ícone↔label |
| `tight` | space-y-2 | label→valor, stack interno de card |
| `snug` | space-y-3 | gutter de itens de lista, campos de form |
| `block` | space-y-4 | entre cards, título de seção→conteúdo |
| `section` | space-y-6 | entre seções de página (absorve o 5) |

**Gaps** espelham: `gap-1` (hair) / `gap-2` (inline) / `gap-3` (gutter) / `gap-4` (wide).
Eliminar `gap-0.5/1.5/5`.

**Card canônico**: `bg-card rounded-lg p-4` + stack interno `tight (space-y-2)`.
Variante row compacto: `p-3`. Raio canônico de card/painel = **rounded-lg** (de-facto;
alinhar a primitiva UiCard de `rounded-xl`→`rounded-lg`). `rounded-md` reservado a chips/inputs.

**Larguras de leitura**: definir papéis — coluna de form/prosa estreita = `max-w-xl`;
container de página permanece `.shop-container` (6xl). Eliminar 2xl/3xl/4xl avulsos onde
forem só "número escolhido na hora".

### Decisões aprovadas (Pablo, 2026-06-16)

- **Escala: 4 degraus enxutos** `{1,2,4,8}` (geométrica ×2), apelidos semânticos:
  | alias (classe) | valor | papel |
  |---|---|---|
  | `.shop-stack-micro` | space-y-1 (0.25rem) | kicker→título, ícone↔label |
  | `.shop-stack-tight` | space-y-2 (0.5rem) | stack interno de card, label→valor, gutter de lista |
  | `.shop-stack-block` | space-y-4 (1rem) | entre cards, título de seção→conteúdo, campos de form |
  | `.shop-stack-section` | space-y-8 (2rem) | entre seções maiores da página |

  **Snap dos legados** (nearest-in-log, decidir por papel ao aplicar, verificar ao vivo):
  `0.5/1/1.5 → micro`; `2/2.5 → tight`; `3 → tight` (lista/intra-card) ou `block` (separa blocos);
  `5 → block`; `6/7/8 → section`. Gutters horizontais (`gap`) usam working set `{1,2,3,4}` —
  eliminar `gap-0.5/1.5/5`.
- **Raio de card/painel canônico: `rounded-lg`** (de-facto, 45 usos). `rounded-md` p/ chips/inputs.
  Alinhar a primitiva `UiCard` (`rounded-xl`→`rounded-lg`) **se** for usada nas telas do storefront.
- **Forma da fonte única: classes utilitárias** em `@layer components` no `tailwind.css`
  (mesma técnica do `.shop-section`/`.shop-container` atual).
- **Card density**: `bg-card rounded-lg p-4` + stack interno `tight`; variante row compacto `p-3`.
