# WP-GAP-14 — Availability + Substitutes UX (kintsugi no shortage)

> Backend `availability.decide` + Offerman substitutes engine estão completos; UI que entrega o momento *kintsugi* (erro → oferta) ainda está parcial. Prompt auto-contido.

**Status**: Ready to start
**Dependencies**: nenhuma (backends prontos)
**Severidade**: 🟠 Média. O caso de uso mais bonito do design do sistema (shortage transformado em sugestão) não está plenamente realizado na storefront.

---

## Contexto

### O backend existente

- `availability.decide(sku, qty, channel_ref, target_date)` ([shopman/shop/services/availability.py](../../shopman/shop/services/availability.py)) retorna `{approved, reason_code, available_qty, is_paused, is_planned, ...}`.
- `substitutes.find_substitutes(sku, limit, same_collection)` ([packages/offerman/shopman/offerman/contrib/substitutes/substitutes.py](../../packages/offerman/shopman/offerman/contrib/substitutes/substitutes.py)): score keywords 3pts + coleção 2pts + price proximity 1pt.
- `CartService.add_item` ([shopman/shop/web/cart.py](../../shopman/shop/web/cart.py)) em shortage levanta `CartUnavailableError(sku, requested, available, is_paused, substitutes, error_code)` **já com substitutes anexados**.

### A UX incompleta

- Storefront hoje mostra **erro** quando add falha — não propõe alternativas de forma pronunciada.
- Partial `shopman/shop/templates/storefront/partials/stock_error_modal.html` existe, mas:
  - Apresenta erro e lista; não sempre com as substitutes.
  - Não é "oferta calorosa" (C3 omotenashi) — é mais "falha técnica".
- Caso `is_paused` (produto desativado hoje mas voltará) e `is_planned` (vem no próximo lote) tratados genericamente — copy idêntica.

### O intent (omotenashi C3, kintsugi)

"Radical transparency, gentle tone, zero melodrama. Nunca esconder info negativa. Comunicar calor. Nunca virar drama."

Caso ideal:
1. Cliente clica "Adicionar" no croissant.
2. Stock esgotou entre load e clique. Backend já detecta, levanta CartUnavailableError com substitutes.
3. UI **NÃO** mostra toast "out of stock". UI mostra:
   - **Modal acolhedor**: "Ih, o último croissant acabou de sair 😔 → [Pain au Chocolat do mesmo lote, R$ 10,90, 'Tão quentinho quanto'] [Brioche Nanterre, R$ 9,90, 'Se você gosta do croissant, vai amar']"
   - Ação em 1 clique para adicionar substitute.
4. Se `is_planned`: "O próximo lote sai às 15:00. Quer pré-reservar?" (planned hold).
5. Se `is_paused`: "Voltamos em breve 🌾. Me avise!" (notify-me subscription — WP futuro, vide memória).

---

## Escopo

### In

**UX (storefront)**:

- Rework `stock_error_modal.html` em partial Penguin UI v4:
  - Header acolhedor (não "Error").
  - Imagem do produto esgotado (grayscale, slight opacity) com copy "acabou".
  - Lista de substitutes como **cards clicáveis** (imagem + nome + preço + razão).
  - Botão "Adicionar [substitute]" — 1 clique substitui ou adiciona.
  - Tratamento distintivo de casos:
    - **Shortage com substitutes**: mostra sugestões + "por enquanto".
    - **is_planned (vem no próximo lote)**: CTA "Reservar no próximo lote" (hold planned com `demand_ok`).
    - **is_paused (pausado)**: copy "Voltamos em breve" + placeholder para "Me avise" (feature futura, não escopo deste WP).
- Inline feedback no catálogo (`_catalog_item_grid.html`): produto com `is_planned=True` já mostra badge "Amanhã" (verificar — pode já existir via SSE stock events).
- PDP (product detail): quando produto está unavailable, seção "Veja também" com substitutes — mas **não** confundir com "Veja também" futuro (memória project_pdp_veja_tambem_pending.md).

**Acessibilidade**:
- Modal com `role="dialog"`, focus trap, Escape fecha, overlay dismiss.
- Screen reader annonces a alternativa.
- Botões com 48px touch target.

**HTMX + Alpine**:
- Modal disparado via `HX-Trigger` em response de `/cart/add/` quando error.
- Substitute add re-dispara `/cart/add/` com novo SKU — mesma lógica, zero JavaScript extra.

### Out

