# THEMING / MARCA — Prompt do arco final (storefront Nuxt)

> **Este é o ÚLTIMO arco do redesign do storefront.** Todos os anteriores foram
> construídos **neutros de propósito** justamente para terminar aqui. O texto
> abaixo é um **prompt auto-contido** — pronto para iniciar uma sessão autônoma
> (cole-o como a mensagem de abertura). Co-author: Claude Fable 5. Fala em pt-br.

---

## PROMPT

Executar o **arco de THEMING / MARCA** do redesign do storefront Nuxt no
django-shopman, branch `redesign/surface-excellence`. Autônomo (AUDITAR a fiação
de tema atual → PROPOR PLANO EM SUB-ARCOS → APLICAR → VERIFICAR AO VIVO em 375px +
desktop, **claro e escuro**, com o tema **ligado e desligado** → COMMIT POR TELA).
Fala comigo em pt-br. Começa apresentando o plano em sub-arcos ANTES da parte
pesada.

### RESTRIÇÃO-MÃE (Pablo, 2026-06-15): FACILMENTE CAMBIÁVEL E REVERSÍVEL
O tema da marca é uma **CAMADA DE OVERRIDE** sobre o base neutro — **nunca**
embutido em componente, utilitário Tailwind ou no CSS base. Consequências
obrigatórias:
- O **base neutro permanece intacto** como *fallback*: os defaults em `:root` /
  `.dark` do `app/assets/css/tailwind.css` (paleta "stone" em oklch, `--radius:
  0.5rem`, `--font-sans: ui-sans-serif`) **não são removidos nem reescritos**. O
  tema só os **sobrescreve** via variáveis CSS inline aplicadas no `<html>`/shell.
- **Um único interruptor** alterna marca ⇄ neutro com **zero resíduo**: ausência/
  objeto vazio de `design_tokens` ⇒ neutro; presença ⇒ marca. Além disso, expor um
  **override de preview** (ex.: `?theme=neutral` / flag) para o Pablo comparar
  marca vs. neutro AO VIVO sem mexer em dado.
- **Critério de aceite de reversibilidade**: desligar o tema devolve a superfície
  **pixel-idêntica** ao neutro de hoje. Demonstrar isso ao vivo.
- Reverter o arco inteiro deve ser trivial (é uma camada aditiva + um flip de
  guardrail): remover o mapeamento de tokens ⇒ volta ao neutro.

### CONTEXTO DA SUPERFÍCIE (estado real — já auditado)
- `surfaces/storefront-uithing-nuxt` (Nuxt 4 + UI-Thing/reka 2.x). Lógica pura em
  `app/utils/*.ts` + `app/presentation/*.ts` com vitest; `.vue` finos. Arcos 0–9 +
  HOME/HERO/NAVBAR + SEO técnico = ✅. **Tudo neutro.**
- **O backend JÁ serve o tema completo.** `shopman/storefront/presentation/shop.py`
  expõe `design_tokens=shop.design_tokens` na shop projection (chega ao Nuxt via
  `/api/v1/storefront/home/`). O contrato TS é
  `ShopDesignTokensProjection` em `app/types/shopman.ts` (set completo: background/
  foreground/card/primary/secondary/muted/accent/destructive/border/input/ring +
  `dark: Record<string,string>` + `theme_hex`/`background_hex`/`heading_font`/
  `body_font`/`color_mode`). **PROVA VIVA**: o storefront **Django** já se veste
  inteiro por esses mesmos tokens em
  `shopman/storefront/templates/storefront/partials/_tokens.html` (mapa light+dark
  + script anti-FOUC). O arco Nuxt deve **espelhar esse mapeamento** (mesmos nomes
  de token) para as duas superfícies vestirem-se de UMA config.
- **O que falta no Nuxt**: `app/utils/shopTheme.ts` hoje só mapeia
  `--shop-brand-color`/`--shop-brand-background` (vars que os componentes nem
  consomem). Os componentes usam os utilitários semânticos (`bg-primary`,
  `text-foreground`, `bg-muted`, …) que resolvem para `--primary`/`--background`/…
  definidos no `:root`. **O arco liga `design_tokens` → essas variáveis reais.**
- Fiação atual: `app/composables/useShopTheme.ts` aplica `shopThemeStyle()` no
  `document.documentElement` (client). `app/app.vue` aplica `shellStyle =
  shopThemeStyle(session.shop.value)` como `:style` no shell. O home fetch já roda
  no SSR (app.vue `useFetch` com cookie) — dá para aplicar o tema **no SSR** e
  evitar FOUC.

### O QUE FAZER (mapear, não inventar)
1. **`app/utils/shopTheme.ts`** — `shopThemeStyle()` passa a mapear o
   `ShopDesignTokensProjection` inteiro para as variáveis CSS reais (`--background`,
   `--foreground`, `--card`, `--primary`, `--primary-foreground`, `--secondary`,
   `--muted`, `--accent`, `--destructive`, `--border`, `--input`, `--ring`, …) e o
   mapa `dark` para os equivalentes sob `.dark`. Mais radius (se houver token) e as
   fontes (`--font-sans`/heading). **Puro + vitest** (tabela token→var; ausência de
   token ⇒ não emite a var ⇒ cai no neutro). Aceitar o formato que o backend manda
   (oklch/hex/rgb triplo — já há `cssColor()`).
