# Plano: Sistema de Cores OKLCH — Paleta Completa, Dark Mode Nativo

## Contexto

O storefront tem um sistema de design tokens funcional (WP-D1/D2 entregues), mas a paleta de cores é limitada: 1 cor primária + derivações simples por soma RGB. Não há secondary/accent, o dark mode não existe, e 25+ cores estão hardcoded. O objetivo é um sistema de cores de referência — inspirado em Radix Colors (12-step scale), shadcn/ui (token pairs), e Material Design 3 (seed-to-palette) — usando **OKLCH** (espaço de cor perceptualmente uniforme, nativo do browser).

**Sem backward-compat. Zero legado.** Os nomes `cream/bark/wheat` são eliminados.

## Arquitetura: OKLCH 12-Step Scale

### Input mínimo do Admin: 3 cores + 1 modo
1. **primary_color** — cor da marca (hex). Obrigatória.
2. **secondary_color** — apoio (hex). Vazio = hue +120° da primária.
3. **accent_color** — destaque (hex). Vazio = hue -60° da primária.
4. **neutral_color** — neutro (hex). Vazio = primária com chroma ~0.01.
5. **color_mode** — `light` | `dark` | `auto` (respeita sistema do usuário).

### Output: 12 shades × 4 escalas × 2 modos = ~96 tokens

Cada escala (primary, secondary, accent, neutral) gera 12 steps variando L (lightness) em OKLCH:

```
Light mode:  L = [0.985, 0.965, 0.935, 0.905, 0.870, 0.825, 0.760, 0.680, 0.550, 0.490, 0.390, 0.250]
Dark mode:   L = [0.110, 0.140, 0.170, 0.200, 0.240, 0.290, 0.350, 0.420, 0.550, 0.610, 0.720, 0.930]
```

Step 9 (L=0.550) é a "cor da marca" — idêntica em light e dark.

### Mapeamento semântico (shadcn-inspired)

```css
/* Superfícies */
--background:         neutral-1       /* fundo da página */
--surface:            neutral-2       /* cards, modals */
--surface-hover:      neutral-3       /* hover em cards */
--muted:              neutral-4       /* disabled, secondary bg */
--border:             neutral-6       /* bordas, dividers */
--border-strong:      neutral-7       /* bordas fortes */
--ring:               primary-8       /* focus rings */

/* Texto */
--foreground:         neutral-12      /* texto principal */
--foreground-muted:   neutral-11      /* texto secundário */

/* Interativo */
--primary:            primary-9       /* botões, CTAs */
--primary-hover:      primary-10      /* hover */
--primary-foreground: white           /* texto em bg primary */

--secondary:          secondary-3     /* bg subtil de apoio */
--secondary-hover:    secondary-4
--secondary-foreground: secondary-11

--accent:             accent-9        /* destaque */
--accent-hover:       accent-10
--accent-foreground:  white

/* Status (hues fixos, não configuráveis) */
--success[-light|-foreground]:  hue=145°
--warning[-light|-foreground]:  hue=75°
--error[-light|-foreground]:    hue=25°
--info[-light|-foreground]:     hue=250°
```

## Fases de Implementação

### Fase 1: Módulo de cores `shop/colors.py` (NOVO)

Pure Python, zero dependências externas. Conversões sRGB↔OKLab↔OKLCH via matrizes do paper de Björn Ottosson.

**Funções:**
- `hex_to_oklch(hex) → (L, C, H)`
- `oklch_to_hex(L, C, H) → hex` (com gamut clamping)
- `oklch_to_css(L, C, H) → "oklch(0.550 0.150 85.0)"`
- `generate_scale(hue, chroma, is_dark) → dict[1..12, css_string]`
- `generate_design_tokens(primary_hex, secondary_hex, accent_hex, neutral_hex, color_mode) → dict`

**Chroma tapering**: `step_chroma = base_chroma * min(1.0, 2.5 * min(L, 1-L))` — reduz saturação nos extremos (muito claro/escuro) para evitar gamut overflow.

**Auto-derivação** (quando campo vazio):
- secondary: hue +120°, chroma ×0.8
- accent: hue -60°, chroma ×1.0
- neutral: mesmo hue, chroma 0.01

### Fase 2: Shop model (`shop/models.py`)

**Remover campos**: `background_color`, `text_color`, `text_muted_color`, `surface_color`, `border_color`
**Remover função**: `_adjust_hex()`
**Adicionar campos**: `secondary_color`, `accent_color`, `neutral_color`, `color_mode`
**Reescrever**: `design_tokens` property → chama `colors.generate_design_tokens()`

O `design_tokens` retorna dict com ~40 tokens light + ~40 tokens dark + `background_hex`/`theme_hex` (fallback para PWA manifest).

