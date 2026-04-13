# WP-F8: Gestor de Pedidos — Painel do Operador

## Context

F0-F7 (storefront completo) estão ✅. F8 é o primeiro WP do lado operador: uma view standalone
(`/pedidos/`) onde o operador gerencia o ciclo de vida dos pedidos de todos os canais.
Benchmark: iFood para Restaurantes. NÃO é KDS — é gestão macro.

**Pré-requisito**: venv funcional (`source .venv/bin/activate && make test-framework` deve passar).

---

## Arquivos a criar

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `shopman/web/views/pedidos.py` | View | GestorPedidosView + partials + actions |
| `shopman/web/templates/pedidos/base.html` | Template | Base standalone (não herda storefront) |
| `shopman/web/templates/pedidos/index.html` | Template | Layout principal (extends pedidos/base.html) |
| `shopman/web/templates/pedidos/partials/card.html` | Template | Card de pedido |
| `shopman/web/templates/pedidos/partials/detail.html` | Template | Card expandido (accordion) |
| `shopman/web/templates/pedidos/partials/order_list.html` | Template | Container dos cards (HTMX target) |
| `shopman/web/static/storefront/js/pedidos.js` | JS | Timer, som, fullscreen, sessionStorage |
| `tests/test_f8_gestor_pedidos.py` | Test | ~12 testes |

## Arquivos a modificar

| Arquivo | Mudança |
|---------|---------|
| `shopman/web/urls.py` | Adicionar rotas `/pedidos/*` |
| `shopman/web/views/__init__.py` | Exportar novas views |
| `shopman/topics.py` | (NÃO adicionar KDS topic — defer para F9) |

---

## Implementação passo a passo

### Step 1: View principal (`shopman/web/views/pedidos.py`)

**Auth**: Usar `request.user.is_staff` check manual (mesmo padrão de `shop/views/production.py`).
Se não autenticado → redirect para `/admin/login/?next=/pedidos/`.

```python
class GestorPedidosView(View):
    def get(self, request):
        if not request.user.is_staff:
            return redirect(f"/admin/login/?next=/pedidos/")

        orders = Order.objects.filter(
            status__in=["new", "confirmed", "processing", "ready"]
        ).select_related("channel").order_by("created_at")

        # Enrich cada order com: timer_seconds, channel_badge, items_summary,
        # fulfillment_type, can_confirm, can_reject, can_advance
        enriched = [_enrich_order(o) for o in orders]

        return render(request, "pedidos/index.html", {
            "orders": enriched,
            "counts": _status_counts(orders),
        })
```

**Helper `_enrich_order(order)`**: Retorna dict com:
- `ref`, `status`, `status_label`, `channel_ref`, `channel_badge` (emoji por canal)
- `customer_name` (de `order.handle_ref` ou `order.data.get("customer_name")`)
- `created_at`, `elapsed_seconds` (seconds since created)
- `timer_class` (verde/amarelo/vermelho baseado nos 5 min de confirmation)
- `items_summary` (primeiros 3 items como "2x Pão Francês, 1x Croissant...")
- `items_count` (total de items)
- `total_display` (R$ formatado)
- `fulfillment_type` (retirada/delivery, de `order.data.get("delivery_method")`)
- `can_confirm` (status == "new")
- `can_advance` (status in confirmed/processing/ready)
- `next_status` e `next_action_label` (contextual)

**Helper `_status_counts(orders)`**: Dict com counts por status para as pills.

### Step 2: Action views (mesmo arquivo)

```python
class PedidoConfirmView(View):
    """POST /pedidos/<ref>/confirm/ — confirma pedido."""
    def post(self, request, ref):
        order = get_object_or_404(Order, ref=ref)
        order.transition_status("confirmed", actor=f"operator:{request.user.username}")
        # Return updated card partial (HTMX swap)

class PedidoRejectView(View):
    """POST /pedidos/<ref>/reject/ — rejeita com motivo obrigatório."""
    def post(self, request, ref):
        reason = request.POST.get("reason", "").strip()
        if not reason:
            return HttpResponse("Motivo obrigatório", status=422)
        order = get_object_or_404(Order, ref=ref)
        order.transition_status("cancelled", actor=f"operator:{request.user.username}")
        order.data["cancellation_reason"] = reason
        order.data["rejected_by"] = request.user.username
        order.save(update_fields=["data", "updated_at"])
        release_holds_for_order(order)
        # Notify customer
        Directive.objects.create(topic=NOTIFICATION_SEND, payload={...})

class PedidoAdvanceView(View):
    """POST /pedidos/<ref>/advance/ — avança status (confirmed→processing, processing→ready, etc)."""
    def post(self, request, ref):
        order = get_object_or_404(Order, ref=ref)
        NEXT = {
            "confirmed": "processing",
            "processing": "ready",
            "ready": "completed",  # ou dispatched se delivery
        }
        next_status = NEXT.get(order.status)
        if not next_status:
            return HttpResponse("", status=422)
        order.transition_status(next_status, actor=f"operator:{request.user.username}")

class PedidoNotesView(View):
    """POST /pedidos/<ref>/notes/ — salva notas internas."""
    def post(self, request, ref):
        order = get_object_or_404(Order, ref=ref)
        order.data["internal_notes"] = request.POST.get("notes", "")
        order.save(update_fields=["data", "updated_at"])

class OrderListPartialView(View):
    """HTMX: retorna lista de cards filtrada (polling)."""
    def get(self, request):
        # Mesmo que GestorPedidosView mas retorna partial
        filter_status = request.GET.get("filter", "new")
        # ...
```

