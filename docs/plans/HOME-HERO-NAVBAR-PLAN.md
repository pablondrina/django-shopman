# HOME / HERO / NAVBAR — Plano do arco (composição/beleza, neutro)

> Iniciativa [[project_excellence_refactor_initiative]] · superfície
> `surfaces/storefront-uithing-nuxt` · branch `redesign/surface-excellence`.
> **Este arco é COMPOSIÇÃO / PRESENÇA / BELEZA — não theming/marca** (cor e
> tipografia de marca são um arco SEPARADO e POSTERIOR). Beleza por composição,
> contraste e ritmo; neutro primeiro. Copy do hero segue 100% server-driven
> (`hero_copy`/OmotenashiCopy). Co-author: Claude Fable 5.

Motivação (Pablo, 2026-06-14): a home antiga (Django :8000) ainda parece **mais
bonita** que a nova (Nuxt :3000), sobretudo **navbar e hero** — densidade,
presença, contraste, "cara de marca". Este arco fecha essa diferença.

---

## Auditoria comparativa (:8000 Django vs :3000 Nuxt, 375px + desktop)

Comparação feita ao vivo com ambas as homes carregadas (foto do hero presente nos
dois lados). O que a antiga acerta e a nova erra:

### NAVBAR / HEADER — a nova está tímida e sub-marcada
| Aspecto | Django :8000 (acerta) | Nuxt :3000 (erra) |
|---|---|---|
| Wordmark | `text-xl font-bold` (~20px, bold) | `text-sm font-semibold` (~14px) — **lê como label, não marca** |
| Ícone | `text-2xl` destacado | `size-5` dentro de caixa `size-8` — miúdo |
| Altura/respiro | `px-6 py-4` substancial | `h-14` enxuto |
| Âncora à direita (mobile) | botão hambúrguer `size-11` (presença) | **nada** — nav e carrinho são `hidden md:flex` → header vazio à direita |

Resultado: o header Nuxt no mobile é só um ícone pequeno + nome pequeno à
esquerda e um grande vazio à direita. Falta peso e presença de marca.

### HERO — composição menos premium e CTA que some
| Aspecto | Django :8000 (acerta) | Nuxt :3000 (erra) |
|---|---|---|
| **CTA** | pílula **branca sólida** (`bg-white text-neutral-900`) — alto contraste, convida | `UiButton` default (fundo escuro) **sobre gradiente escuro** → baixo contraste, some na foto |
| Layout | **pôster**: headline centralizado vertical (`flex-1`) + CTA ancorado embaixo (`pb-14`) → ritmo editorial, respiro | stack apertado: headline+sub+CTA juntos no centro |
| Peso do título | `font-bold tracking-tight` + `drop-shadow-lg` (profundidade/legibilidade) | `font-semibold`, sem drop-shadow |
| Setas/dots | `bg-white/20 backdrop-blur` (presença) | `bg-white/15` ghost (mais apagadas) |

CTA é a maior perda visual: na foto do croissant o botão escuro quase desaparece.

### ROBUSTEZ (achado técnico)
O crossfade do hero usa um único `<Transition name="hero-fade">` com troca de
`:key`. Em navegação SPA / sessão longa de dev (HMR) ele **orfana elementos**:
acumulam vários `<img>` presos em `hero-fade-enter-from` (opacity:0) → o hero vira
um **cinza chapado sem foto** (reproduzido ao vivo: 4 imgs empilhados, opacity 0
persistente). Numa carga limpa funciona (1 img, opacity 1), mas o padrão é frágil.
A reconstrução do hero deve usar **slides empilhados + opacity por classe**
(sem enter/leave do Vue a orfanar) — robusto e ainda neutro.

### SHELL
- Banner de pedido ativo (marrom escuro, full-width) entre header e hero: útil,
  mas é uma laje pesada que corta o hero do header e come altura da 1ª dobra.
  Candidato a refino leve (sub-arco 3), mantendo a função.
