# Nuxt Design System — Storefront e Backstage

Guia operacional para superficies Nuxt v4 do Shopman. Aplica a `surfaces/storefront-nuxt/`
e a futura `surfaces/backstage-nuxt/`.

**Princípio mestre:** se Nuxt UI v4 já resolve, use Nuxt UI v4. Não copie classes nem
imite aparência. `:ui` overrides são exceção, não regra. **Máximo 1 `:ui` override por
elemento.** Mais que isso significa que o componente errado foi escolhido.

## Tipografia — 5 níveis, fim

| Nível       | Mobile        | Desktop       | Peso       | Cor token            | Uso                                             |
|-------------|---------------|---------------|------------|----------------------|-------------------------------------------------|
| Display     | `text-4xl`    | `text-5xl`    | `font-bold`| `text-highlighted`   | Hero único da página, raro                      |
| Title       | `text-2xl`    | `text-3xl`    | `font-bold`| `text-highlighted`   | `UPageHeader` title, página/seção principal     |
| Section     | `text-lg`     | `text-xl`     | `font-semibold` | `text-highlighted` | Card header, subseção                          |
| Body        | `text-base`   | `text-base`   | `font-normal` | `text-default`     | Conteúdo principal — **sempre 16px no mobile**  |
| Caption     | `text-sm`     | `text-sm`     | `font-normal` | `text-muted`       | Metadados, hints, descrições secundárias        |

**Regras inegociáveis:**
- Body em mobile **nunca** abaixo de `text-base` (16px). Usuário idoso é first-class.
- `text-xs` reservado para badges (`UBadge size="xs"`) e timestamps. Nunca em parágrafos.
- Contraste mínimo: `text-muted` em `bg-default`. Nunca `text-dimmed` para conteúdo.
- Preço/total: `tabular-nums` sempre. Sem exceção.

## Cores — só tokens semânticos

Use os tokens do tema. **Nunca** Tailwind cores diretas (`bg-amber-500`, `text-gray-700`).

| Token              | Quando usar                                              |
|--------------------|----------------------------------------------------------|
| `text-highlighted` | Títulos, valores em destaque, nomes de produto           |
| `text-default`     | Corpo de texto, conteúdo principal                       |
| `text-muted`       | Descrições secundárias, hints, metadados                 |
| `text-dimmed`      | Decorativo apenas (ex: counters em background)           |
| `text-inverted`    | Texto sobre `bg-inverted`                                 |
| `text-toned`       | Variação do default; usar quando `text-default` for forte demais |
| `bg-default`       | Fundo da página                                           |
| `bg-elevated`      | Cards, containers elevados                                |
| `bg-muted`         | Áreas de descanso visual                                  |
| `bg-inverted`      | Hero, CTA invertido                                       |

Cores semânticas (`primary`, `success`, `warning`, `error`, `info`, `neutral`) **só** via
`color="..."` em componentes Nuxt UI. Não escreva `bg-primary` solto — use `UBadge color="primary"`.

## Hierarquia de componentes

**Página** = `UContainer` + `UPageHeader` + sections. Não inventar wrappers.

**Section** = `UPageSection` (com headline/title/description props), ou `<section>` simples
quando a section não precisa de header (ex: hero).

**Card** decisão:
- `UCard` quando estrutura é simples (header + body + footer slots).
- `UPageCard` quando precisa de `to`, `title`, `description` props (CTA cards, marketing).
- `UCard variant="subtle"` para sidebars/resumos.
- `UCard variant="outline"` (default) para conteúdo principal.

**Lista de itens repetidos** = componente próprio (ex: `CartLineItem.vue`,
`ProductCard.vue`). Markup inline em `v-for` proibido para qualquer item com >3 elementos.

**Form** = `UForm` + `UFormField` + Nuxt UI inputs. Não compor com `<form>` + `<input>` cru.

**Modal** = `UModal` com `v-model:open`. Não inventar overlay.

## CTAs

- **Primário** (ação principal da tela): `<UButton size="xl">` (mobile) ou `size="lg"` (componentes embed).
- **Secundário**: `color="neutral" variant="outline"`.
- **Ghost** (link): `color="neutral" variant="ghost"`.
- **Inverted** (sobre `bg-inverted`): `color="neutral" variant="solid"` dentro de `dark` class.

Ícone-only só com `aria-label`. Sempre.

## Mobile-first