### Step 3: URLs

```python
# Em shopman/web/urls.py, adicionar:
# Operator dashboard
path("pedidos/", views.GestorPedidosView.as_view(), name="gestor_pedidos"),
path("pedidos/list/", views.OrderListPartialView.as_view(), name="gestor_list_partial"),
path("pedidos/<str:ref>/detail/", views.PedidoDetailPartialView.as_view(), name="gestor_detail"),
path("pedidos/<str:ref>/confirm/", views.PedidoConfirmView.as_view(), name="gestor_confirm"),
path("pedidos/<str:ref>/reject/", views.PedidoRejectView.as_view(), name="gestor_reject"),
path("pedidos/<str:ref>/advance/", views.PedidoAdvanceView.as_view(), name="gestor_advance"),
path("pedidos/<str:ref>/notes/", views.PedidoNotesView.as_view(), name="gestor_notes"),
```

### Step 4: Template principal (`pedidos/index.html`)

```
┌─────────────────────────────────────────────────┐
│ Nelson Boulangerie — Gestor de Pedidos    🔊 ⚙️ │
├─────────────────────────────────────────────────┤
│ [Aguardando (3)] [Preparando (2)] [Prontos (1)] │  ← pills com contadores
├──────────────────────┬──────────────────────────┤
│  Card Pedido #001    │  Card Pedido #002        │  ← grid 2 cols
│  🌐 web · 2:34       │  📱 WhatsApp · 0:45      │
│  João Silva          │  Maria Santos            │
│  2x Pão, 1x Café    │  1x Croissant            │
│  🏪 Retirada         │  🚗 Delivery             │
│  [Confirmar][Rejeitar]│  [Confirmar][Rejeitar]   │
├──────────────────────┴──────────────────────────┤
│  Card Pedido #003 (CONFIRMED)                   │
│  [▸ Iniciar Preparo]                            │
└─────────────────────────────────────────────────┘
```

**Estrutura Alpine**:
```html
<div x-data="gestorPedidos()" x-init="init()">
```

**HTMX polling**: `hx-get="/pedidos/list/?filter=..." hx-trigger="every 5s" hx-target="#order-grid"`

**Layout standalone** (`pedidos/base.html`): HTML independente, não herda do storefront.
Inclui: Tailwind output.css, Alpine.js, HTMX, design tokens (_design_tokens.html), fonts.
Sem bottom nav, sem header do storefront, sem footer. Layout otimizado para tablet landscape.
Criar `pedidos/base.html` com:
- `<head>`: meta viewport, output.css, Alpine CDN, HTMX CDN, design tokens
- `<body>`: full-height flex column, header próprio (shop name + hora + som + config + fullscreen)
- `{% block content %}{% endblock %}`
- `<script>` com pedidos.js inline ou referenciado

### Step 5: Card template (`pedidos/partials/card.html`)

Cada card:
- Header: `ref` + canal badge (🌐/📱/🍔/🏪) + timer elapsed
- Timer: Alpine countdown, cores `text-success` (<3min), `text-warning` (3-4min), `text-error` (>4min)
- Body: customer name, items summary (truncado), fulfillment type
- Footer: action buttons contextuais
  - NEW: "Confirmar ✓" (hx-post confirm) + "Rejeitar ✗" (abre campo motivo)
  - CONFIRMED: "Iniciar Preparo ▸" (hx-post advance)
  - PROCESSING: "Marcar Pronto ▸"
  - READY: "Entregar ✓" ou "Despachar 🚗"
- Click no body → expande detail (accordion Alpine x-collapse)

### Step 6: Detail template (`pedidos/partials/detail.html`)

Expandido dentro do card:
- Items completos: nome, qty, preço, subtotal
- Disponibilidade por item: query `StockBackend.check_availability(sku, qty)`
  - ✓ verde (disponível), ⚠ amarelo (em produção — query WorkOrder open com output_ref=sku), ❌ vermelho
- Notas internas (textarea, hx-post notes)
- Mini-timeline (reusa `_build_tracking_context` de tracking.py)
- Campo motivo (textarea, só aparece ao clicar "Rejeitar")

**Stock check**: Usar `StockBackend` do shopman/backends/stock.py:
```python
from channels.backends.stock import StockBackend
backend = StockBackend()
result = backend.check_availability(sku=item.sku, quantity=item.qty)
```

**WorkOrder check** (se indisponível mas em produção):
```python
from shopman.crafting.models import WorkOrder
wo = WorkOrder.objects.filter(output_ref=item.sku, status__in=["planned", "started"]).first()
# Se existe → badge "Em produção"
```

