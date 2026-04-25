# Plano Temporário — Fix UX: Adicionar ao Carrinho (Cardápio ↔ PDP)

Data: 2026-04-15
Status: Pendente
Escopo: Pequeno (template + Alpine, sem tocar em view/service)
Arquivar em: `docs/plans/completed/` ao concluir.

---

## Contexto do Problema

No cardápio (listagem de produtos), o usuário relata que clicar em "adicionar" adiciona o produto ao carrinho **e** navega para a PDP (product detail page). Isso quebra o modelo mental: parece que a PDP existe para "confirmar a quantidade", mas clicar de novo lá adiciona novamente.

### Caracterização real (investigado em 2026-04-15)

- Template: [shopman/shop/templates/storefront/partials/product_card.html](../../shopman/shop/templates/storefront/partials/product_card.html)
  - Linhas 3-81: card envolvido por `<a href="{% url 'storefront:product_detail' item.product.sku %}">` (imagem, nome, preço dentro do link)
  - Linhas 84-113: botão "Adicionar" com `hx-post` tecnicamente **após** o `</a>`
- Endpoint: [shopman/shop/web/views/cart.py:30](../../shopman/shop/web/views/cart.py) `AddToCartView` retorna HTMX partial (badge), **não redireciona**. `HX-Trigger: cartUpdated`.
- `CartService.add_item` em [shopman/shop/web/cart.py:87](../../shopman/shop/web/cart.py) faz merge correto por SKU (soma qty existente via `set_qty`).
- PDP em [shopman/shop/templates/storefront/product_detail.html:178](../../shopman/shop/templates/storefront/product_detail.html) tem stepper Alpine que lê qty e posta no mesmo endpoint.

### Diagnóstico

O **backend está correto**. A confusão é 100% de UX:
1. Clique no botão pode vazar para a área do link ancestral (dependendo de onde cai), causando navegação não intencional.
2. Feedback do add-to-cart é só o badge do header — imperceptível no card do produto.
3. Botão fixo em `qty=1` no cardápio + stepper no PDP → usuário assume que PDP é pra "confirmar qty", quando na verdade já adicionou.

---

## Best Practice Adotada

Padrão **iFood/Rappi/UberEats** (stepper inline no card), adequado ao Nelson Boulangerie e a qualquer food/retail:

- **Tocar em área do card (imagem, nome, preço) → navega para PDP.** Descoberta de detalhes continua livre.
- **Stepper inline como elemento primário do add-to-cart.**
  - Estado inicial: botão `+` (ou "Adicionar") se `qty_in_cart == 0`.
  - Após primeiro toque: vira `−  N  +` inline, com N refletindo a quantidade atual no carrinho.
  - Cada toque dispara `hx-post` para `cart_add` (+) ou `cart_set_qty` (−) com `event.stopPropagation()` para não acionar o link ancestral.
- **Feedback local**: o próprio stepper é o feedback (N visível). Badge global no header é reforço secundário.
- **PDP continua existindo** para casos que exigem detalhe (observação, variantes, customização, descrição completa). O stepper da PDP é maior e permite ajuste fino com confirmação explícita.
- **Merge por SKU já está correto** no `CartService` — nada muda no backend.

### Contra-indicações / quando fugir do padrão

- Produtos com customização obrigatória (ex: sabor, tamanho) **não devem** ter quick-add no card — o clique deve ir pra PDP direto. Sinalizar via `requires_customization: bool` na projection.
- Produtos por peso (kg/g) podem precisar de campo customizado — tratar como exceção.

---

## Escopo da Mudança

### 1. Template (único arquivo principal)

