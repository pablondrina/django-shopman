import type { ShopProjection, ShopDesignTokensProjection } from '~/types/shopman'

/**
 * Camada de marca = OVERRIDE sobre o base neutro (`app/assets/css/tailwind.css`).
 *
 * O base define a paleta stone em `:root`/`.dark` e os componentes UI-Thing leem as
 * variáveis reais (`--primary`, `--background`, …) via `@theme inline`. Aqui mapeamos
 * o `design_tokens` server-driven para ESSAS mesmas variáveis, emitidas num bloco
 * `<style>` (`:root{}` + `.dark{}`) injetado no SSR. Regras de reversibilidade:
 *   - ausência de `design_tokens` ⇒ nenhum override ⇒ cai no neutro (pixel-idêntico);
 *   - `?theme=neutral` ⇒ ignora a marca ao vivo (A/B), sem tocar em dado.
 *
 * O backend serve cada cor como canais `'R G B'` (0–255). No base neutro do Nuxt a
 * variável guarda uma COR COMPLETA (`oklch(...)`) consumida via `var(--token)` — então
 * aqui emitimos `rgb(R G B)` (cor completa), não os canais crus.
 */

/** token semântico do backend → custom property que o base neutro realmente consome. */
export const TOKEN_TO_CSS_VAR: Record<string, string> = {
  background: '--background',
  foreground: '--foreground',
  card: '--card',
  card_foreground: '--card-foreground',
  popover: '--popover',
  popover_foreground: '--popover-foreground',
  primary: '--primary',
  primary_foreground: '--primary-foreground',
  secondary: '--secondary',
  secondary_foreground: '--secondary-foreground',
  muted: '--muted',
  muted_foreground: '--muted-foreground',
  accent: '--accent',
  accent_foreground: '--accent-foreground',
  destructive: '--destructive',
  destructive_foreground: '--destructive-foreground',
  warning: '--warning',
  warning_foreground: '--warning-foreground',
  success: '--success',
  success_foreground: '--success-foreground',
  info: '--info',
  info_foreground: '--info-foreground',
  border: '--border',
  input: '--input',
  ring: '--ring',
  // Superfícies de identidade (navbar/rodapé). Defaults neutros no base = background/
  // foreground / tom do rodapé de hoje, então ausência da marca ⇒ neutro idêntico.
  header: '--shop-header',
  header_foreground: '--shop-header-foreground',
  footer: '--shop-footer',
  footer_foreground: '--shop-footer-foreground',
  help: '--shop-help',
  help_foreground: '--shop-help-foreground',
  ink: '--shop-ink',
  ink_foreground: '--shop-ink-foreground',
  bottomnav: '--shop-bottomnav',
  cta: '--shop-cta',
  cta_foreground: '--shop-cta-foreground'
}

function cssColor (value: string): string {
  const trimmed = value.trim()
  if (/^\d+\s+\d+\s+\d+(?:\s*\/\s*[\d.]+)?$/.test(trimmed)) return `rgb(${trimmed})`
  return trimmed
}

/** Mapeia um conjunto de tokens (light ou dark) → { '--var': 'rgb(...)' }. */
export function tokenVars (
  tokens: ShopDesignTokensProjection | Record<string, string> | null | undefined
): Record<string, string> {
  const out: Record<string, string> = {}
  if (!tokens) return out
  // Leitura por chave dinâmica sobre um bag de cores server-driven (o backend serve
  // mais tokens do que a projeção tipa, ex. cta/ink/bottomnav). `unknown` + guarda
  // de tipo mantém o acesso seguro sem afrouxar para `any`.
  const lookup = tokens as Record<string, unknown>
  for (const [key, cssVar] of Object.entries(TOKEN_TO_CSS_VAR)) {
    const raw = lookup[key]
    if (typeof raw === 'string' && raw.trim()) out[cssVar] = cssColor(raw)
  }
  return out
}

/** Variáveis CSS da marca para o modo claro (vazio ⇒ neutro). */
export function shopThemeStyle (shop: ShopProjection | null | undefined): Record<string, string> {
  return tokenVars(shop?.design_tokens)
}