### Step 7: JavaScript (`pedidos.js`)

```javascript
function gestorPedidos() {
  return {
    filter: sessionStorage.getItem('gestor_filter') || 'new',
    soundEnabled: sessionStorage.getItem('gestor_sound') !== 'false',
    compact: sessionStorage.getItem('gestor_compact') === 'true',
    previousCount: 0,

    init() {
      // Watch for new orders (compare count after HTMX swap)
      document.addEventListener('htmx:afterSwap', (e) => {
        if (e.detail.target.id === 'order-grid') {
          var newCount = e.detail.target.querySelectorAll('[data-order-card]').length;
          if (newCount > this.previousCount && this.soundEnabled) {
            this.playSound();
          }
          this.previousCount = newCount;
        }
      });
    },

    setFilter(f) {
      this.filter = f;
      sessionStorage.setItem('gestor_filter', f);
      htmx.trigger('#order-grid', 'refresh');
    },

    playSound() {
      var audio = new Audio('/static/storefront/sounds/new-order.mp3');
      audio.volume = 0.5;
      audio.play().catch(function() {});
    },

    toggleFullscreen() {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen();
      } else {
        document.exitFullscreen();
      }
    }
  }
}
```

### Step 8: Testes (`tests/test_f8_gestor_pedidos.py`)

```python
# Setup: Channel + Order factory

class TestGestorAccess(TestCase):
    def test_requires_staff(self): # → redirect to admin login
    def test_staff_can_access(self): # → 200

class TestGestorList(TestCase):
    def test_shows_new_orders(self): # orders com status=new aparecem
    def test_filters_by_status(self): # ?filter=processing filtra
    def test_multichannel_badges(self): # web/whatsapp/pos badges corretos
    def test_timer_display(self): # elapsed seconds renderizado

class TestGestorActions(TestCase):
    def test_confirm_order(self): # POST confirm → status=confirmed
    def test_reject_requires_reason(self): # POST reject sem motivo → 422
    def test_reject_with_reason(self): # POST reject → cancelled + reason in data
    def test_advance_confirmed_to_processing(self): # POST advance
    def test_advance_processing_to_ready(self):
    def test_internal_notes_saved(self): # POST notes → data["internal_notes"]

class TestGestorDetail(TestCase):
    def test_detail_shows_items(self): # items do pedido renderizados
    def test_detail_shows_availability(self): # badges de estoque
```

---

## Padrões a seguir (referência para a sessão)

| Aspecto | Padrão | Arquivo referência |
|---------|--------|--------------------|
| Auth staff | `request.user.is_staff` check manual | `shop/views/production.py:24` |
| Order transitions | `order.transition_status(status, actor)` | `ordering/models/order.py:206` |
| Order events | `order.emit_event(type, actor, payload)` | `ordering/models/order.py:228` |
| Stock check | `StockBackend().check_availability(sku, qty)` → `AvailabilityResult` | `shopman/backends/stock.py:36` |
| WorkOrder check | `WorkOrder.objects.filter(output_ref=sku, status__in=["planned", "started"])` | `crafting/models/work_order.py` |
| Recipe check | `Recipe.objects.filter(output_ref=sku, is_active=True)` | `crafting/models/recipe.py` |
| Release holds | `release_holds_for_order(order)` | `ordering/holds.py` |
| Directive creation | `Directive.objects.create(topic=..., payload=...)` | `shopman/lifecycle.py:38` |
| HTMX partial swap | `hx-get`, `hx-target`, `hx-swap="innerHTML"` | `tracking.html`, `payment.html` |
| Alpine state | `x-data="componentName()"` com function no `<script>` | `payment.html`, `product_detail.html` |
| Timer Alpine | Countdown com `setInterval`, cores por threshold | `order_status.html` (confirmTimer) |
| Bottom sheet | Inline Alpine com fixed overlay + swipe-dismiss | `tracking.html` (cancel modal) |
| Status labels/colors | Dicts `STATUS_LABELS`, `STATUS_COLORS` | `shopman/web/views/tracking.py:18` |
| `data` JSONField | Extensão via `order.data["key"]` — consultar `docs/reference/data-schemas.md` | `CLAUDE.md` |

## O que NÃO fazer no F8

- **NÃO criar modelos KDSTicket/KDSInstance** — isso é F9
- **NÃO alterar o Core** — tudo no App layer
- **NÃO criar migrations** — usar `order.data` JSONField para internal_notes, rejected_by
- **NÃO inventar features** — implementar exatamente o plano
- **NÃO fazer requests ao Core desnecessários** — stock check é caro, fazer lazy (só no detail expand)

## Verificação

```bash
source .venv/bin/activate
make test-framework  # deve passar TODOS os 1156+ testes existentes + novos F8
```

Testar manualmente:
1. `make seed` → popular banco
2. `make run` → acessar `/pedidos/` como staff
3. Verificar: cards aparecem, filtros funcionam, confirm/reject transiciona status, timer conta, som toca