- Layout começa em uma coluna. `lg:grid-cols-...` adiciona colunas, nunca remove conteúdo.
- Toque mínimo 44×44px. Use `size="md"` ou maior em controles primários mobile.
- Bottom nav fixa só em mobile (`lg:hidden`). Header reage com `UHeader`.
- Sticky CTA bar mobile para checkout/finalizar — `lg:hidden`, acima do bottom nav.
- Imagens: `loading="lazy"` exceto a primeira above-the-fold.

## Omotenashi

Copy é cuidado, não floreio. Princípios:

- **Verbos no presente, voz ativa.** "Confirme até 18h" > "Será necessário confirmar".
- **Trate o cliente por você.** "Como podemos te chamar?" > "Informe seu nome".
- **Antecipe a próxima ação.** Toda mensagem de estado tem um próximo passo claro ou
  uma promessa ("a casa avisa quando").
- **Sem jargão técnico.** "Carrinho aguardando" > "Itens com hold preventivo".
- **Idoso-first.** Nada de copy fofo que dependa de contexto cultural digital.

## Estados visuais (loading / empty / error)

- **Loading**: `<USkeleton>` com forma aproximada. Nunca spinner solto centralizado.
- **Empty**: `<UEmpty>` com `icon`, `title`, `description`, `:actions=[{label, to, icon}]`.
- **Error**: `<UAlert color="error" variant="soft" :title :description>`.

Toast: `useToast().add({icon, color, title, description})` para feedback transitório.
Modal: `<UModal>` para confirmações destrutivas/decisão.

## Imagens

Hero: 1600px wide, `auto=format&fit=crop&q=80` (Unsplash). `loading="eager"`.
Cards: 800px wide, `loading="lazy"`. Aspect ratio fixo via `aspect-4/3`.
Avatar: `<UAvatar>` com `text` (iniciais) fallback. Nunca `<img>` solto pra avatar.

## :ui overrides — limite duro

Se você está prestes a escrever `:ui="{ ... }"` em um componente:

1. O prop `variant` resolve? Use o variant.
2. O prop `size` resolve? Use o size.
3. Slot resolve? Use slot.
4. **Só então** `:ui` com **uma** classe override.

Anti-pattern:
```vue
<UCard :ui="{ root: 'rounded-xl shadow-lg', body: 'p-6 sm:p-8', header: 'border-b-2' }" class="bg-amber-50">
```

Pattern:
```vue
<UCard variant="subtle">
```

## Estrutura de pastas Nuxt

```
app/
  components/        Componentes reutilizáveis. Nome PascalCase, prefixo opcional.
                     Ex: ProductCard.vue, CartLineItem.vue, AddressFormModal.vue.
  composables/       useShopSession, useCartState, useReorder, useGoogleMaps.
                     Sempre `use*`, retorno reativo (refs/computed).
  pages/             Rotas. Cada página é fina — delega lógica a composables, layout a componentes.
  layouts/           default.vue, e variantes para superficies (ex: `auth.vue`).
  plugins/           Bootstrap client/server (ex: session.client.ts).
  types/             Tipos compartilhados (shopman.ts mirror dos projections Django).
  utils/             Helpers puros (sem reativo, sem composição).
  assets/css/        main.css com tokens globais e overrides mínimos.
server/              Proxy para Django. `[...path].ts` por superfície.
```

## Testando o design

Antes de marcar uma tela como pronta:

1. **Mobile 375×812** primeiro. Tudo legível? Botões alcançáveis com polegar? Bottom-bar não cobre conteúdo?
2. **Desktop 1280×800**. Não exagera no espaço — max-width consistente.
3. **Dark mode**. Tokens funcionam? Imagens têm contraste? Imagens decorativas sem `alt`.
4. **Sem JS**: SSR renderiza algo útil?
5. **Idoso na tela**: peça pra alguém de 70+ usar. Sério.

## Deprecations / banidos

- `bg-{color}-{shade}` solto fora de Nuxt UI components → use `color` prop.
- `text-gray-*`, `text-amber-*` etc. → use tokens semânticos.
- `:onclick="..."`, `document.getElementById` → use `@click`, refs Vue.
- `prose` em conteúdo de aplicação → use hierarquia tipográfica acima.
- `style="..."` inline → Tailwind utility ou `:ui`.
- `:ui` com mais de 1 chave sem motivo justificado em comentário.
- `text-xs` em parágrafo de body.
