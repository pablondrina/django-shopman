# SEO-PLAN — SEO como capítulo próprio do storefront

> **SEO não é afterthought.** O storefront é um site web. Tráfego orgânico é um canal
> de aquisição como qualquer outro. Este doc é a fonte única da verdade para
> SEO técnico (meta tags, schema, sitemap, robots, canonical, performance).

## Princípio

**Uma única fonte de verdade alimenta três superfícies:**

```
Product.keywords  ──┬──▶  Alternatives / busca (scoring)
                    ├──▶  Meta keywords + body semantics
                    └──▶  Schema.org / Open Graph tags
```

Quando o operador cura bem as keywords do produto, ganha de graça: UX interna
(busca, alternatives, "produtos similares") + rankeamento orgânico externo.

Mesma lógica para `short_description` (= meta description + og:description),
`image_url` (= og:image + schema image), `base_price_q` (= schema offer),
`long_description` (= body semantics para LSI).

## Estado atual

### Já existe
- ✅ `Product.keywords` (django-taggit) — curadoria por SKU.
- ✅ `robots.txt` em `storefront/robots.txt` — básico.
- ✅ `sitemap.xml` em `SitemapView` — lista URLs de home/menu/coleções/produtos, com priority/changefreq.
- ✅ `<meta description>` via `{% block meta_description %}` em base.html.
- ✅ Open Graph tags básicas (`og:title`, `og:description`, `og:type`, `og:locale`, `og:site_name`) em base.html.
- ✅ Favicons, theme-color, manifest PWA.

### Lacunas
- ❌ **`og:image`** não é gerado por produto (só usa logo como fallback). Precisa `Product.image_url` quando na PDP.
- ❌ **`og:url`** ausente — canonical precisa estar correto.
- ❌ **`<link rel="canonical">`** ausente — pode gerar duplicate content nas filtragens.
- ❌ **Twitter Card** tags ausentes.
- ❌ **Schema.org JSON-LD** ausente — Product, Offer, LocalBusiness, Bakery, BreadcrumbList.
- ❌ **Meta keywords** não usa `Product.keywords` na PDP.
- ❌ **Sitemap** não inclui `<image:image>` nem `lastmod` real (usa apenas priority/changefreq estáticos).
- ❌ **Meta description** na PDP usa `short_description|truncatewords:20` (genérico) — não é otimizada.
- ❌ **hreflang** (se houver variantes locale no futuro) — não aplicável por ora.
- ❌ **FAQ schema** em página Como Funciona — seria rico snippet gratuito.

## WPs propostos

### WP-SEO-1 — Meta tags essenciais na PDP
- Tag `<link rel="canonical" href="{absolute PDP URL}">` em base.html com sobrescrita possível.
- `og:image` = `product.image_url` na PDP, com fallback para `storefront.logo`.
- `og:url` absoluto.
- Twitter Card (`summary_large_image`) com mesmos assets.
- `meta keywords` populado por `Product.keywords` **somente** na PDP (outras páginas não precisam).
- Meta description da PDP: composição priorizada — `short_description` > primeiros 160 chars de `long_description` > fallback atual.

### WP-SEO-2 — Schema.org / JSON-LD
- Template tag `{% schema_org 'product' product %}` renderiza `<script type="application/ld+json">` com:
  - `@type: Product` com `name`, `description`, `image`, `sku`, `brand`, `offers` (`@type: Offer`, `priceCurrency`, `price`, `availability`, `url`).
  - `@type: BreadcrumbList` com `itemListElement` a partir do breadcrumb da página.
- Homepage: `@type: Bakery` (subtype de `FoodEstablishment`/`LocalBusiness`) com `address`, `openingHoursSpecification`, `image`, `priceRange`.
- "Como Funciona" com perguntas-resposta: `@type: FAQPage`.

### WP-SEO-3 — Sitemap enriquecido
- `<image:image>` por produto (Google Image Search).
- `lastmod` real via `Product.updated_at` / `Shop.updated_at`.
- Opcional: sitemap separado para images e uma `<sitemapindex>` quando catálogo crescer.

### WP-SEO-4 — Performance / Core Web Vitals
- `<link rel="preload">` para fontes críticas (já temos `preconnect`, faltam as fontes específicas em crawler time).
- `loading="lazy"` já em imagens secundárias. Auditar primeira image (LCP) — usar `loading="eager"` + `fetchpriority="high"`.
- Tailwind output cacheado com hash (já tem — `output-v2.css`).
- Admin flag para desligar preview/reload scripts em produção.

### WP-SEO-5 — Busca interna
- Implementar busca no cardápio usando o **mesmo scoring de `_score_candidates`** (keywords × name similarity × collection × price proximity).
- Reabilitar a URL `menu/search/` que foi removida — agora com motor consistente.
- Input sticky no header do menu ("Buscar no cardápio"), HTMX com debounce.

## Reuso entre SEO e UX interna

Keywords são o pivô. **Curadoria de keywords é curadoria de SEO** — a mesma
ação ajuda três superfícies. O operador não precisa pensar "isso é pra SEO"
ou "isso é pra busca interna" — preenche uma vez, sistema distribui.

Similaridade de nome (implementada em `_score_candidates`) serve alternatives
**e** busca interna quando WP-SEO-5 for executado. Mesmo motor, mesmo ranking,
mesma experiência — menos surpresa pro operador e pro cliente.

## Regras invariantes

- **Uma única fonte** por conceito SEO — centralizar em template tags ou context
  processor, nunca duplicar.
- **Schema bem formado** — testar com [Rich Results Test](https://search.google.com/test/rich-results) antes de mergar.
- **Performance first** — SEO técnico que derruba LCP não vale a pena.
- **Descrições humanas** — zero keyword-stuffing. Google detecta e penaliza.
- **Sitemap honesto** — só URLs realmente indexáveis; `noindex` onde precisar
  (checkout, confirmações, etc.).