`shopman/shop/templates/storefront/partials/product_card.html`:
- Separar **fisicamente** a área navegável (link para PDP) do elemento de ação (stepper).
- Substituir o botão atual por componente stepper Alpine:
  ```html
  <div x-data="{ qty: {{ item.qty_in_cart|default:0 }} }"
       @click.stop>
    <template x-if="qty === 0">
      <button hx-post="{% url 'storefront:cart_add' %}"
              hx-vals='{"sku": "{{ item.product.sku }}", "qty": "1"}'
              hx-target="#cart-badge-header"
              hx-swap="innerHTML"
              @htmx:after-request="qty = 1"
              @click.stop>Adicionar</button>
    </template>
    <template x-if="qty > 0">
      <div class="flex items-center gap-2">
        <button @click.stop
                hx-post="{% url 'storefront:cart_set_qty' %}"
                hx-vals="js:{sku: '{{ item.product.sku }}', qty: String(qty - 1)}"
                @htmx:after-request="qty = Math.max(0, qty - 1)">−</button>
        <span x-text="qty"></span>
        <button @click.stop
                hx-post="{% url 'storefront:cart_add' %}"
                hx-vals='{"sku": "{{ item.product.sku }}", "qty": "1"}'
                @htmx:after-request="qty += 1">+</button>
      </div>
    </template>
  </div>
  ```
- Usar apenas classes Tailwind já presentes no projeto (ver [feedback_tailwind_only_existing_classes.md](../../.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/feedback_tailwind_only_existing_classes.md) — sem `bg-amber-*`).

### 2. Context da view (pequeno)

`shopman/shop/web/views/catalog.py` (`MenuView` + `HomeView`):
- Ao montar a lista de produtos, anotar `qty_in_cart` lendo do carrinho atual (via `CartService.get_cart()` ou equivalente). Assim o template já abre com o stepper no estado certo se o usuário recarregar a página ou voltar ao cardápio.

### 3. Endpoint `cart_set_qty` (verificar se já existe)

Verificar em [shopman/shop/web/urls.py](../../shopman/shop/web/urls.py) e [shopman/shop/web/views/cart.py](../../shopman/shop/web/views/cart.py):
- Se `cart_set_qty` já existe como rota, reutilizar.
- Se não existe mas o `ModifyService` já suporta (`op: "set_qty"`), criar thin view.
- Retornar HTMX partial consistente com `cart_add` (badge + trigger `cartUpdated`).

### 4. PDP — pequeno ajuste opcional

O stepper da PDP pode ler o estado inicial do carrinho (`qty_in_cart`) em vez de sempre começar em 1. Isso fecha o loop mental: "já tenho 2 no carrinho, aqui eu ajusto pra 3".

### 5. Testes

- Atualizar [test_web.py](../../shopman/shop/tests/test_web.py) se houver teste que espere o botão antigo.
- Adicionar teste cobrindo: `qty_in_cart` corretamente anotado no context da MenuView quando há item no carrinho.

---

## O que NÃO fazer

- **Não** mexer em `CartService.add_item` — o merge por SKU já está correto.
- **Não** criar "toast" / modal de confirmação. O stepper visível é feedback suficiente.
- **Não** tentar resolver isto via projection (esse plano é pré-projection — ver [PROJECTION-UI-PLAN.md](PROJECTION-UI-PLAN.md)). Quando a fase 1 das projections chegar, o stepper vai naturalmente consumir `CatalogItemProjection.qty_in_cart` em vez de annotation ad-hoc. Esta mudança é tática, pra não deixar o bug ativo enquanto esperamos projections.
- **Não** duplicar lógica entre MenuView e HomeView — extrair helper se necessário.

---

## Quando executar

- **Depois** dos commits pendentes estarem organizados (a leva backend em trânsito).
- **Antes** ou em paralelo com o início da Fase 1 do PROJECTION-UI-PLAN (quando a Fase 1 migrar `menu.html` para `CatalogProjection`, o stepper já vai estar no lugar certo — só muda a fonte do `qty_in_cart`).

---

## Ao concluir

1. Mover este arquivo para `docs/plans/completed/`.
2. Remover o link do ROADMAP (seção "Pendências Ativas").
3. Atualizar a entrada de memória `project_current_state.md` se relevante.