// Fontes canônicas já self-hospedadas via @nuxt/fonts (declaradas no tailwind.css):
// Instrument Sans é a `--font-sans` do tema; Fraunces a display dos títulos. A marca
// não precisa re-injetá-las nem buscá-las externamente — só fontes de tenant DIFERENTES.
const SELF_HOSTED_FONTS = new Set(['Instrument Sans', 'Fraunces'])

/**
 * Família tipográfica da marca para `--font-sans` — só quando o tenant pede uma fonte
 * DIFERENTE da canônica (Instrument Sans, já o default self-hospedado). null ⇒ usa a
 * canônica do tema, sem override redundante.
 */
export function shopFontFamily (tokens: ShopDesignTokensProjection | null | undefined): string | null {
  const name = (tokens?.body_font || tokens?.heading_font || '').trim()
  if (!name || SELF_HOSTED_FONTS.has(name)) return null
  return `'${name}', ui-sans-serif, system-ui, sans-serif`
}

/** `<link>` para carregar a(s) fonte(s) da marca (vazio ⇒ neutro / preview). */
export function shopFontLinks (
  shop: ShopProjection | null | undefined,
  options: { preview?: string | null } = {}
): Array<Record<string, string>> {
  if (options.preview === 'neutral') return []
  const tokens = shop?.design_tokens as ShopDesignTokensProjection | undefined
  if (!tokens) return []

  const families = [...new Set(
    [tokens.heading_font, tokens.body_font]
      .map(f => (f || '').trim())
      .filter(Boolean)
  )].filter(f => !SELF_HOSTED_FONTS.has(f))
  if (!families.length) return []

  const query = families
    .map(f => `family=${encodeURIComponent(f).replace(/%20/g, '+')}:wght@400;500;600`)
    .join('&')

  return [
    { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
    { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
    { rel: 'stylesheet', href: `https://fonts.googleapis.com/css2?${query}&display=swap` }
  ]
}

function declarations (vars: Record<string, string>): string {
  return Object.entries(vars).map(([name, value]) => `${name}: ${value};`).join(' ')
}

/**
 * Bloco `<style>` da marca: `:root{}` (claro) + `.dark{}` (escuro). Retorna `''` quando
 * não há marca a aplicar — é o interruptor de reversibilidade.
 *
 * @param preview valor de `?theme=` (ex.: `'neutral'` força o neutro ao vivo).
 */
export function shopThemeCss (
  shop: ShopProjection | null | undefined,
  options: { preview?: string | null } = {}
): string {
  if (options.preview === 'neutral') return ''
  const tokens = shop?.design_tokens as ShopDesignTokensProjection | undefined
  if (!tokens) return ''

  const light = tokenVars(tokens)
  const dark = tokenVars(tokens.dark)

  // Tipografia da marca entra no mesmo bloco claro (a família não muda no escuro).
  const font = shopFontFamily(tokens)
  if (font) light['--font-sans'] = font

  // Especificidade dobrada (`:root:root` = 0,2,0) para vencer o base neutro (`:root`
  // / `.dark` = 0,1,0) independentemente da ORDEM de injeção (head/HMR/prod). O bloco
  // dark vem depois do light: em dark mode ambos casam com 0,2,0 e o último ganha.
  const blocks: string[] = []
  if (Object.keys(light).length) blocks.push(`:root:root { ${declarations(light)} }`)
  if (Object.keys(dark).length) blocks.push(`:root.dark { ${declarations(dark)} }`)

  // Remap escopado da navbar (só com marca): os internos usam tokens globais (--muted,
  // --primary, …) calibrados para o corpo creme; sobre o burgundy eles viram creme/gold
  // translúcido derivado de --shop-header-foreground. Emitido só aqui ⇒ neutro intacto.
  if (light['--shop-header'] && light['--shop-header-foreground']) {
    const fg = 'var(--shop-header-foreground)'
    blocks.push(
      `.shop-header-bar {` +
      ` color: ${fg};` +
      ` --background: var(--shop-header);` +
      ` --foreground: ${fg};` +
      ` --muted: color-mix(in srgb, ${fg} 14%, transparent);` +
      ` --muted-foreground: color-mix(in srgb, ${fg} 78%, transparent);` +
      ` --accent: color-mix(in srgb, ${fg} 16%, transparent);` +
      ` --accent-foreground: ${fg};` +
      ` --border: color-mix(in srgb, ${fg} 24%, transparent);` +
      ` --secondary: color-mix(in srgb, ${fg} 16%, transparent);` +
      ` --secondary-foreground: ${fg};` +
      ` --primary: var(--ring);` +
      ` --primary-foreground: var(--shop-header);` +
      ` --ring: ${fg};` +
      ` --logo-brass: color-mix(in oklch, var(--shop-cta), white 34%);` +
      ` }`
    )
  }

  // CTA do hero (sobre foto): neutro mantém a pílula branca (decisão do arco hero);
  // com marca, primária = Kraft (texto escuro) e secundária = transparente + borda
  // dourada. Emitido só com marca (especificidade dobrada vence as utilities bg-white).
  if (light['--shop-cta']) {
    blocks.push(
      `.shop-hero-cta.shop-hero-cta { background-color: var(--primary); color: var(--primary-foreground); }`,
      `.shop-hero-cta.shop-hero-cta:hover { background-color: color-mix(in srgb, var(--primary) 90%, #000); color: var(--primary-foreground); }`,
      `.shop-hero-cta-ghost.shop-hero-cta-ghost { background-color: transparent; border-color: var(--shop-cta); color: #fff; }`,
      `.shop-hero-cta-ghost.shop-hero-cta-ghost:hover { background-color: color-mix(in srgb, var(--shop-cta) 20%, transparent); color: #fff; }`
    )

    // Controle de quantidade é INTERATIVO (−/+) ⇒ cor de AÇÃO: pílula burgundy
    // (--primary) + conteúdo claro, dando continuidade ao botão "Adicionar". Remapeia
    // --foreground p/ os botões −/+ (text-foreground) ficarem claros. Neutro = pílula branca.
    blocks.push(
      `.shop-qty.shop-qty { background-color: var(--primary); color: var(--primary-foreground); border-color: color-mix(in srgb, var(--primary-foreground) 28%, transparent); --foreground: var(--primary-foreground); --accent: color-mix(in srgb, var(--primary) 82%, #000); --accent-foreground: var(--primary-foreground); }`
    )

    // Ação SOBRE o card escuro flutuante (CTA fixo mobile, fundo ink): inverte pra
    // manter a ação clara e legível sobre o vinho. Fundo Faubourg (--shop-bottomnav) +
    // texto Brass escurecido — alto contraste, ainda dentro da paleta. Consumido por
    // botões (.shop-action-inverted) e pela pílula de quantidade (.shop-qty-inverted).
    blocks.push(
      `.shop-action-inverted.shop-action-inverted { background-color: var(--shop-bottomnav); color: color-mix(in srgb, var(--shop-cta), #000 40%); border-color: transparent; }`,
      `.shop-action-inverted.shop-action-inverted:hover { background-color: color-mix(in srgb, var(--shop-bottomnav) 90%, #000); color: color-mix(in srgb, var(--shop-cta), #000 40%); }`,
      `.shop-qty-inverted.shop-qty-inverted { background-color: var(--shop-bottomnav); color: color-mix(in srgb, var(--shop-cta), #000 40%); border-color: color-mix(in srgb, var(--shop-cta) 30%, transparent); --foreground: color-mix(in srgb, var(--shop-cta), #000 40%); --accent: color-mix(in srgb, var(--shop-bottomnav) 84%, #000); --accent-foreground: color-mix(in srgb, var(--shop-cta), #000 40%); }`
    )

    // Seção da busca/reordenar: wash dourado (tint) — não sólido, p/ não engolir o
    // banner de pedido e os CTAs que também são Brass sólido.
    blocks.push(
      `.shop-section-cta.shop-section-cta { background-color: color-mix(in srgb, var(--shop-cta) 18%, var(--background)); }`
    )

    // Botão da seção "Dúvidas?" (WhatsApp) em Dark Moss próprio — um tom acima do
    // rodapé, que reserva o Deep Dark Moss só pra ele. Texto branco.
    blocks.push(
      `.shop-help-cta.shop-help-cta { background-color: var(--shop-help); color: var(--shop-help-foreground); }`,
      `.shop-help-cta.shop-help-cta:hover { background-color: color-mix(in srgb, var(--shop-help) 88%, #000); color: var(--shop-help-foreground); }`
    )

    // Pill bar (cardápio): barra Brass; pills inativas transparentes com texto branco;
    // pill de destaque BRANCA com texto Brass (como um segmented control). Remap escopado
    // resolve busca/limpar/contadores. Neutro mantém a barra clara (sem este emit).
    blocks.push(
      // Pills inativas = rótulos brancos limpos (sem borda/fill); ação (busca/limpar)
      // mantém leve contorno branco (--input). Selecionada = pílula deep dark brass.
      `.shop-pillbar.shop-pillbar { background-color: var(--shop-cta); color: #fff; --background: transparent; --foreground: #fff; --muted-foreground: #fff; --border: transparent; --input: color-mix(in srgb, #fff 55%, transparent); --accent: color-mix(in srgb, #fff 16%, transparent); --accent-foreground: #fff; }`,
      `.shop-pillbar [data-menu-pill-ref][data-state="active"] { background-color: color-mix(in srgb, var(--shop-cta) 38%, #000); border-color: color-mix(in srgb, var(--shop-cta) 38%, #000); color: #fff; }`
    )

    // Barra de busca: fundo Brass, campo branco (bg-card no input), ícone de voltar branco.
    // Hover do botão de voltar (ghost) = mesmo wash branco sutil da pill bar (remap --accent).
    blocks.push(
      `.shop-searchbar.shop-searchbar { background-color: var(--shop-cta); color: #fff; --accent: color-mix(in srgb, #fff 16%, transparent); --accent-foreground: #fff; }`,
      `.shop-searchbar [aria-label="Voltar ao cardápio"] { color: #fff; }`
    )

    // Breadcrumb sobre barra Brass: letras creme nos links, item ATUAL branco (o
    // UiBreadcrumbs usa text-primary no atual → remapeado p/ branco aqui).
    blocks.push(
      `.shop-breadcrumb-bar.shop-breadcrumb-bar { background-color: var(--shop-cta); color: #fff; --foreground: #fff; --primary: #fff; --muted-foreground: color-mix(in srgb, #fff 80%, transparent); }`
    )

    // Fios dourados que emolduram o conteúdo. O header pinta 6px Brass logo ABAIXO de
    // si (sombra externa, sobre o topo do conteúdo). O footer usa sombra INTERNA (inset)
    // no próprio topo: o fio fica DENTRO do rodapé (Brass sobre o verde), então é sempre
    // nítido e consistente em todas as páginas — antes, como sombra externa sobre o
    // conteúdo, sumia quando o que encostava era foto/imagem.
    blocks.push(
      `.shop-header-bar.shop-header-bar { box-shadow: 0 6px 0 0 var(--shop-cta); }`,
      `.shop-footer.shop-footer { box-shadow: inset 0 6px 0 0 var(--shop-cta); }`,
      // Bottom bar: fio FINO (1px) dourado no topo — recolore a borda existente.
      `.shop-bottomnav-bar.shop-bottomnav-bar { border-top-color: var(--shop-cta); }`
    )

    // Hover dourado-claro elegante (sobre o creme): wash Brass sutil + texto Brass.
    // Usado em CTAs ghost ("Ver cardápio completo") e nas linhas de coleção da busca.
    blocks.push(
      `.shop-gold-hover.shop-gold-hover:hover { background-color: color-mix(in srgb, var(--shop-cta) 14%, transparent); color: var(--shop-cta); }`
    )

  }

  return blocks.join('\n')
}
