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