2. **`app/composables/useShopTheme.ts` + `app/app.vue`** — aplicar o set completo
   **no SSR e no client** (sem FOUC). `theme-color` meta server-driven; favicon/logo
   pela marca quando houver (`shop.logo_url`).
3. **Fontes** — `heading_font`/`body_font` → carregar só quando setadas (preferir
   `@nuxt/fonts` ou `<link>`), com fallback `ui-sans-serif` (neutro). Manter a
   disciplina de pesos (400/600; o sistema tipográfico do Nuxt não usa 700).
4. **Logo na marca** — quando `shop.logo_url` existir, usar no ShopHeader (o
   ícone-em-círculo neutro vira o logo), no menu (sheet) e, se fizer sentido, no
   hero. Sem logo ⇒ mantém o neutro.
5. **Interruptor + preview** — definir o switch de reversibilidade (ausência de
   `design_tokens` ⇒ neutro) e um override de preview (`?theme=neutral`/flag) para
   A/B ao vivo. Documentar.

### GUARDRAIL A REVISITAR CONSCIENTEMENTE
`tests/surfaceGuardrails.test.ts` › **"keeps the UI Thing theme surface-owned with
stone primary and doubled radius"** hoje **congela** o neutro E **proíbe** o
override: `theme.not.toContain("style['--primary']")` e
`not.toContain('TOKEN_TO_CSS_VAR')` são **resíduo de uma tentativa anterior de
theming REJEITADA** ("frankenstein"). Este arco deve **FLIPAR** essas duas
asserções para o **novo contrato limpo** de override por tokens — **mantendo** os
pinos do base neutro como *fallback* (paleta stone/oklch do `:root`, `--radius:
0.5rem`, `--font-sans: ui-sans-serif`, `theme "stone"` no `ui-thing.config.ts`).
**Atualizar junto, com asserções positivas do novo mecanismo — não só apagar.**
Demais guardrails que pinam strings dos `.vue` (surfaceGuardrails/canonicalEndpoints)
seguem o mesmo princípio.

### CORE É SAGRADO
Os tokens nascem da config do Shop (`shopman/shop/colors.py` /
`oxbow_tokens.py` / `Shop.design_tokens` — JSONField), **não** mexer no sistema de
tokens do Core. Se a shop projection servida ao Nuxt vier sem tokens, o problema é
de **wiring da projection/seed/Admin**, não do Core. Sem campos novos no Core; o
contexto vive em JSONField (`docs/reference/data-schemas.md`).

### ACESSIBILIDADE / OMOTENASHI (first-class, não deixar pra depois)
A marca **não pode** quebrar contraste: texto sobre `primary`, a **pílula branca do
hero**, a barra de status, badges e estados. Verificar com a persona idosa em mente
(contraste alto). Se uma cor de marca falhar, o pipeline de tokens deve
garantir/ajustar o `*-foreground` (o `colors.py` do backend já calcula foregrounds
acessíveis — confiar nele). Copy segue 100% server-driven (não é deste arco).

### MÉTODO / GATES / VERIFICAÇÃO
- Gates SEMPRE de **dentro** de `surfaces/storefront-uithing-nuxt`: `npx vitest run`
  + `npx nuxt build` (da raiz pega o POS e quebra o alias `~`). Backend (se tocar):
  `.venv/bin/pytest shopman/storefront/tests` (da raiz).
- Verificação AO VIVO (preview tools, **sempre 127.0.0.1**, sessão Pablo Teste
  +5543999887766): 375px + desktop, **claro e escuro**, **tema ligado e desligado**.
  Console limpo, sem hydration mismatch. reka 2.x: `v-model`/`:model-value`. Botões
  reka respondem a `pointerdown` (PointerEvent na verificação). `preview_network`
  rotaciona com HMR — conferir via urlFilter/grep.
- **Commit por tela**, plano em `docs/plans/THEMING-PLAN.md` (este arquivo —
  registrar a execução ao fim). Atualizar a memória
  `project_storefront_nuxt_redesign.md`.

### PROVÁVEIS SUB-ARCOS (validar comigo antes da parte pesada)
- **T1 — pipeline de tokens**: `shopThemeStyle` completo (light+dark) + SSR/anti-FOUC
  + vitest + flip do guardrail + interruptor/preview de reversibilidade.
- **T2 — tipografia da marca**: fontes heading/body server-driven com fallback neutro.
- **T3 — identidade visual**: logo (header/menu/hero), favicon, theme-color,
  acertos de contraste (hero/status/badges) sob a marca.
- (Decisões de UX/marca comigo.)

### ENTREGAR
1. Auditoria curta da fiação de tema (já adiantada acima) + plano em sub-arcos →
   validar comigo.
2. Executar autônomo, verificação ao vivo por tela (claro/escuro, on/off), commit
   por tela.
3. Demonstrar a **reversibilidade** ao vivo (marca ⇄ neutro por um interruptor;
   neutro pixel-idêntico ao de hoje).

---

## Estado inicial (para referência)
Branch `redesign/surface-excellence`. Storefront: arcos 0–9 + HOME/HERO/NAVBAR +
SEO técnico ✅, tudo neutro. vitest 204 / nuxt build verdes. Backend já serve
`design_tokens` (Django storefront já se veste por eles). Sessão preview = Pablo
Teste (+5543999887766).