- Pílula "Buscar no cardápio" abaixo do hero: boa, manter.
- Corpo (featured rail, "Como você preferir", WhatsApp CTA, rodapé): aceitável;
  ritmo/presença podem melhorar, mas é prioridade menor que hero+navbar.

---

## Plano em sub-arcos

### Sub-arco A — NAVBAR/HEADER (presença de marca) · `ShopHeader.vue`
- Wordmark maior e mais forte (≈`text-lg`/`text-xl`, `font-bold`), ícone maior,
  mais respiro vertical (mobile `h-16`). Mantém sticky, mantém `brand_name`
  server-driven (neutro — sem cor/fonte de marca).
- Âncora à direita no mobile (decisão do Pablo — ver Decisões).
- Atualizar `surfaceGuardrails`/`canonicalEndpoints` se pinarem strings do header.
- Commit por tela. Verificar 375px + desktop, console limpo.

### Sub-arco B — HERO (composição/presença/1ª dobra) · `HomeHeroThing.vue` + `tailwind.css`
- **CTA alto-contraste** (pílula clara sobre o gradiente) — reverte o "botão que
  some". Neutro (branco/`background`, não cor de marca).
- **Layout pôster**: headline no centro vertical, CTA ancorado mais abaixo —
  ritmo editorial como o Django.
- Título `font-bold` + `drop-shadow` para profundidade e legibilidade.
- Setas/dots com um pouco mais de presença.
- **Crossfade robusto** (slides empilhados + opacity por classe; mata o bug do
  cinza/HMR). Mantém autoplay 8s, swipe, reduced-motion, copy server-driven.
- Reconciliar altura do hero com o banner de pedido ativo (1ª dobra cheia).
- Commit. Verificar 375px + desktop, sem erro de hidratação, console limpo.

### Sub-arco C — CORPO DA HOME (ritmo/seções/rodapé) · `index.vue` *(escopo a confirmar)*
- Presença do heading do featured rail; ritmo/espaçamento entre seções.
- Refino leve do banner de pedido ativo (menos laje, mais integrado).
- Cartões "Como você preferir" e CTA WhatsApp: hierarquia/respiro.
- Commit. Verificar 375px + desktop.

---

## Decisões de UX (Pablo) — TRAVADAS (2026-06-15)
1. **Âncora à direita do header**: **hambúrguer "lindão"** abrindo um menu rico,
   limpo e organizado com acesso a tudo — Cardápio, Carrinho, Conta, Como funciona,
   Como chegar, Horário de atendimento, Contato (telefone/e-mail/WhatsApp) e Redes
   sociais. Usa o `UiSheet` canônico (reka, sem lib externa). Bottom-nav segue.
   Dados já disponíveis via `session.shop` (full_address, maps_url, phone_url,
   phone_display, email, whatsapp_url, **social_links**) + `session.openingHours`.
2. **CTA do hero**: **pílula branca sólida** alto-contraste (neutro).
3. **Escopo**: **incluir o corpo da home** (sub-arcos A + B + C).

> "Como funciona" no Nuxt não tem rota dedicada (existe a seção "Como você
> preferir" na home). O item do menu aponta para essa seção (âncora) — decisão
> de implementação, sem inventar página nova.

---

## Gates (rodar de DENTRO de `surfaces/storefront-uithing-nuxt`)
- `npx vitest run` + `npx nuxt build`. Backend (se tocar): `.venv/bin/pytest shopman/storefront/tests`.
- `surfaceGuardrails.test.ts` / `canonicalEndpoints` pinam strings exatas dos
  `.vue` — atualizar junto, não só apagar.
- Verificação ao vivo 375px + desktop, console limpo, sem hydration mismatch.
  reka 2.x: `v-model`/`:model-value`. Botões reka: PointerEvent na verificação.

## Estado inicial
Branch `redesign/surface-excellence`, último commit `0b9df3cb`. Verde (vitest 202,
backstage 80 + admin 63, storefront 863).