### Fase 3: Migração `shop/migrations/0010_oklch_color_system.py`

AddField × 4, RemoveField × 5. Sem data migration — defaults cobrem tudo.

### Fase 4: Admin (`shop/admin.py`)

Novo fieldset "Paleta de Cores" com secondary/accent/neutral + color_mode. `primary_color` fica em "Branding".

**Color picker nativo** via `UnfoldAdminColorInputWidget` (já existe no Unfold instalado):
```python
from unfold.widgets import UnfoldAdminColorInputWidget

class ShopForm(forms.ModelForm):
    class Meta:
        model = Shop
        fields = "__all__"
        widgets = {
            "primary_color": UnfoldAdminColorInputWidget,
            "secondary_color": UnfoldAdminColorInputWidget,
            "accent_color": UnfoldAdminColorInputWidget,
            "neutral_color": UnfoldAdminColorInputWidget,
        }

@admin.register(Shop)
class ShopAdmin(ModelAdmin):
    form = ShopForm
```

O picker do browser (Chrome/Safari/Firefox) já oferece HSL, RGB, hex e eyedropper nativamente. Zero JS custom, zero pacote extra.

Os campos aceitam e armazenam hex (`#RRGGBB`). O picker do browser converte HSL→hex automaticamente ao selecionar. O campo exibe o swatch de cor ao lado do input.

### Fase 5: `_design_tokens.html` — Rewrite completo

Gera:
- CSS `:root { --background: oklch(...); --foreground: oklch(...); ... }`
- Dark mode: `@media (prefers-color-scheme: dark)` (auto) ou `.dark` (forçado)
- Tailwind config com semantic colors → `var(--*)`
- Google Fonts + Alpine + HTMX CDN links

**Tailwind darkMode**: `'media'` se auto, `'class'` se light/dark.

### Fase 6: `base.html` — Limpar legado

- **Eliminar** bloco JS backward-compat (aliases cream→background, bark→text, wheat→primary)
- **Eliminar** bloco CSS backward-compat (--color-cream, --color-bark, --color-wheat)
- **Atualizar** `<html>` com classe dark condicional
- **Atualizar** `<body class>`: `bg-cream text-bark` → `bg-background text-foreground`
- **Atualizar** header, footer, spinner, modal, badges — tudo com nomes novos

### Fase 7: Migração de 36 templates (~551 substituições)

Mapeamento completo:

| Antigo | Novo |
|--------|------|
| `bg-cream` | `bg-background` |
| `bg-white` | `bg-surface` |
| `text-bark` | `text-foreground` |
| `text-bark-light` | `text-muted-foreground` |
| `bg-wheat` | `bg-primary` |
| `hover:bg-wheat-dark` | `hover:bg-primary-hover` |
| `text-wheat-dark` | `text-primary` |
| `border-cream-dark` | `border-border` |
| `bg-red-50` | `bg-error-light` |
| `text-red-*` | `text-error` |
| `bg-amber-50` | `bg-warning-light` |
| `text-amber-*` | `text-warning` |
| `bg-green-50` | `bg-success-light` |
| `text-green-*` | `text-success` |
| `font-serif` | `font-heading` |
| `var(--color-*)` | `var(--*)` |

### Fase 8: PWA (`pwa.py`) + Seed + Tests

- `ManifestView`: `config.background_color` → `tokens["background_hex"]`
- `seed.py`: remover `background_color` do seed
- 4 test fixtures: remover `background_color=` do Shop.objects.create()
- **Novo**: `shop/tests/test_colors.py` com 15 test cases (roundtrip, scale, derivation, tokens)

## Arquivos

| Arquivo | Ação |
|---------|------|
| `shop/colors.py` | **NOVO** — módulo OKLCH |
| `shop/models.py` | Reescrever campos + design_tokens |
| `shop/admin.py` | Novo fieldset |
| `shop/migrations/0010_*.py` | Add/Remove fields |
| `shop/tests/test_colors.py` | **NOVO** — 15 tests |
| `partials/_design_tokens.html` | Rewrite completo |
| `base.html` | Eliminar legado, migrar classes |
| 35 templates restantes | Find-replace ~551 ocorrências |
| `pwa.py` | Hex fallback |
| `seed.py` | Remover campo removido |
| 4 arquivos de teste | Remover campo removido |

## Verificação

1. `make test` — 970+ passam
2. `make run` → Admin → mudar primary_color → toda UI reflete
3. Admin → color_mode "dark" → toda UI inverte
4. Admin → color_mode "auto" → respeita `prefers-color-scheme`
5. Admin → secondary/accent vazios → derivados automaticamente
6. Lighthouse: contrast ratios AA+ em ambos os modos