- "Me avise quando chegar" (notify-me subscription) — memória `project_notify_me_pending.md`. WP futuro.
- "Veja também" proactive em PDP (descoberta lateral por keywords) — memória `project_pdp_veja_tambem_pending.md`. Diferente de substitutes-em-shortage.
- Trocar Offerman substitutes algorithm — fora.
- Notificações push de restock — fora.

---

## Entregáveis

### Edições

- [shopman/shop/templates/storefront/partials/stock_error_modal.html](../../shopman/shop/templates/storefront/partials/stock_error_modal.html): rewrite em Penguin UI v4 + 3 variantes (shortage/planned/paused).
- [shopman/shop/web/cart.py](../../shopman/shop/web/cart.py): ensure `CartUnavailableError` passa `error_code` distinguindo os 3 casos; include `planned_target_date` quando `is_planned`.
- [shopman/shop/web/views/cart.py](../../shopman/shop/web/views/cart.py) AddToCart handler: emite `HX-Trigger: open-stock-error-modal` com payload do erro.
- Alpine listener no `base.html` ou componente modal: abre modal com payload.
- Testes em `shopman/shop/tests/test_stock_error_ux.py` (arquivo já existe — estender):
  - Modal renderiza com substitutes corretos.
  - Click em substitute dispara add do SKU novo.
  - Case `is_planned` mostra CTA "Reservar".
  - Case `is_paused` mostra placeholder "voltamos".

### Copy (via WP-GAP-03 Omotenashi tag)

- Novas keys:
  - `shortage_generic` → "Ih, o último acabou de sair :("
  - `shortage_substitutes_intro` → "Que tal um destes no lugar?"
  - `planned_offer` → "O próximo lote sai às {time}. Quer pré-reservar?"
  - `paused_copy` → "Voltamos em breve!"
- Adicionar à `OMOTENASHI_DEFAULTS` em [shopman/shop/omotenashi/copy.py](../../shopman/shop/omotenashi/copy.py).

---

## Invariantes a respeitar

- **HTMX ↔ servidor, Alpine ↔ DOM**: modal é Alpine; add é HTMX.
- **Copy via `{% omotenashi %}` tag** (depende de WP-GAP-03 Fase 1 — se merge ainda não aconteceu, usar strings inline temporárias com `{# copy-ok: migrar após WP-GAP-03 #}`).
- **Penguin UI v4 tokens**: stone-based, orange-900 primary.
- **48px touch targets**, 16px+ body.
- **Zero MELODRAMA** (omotenashi C3): "acabou" sem drama, com alternativa pronta.
- **Acessibilidade modal**: focus trap + ESC + overlay click.
- **Kintsugi preserved**: erro vira oferta, nunca só erro.

---

## Critérios de aceite

1. Cliente tenta add croissant esgotado → modal bonito com 3 substitutes (score by Offerman engine).
2. Click em "Adicionar Pain au Chocolat" → item adicionado ao cart, modal fecha, cart badge atualiza.
3. Tentar add produto `is_planned` com target_date amanhã → modal com CTA "Reservar no próximo lote" (cria planned hold).
4. Tentar add produto `is_paused` → modal copy "Voltamos em breve".
5. Screen reader annoounce modal open + opções.
6. ESC fecha modal; overlay click fecha.
7. Mobile (375px viewport) — modal responsivo, botões com 48px.
8. `make test` verde (incluindo `test_stock_error_ux.py` estendido).

---

## Referências

- [shopman/shop/services/availability.py](../../shopman/shop/services/availability.py) `decide()`.
- [packages/offerman/shopman/offerman/contrib/substitutes/substitutes.py](../../packages/offerman/shopman/offerman/contrib/substitutes/substitutes.py).
- [shopman/shop/web/cart.py](../../shopman/shop/web/cart.py) `CartService.add_item` + `CartUnavailableError`.
- [shopman/shop/templates/storefront/partials/stock_error_modal.html](../../shopman/shop/templates/storefront/partials/stock_error_modal.html) (rewrite target).
- Memórias:
  - [project_stock_ux_spec.md](.claude/memory) — spec canônica em STOCK-UX-PLAN.
  - [project_notify_me_pending.md](.claude/memory) — feature futura, fora deste WP.
  - [project_pdp_veja_tambem_pending.md](.claude/memory) — diferente de substitutes.
- [docs/plans/STOCK-UX-PLAN.md](STOCK-UX-PLAN.md) — plano existente (escopo adjacente).
- [docs/omotenashi.md](../omotenashi.md) — corolário C3 + kintsugi.
- [WP-GAP-03](WP-GAP-03-omotenashi-copy.md) — copy tag + defaults.
