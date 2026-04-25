# WP-AV-13 — Fermata UI (Estado de Espera + Countdown)

**Status:** draft, executável por sessão paralela.

**Origem:** WP diferido do [AVAILABILITY-PLAN](AVAILABILITY-PLAN.md#wp-av-13--fermata-ui-countdown--estado-aguardando-produção). Esta é a expansão completa para execução standalone.

**Pré-requisitos no main (todos concluídos)**:
- WP-AV-11 — adapter cria hold com `expires_at=None` para demand_ok/planned ([adapters/stock.py](../../shopman/shop/adapters/stock.py)).
- WP-AV-12 — `on_holds_materialized` dispara `notify(event="stock.arrived", ...)` via registry ([_stock_receivers.py](../../shopman/shop/handlers/_stock_receivers.py)).

**Independência do WP-AV-10 (SSE push)**: este plano **não** depende do SSE estar pronto. A UI funciona com refresh via `cartUpdated` event + nota ativa por canal (WhatsApp/SMS/email já entrega o ping). SSE é enhancement futuro pra atualização in-page real-time — quando WP-AV-10 fechar, a UI deste plano automaticamente herda o push (basta o `cartUpdated` ser disparado pelo SSE handler).

---

## 1. Resumo executivo

Quando o cliente adiciona um produto **sem estoque pronto** mas com política `demand_ok` ou `planned_ok` (linha de produção planejada / "encomendo agora, fica feito depois"), o sistema cria um **hold indefinido** (fermata, WP-AV-11). A UI hoje **não comunica esse estado**: a linha do carrinho parece igual a uma linha normal, sem indicação de que o cliente está numa fila de produção, sem prazo, sem countdown quando o produto chegar.

Este plano fecha a UX:

1. **Backfill da projeção** (WP-AV-11 ficou parcial — só o adapter mudou, a flag `is_waiting_production` nunca foi propagada).
2. **Badge "Aguardando produção"** na linha do cart (drawer e page) enquanto o hold é fermata.
3. **Transição visual + countdown** quando o hold materializa: "Chegou! Confirme até HH:MM" com timer Alpine.
4. **Toast no `cartUpdated`** quando alguma linha sai de fermata pra "chegou".
5. **Vocabulário canônico** anexado ao AVAILABILITY-PLAN §2.

Honra o princípio de [feedback_transparent_timeouts](../../.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/feedback_transparent_timeouts.md): TTL visível na UI + notificação ativa (que já funciona via WP-AV-12) + cancelamento amigável.

---

## 2. Modelo de estado da fermata

Cada linha do cart pode estar em um de **quatro estados** (novo nesta rodada):

| Estado | Condição (em hold) | Copy / badge | CTA |
|---|---|---|---|
| **Disponível** | `quant != None` AND `quant.target_date == None` AND `quant._quantity > 0` | _(sem badge — default)_ | Stepper normal |
| **Aguardando produção** (fermata pré-materialização) | `quant == None` OR (`quant.target_date != None` AND `expires_at == None`) | Badge `Aguardando produção`, secondary `Avisamos quando chegar.` | Stepper somente decrementa / remove |
| **Chegou! Confirme** (fermata pós-materialização) | `quant != None` AND `quant.target_date == None` AND `expires_at != None` (post-materialize TTL) | Badge `Chegou! Confirme até <HH:MM>`, countdown Alpine | CTA destacada "Ir para checkout" |
| **Indisponível real** (cobertura existente — NÃO fermata) | shortage > 0 conforme cálculo do cart | `Indisponível` ou `Apenas N disponíveis` | "Aceitar N" / "Remover" |

A diferença essencial entre **"Chegou! Confirme"** e **"Indisponível"**: o primeiro é um countdown urgente; o segundo é um shortage informativo. Não confundir.

---

## 3. Backfill: propagar `is_waiting_production` na projeção

### 3.1 Onde calcular

Em [`CartService.get_cart`](../../shopman/shop/web/cart.py) (depois do bloco que computa `own_holds_by_sku`), inspecionar **os holds** desta sessão por SKU para classificar a linha.

Concretamente, para cada `item` do cart:

```python
# Após o bloco que computa max_orderable / shortage existente:
fermata_state = _classify_fermata_for_session_sku(session_key, item['sku'])
item['is_waiting_production'] = fermata_state['is_waiting']
item['is_arrived_pending_confirmation'] = fermata_state['is_arrived']
item['fermata_deadline_iso'] = fermata_state.get('deadline_iso')  # str ISO ou None
```

### 3.2 Helper `_classify_fermata_for_session_sku`

Lê os Holds ativos da sessão para o SKU. Retorna:

```python
{
    "is_waiting": bool,   # True se algum hold ainda é fermata pré-materialização
    "is_arrived": bool,   # True se TODOS os holds já materializaram (passaram a ter expires_at no futuro próximo)
    "deadline_iso": str | None,  # menor expires_at entre os holds já materializados
}
```

**Regra de classificação** (por hold):
- `expires_at IS NULL` AND (quant IS NULL OR quant.target_date IS NOT NULL) → fermata pré-materialização ("waiting").
- `expires_at IS NOT NULL` AND quant IS NOT NULL AND quant.target_date IS NULL AND `expires_at > now + 1 hour` (heurística: TTL "longo" = pós-materialização, ~60min default) → "arrived".
- Outros casos (TTL curto de 30min, hold normal) → não é fermata.

**Edge case**: se a linha tem múltiplos holds (split via `_reserve_across_quants`), `is_waiting` é OR de todos; `is_arrived` é AND de todos; `deadline_iso` é o min dos `expires_at` "arrived". 

### 3.3 Adicionar fields ao `CartItemProjection`

[`shopman/shop/projections/cart.py`](../../shopman/shop/projections/cart.py):

```python
@dataclass(frozen=True)
class CartItemProjection:
    ...
    is_waiting_production: bool = False
    is_arrived_pending_confirmation: bool = False
    fermata_deadline_iso: str | None = None  # ISO 8601 UTC, e.g. "2026-04-18T15:30:00Z"
```

E em `_build_item`, copiar do raw dict.

---

## 4. UI — Cart drawer e Cart page

### 4.1 Badge "Aguardando produção"

Acima do nome ou do preço da linha, quando `is_waiting_production`:

```html
{% if item.is_waiting_production %}
<div class="inline-flex items-center gap-1.5 rounded-full bg-info/10 px-2 py-0.5 text-xs font-medium text-info dark:bg-info-dark/10 dark:text-info-dark">
  <span class="material-symbols-rounded text-sm" aria-hidden="true">schedule</span>
  Aguardando produção
</div>
<p class="text-xs text-on-surface/70 dark:text-on-surface-dark/70 mt-0.5">
  Avisamos pelo {{ customer.notification_channel_label|default:"seu canal preferido" }} assim que chegar.
</p>
{% endif %}
```

Se a sessão é anônima (sem `customer` ainda), exibir copy genérico: "Avisamos quando chegar — verifique sua sessão depois".

### 4.2 Badge "Chegou! Confirme"

Quando `is_arrived_pending_confirmation`:

```html
{% if item.is_arrived_pending_confirmation %}
<div x-data="fermataCountdown('{{ item.fermata_deadline_iso }}')"
     class="rounded-radius border border-success/40 bg-success/5 p-3 dark:border-success-dark/40 dark:bg-success-dark/5"
     role="status">
  <div class="flex items-center gap-2">
    <span class="material-symbols-rounded text-success" aria-hidden="true">celebration</span>
    <p class="text-sm font-semibold text-on-surface-strong dark:text-on-surface-dark-strong">
      Chegou! Confirme até <span x-text="deadlineLabel"></span>
    </p>
  </div>
  <p class="mt-1 text-xs text-on-surface dark:text-on-surface-dark tabular-nums" aria-live="polite">
    Tempo restante: <span x-text="countdownLabel"></span>
  </p>
</div>
{% endif %}
```

### 4.3 Componente Alpine `fermataCountdown`

Em [base.html](../../shopman/shop/templates/storefront/base.html) ou em arquivo separado carregado:

```javascript
window.fermataCountdown = function(deadlineIso) {
  return {
    deadlineLabel: '',
    countdownLabel: '',
    init() {
      const deadline = new Date(deadlineIso);
      const fmt = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' });
      this.deadlineLabel = fmt.format(deadline);
      this.tick(deadline);
      this._timer = setInterval(() => this.tick(deadline), 1000);
    },
    tick(deadline) {
      const ms = deadline - new Date();
      if (ms <= 0) {
        this.countdownLabel = 'expirado';
        clearInterval(this._timer);
        // Trigger reload — server already released the hold; cart refreshes.
        htmx.trigger(document.body, 'cartUpdated');
        return;
      }
      const totalSec = Math.floor(ms / 1000);
      const min = Math.floor(totalSec / 60);
      const sec = totalSec % 60;
      this.countdownLabel = `${min}m ${String(sec).padStart(2, '0')}s`;
    },
    destroy() { if (this._timer) clearInterval(this._timer); },
  };
};
```

### 4.4 Toast "produto chegou"

Quando o cart re-renderiza e detecta uma linha que **virou** `is_arrived_pending_confirmation` (não estava antes), disparar toast:

```javascript
// Hook no event cartUpdated do cart drawer/page Alpine
$watch('cart.items', (items, prev) => {
  for (const item of items) {
    const prevItem = prev?.find(p => p.line_id === item.line_id);
    if (item.is_arrived_pending_confirmation && !prevItem?.is_arrived_pending_confirmation) {
      window.dispatchEvent(new CustomEvent('notify', {
        detail: { variant: 'success', message: item.name + ' chegou! Confirme antes de ' + item.fermata_deadline_label },
      }));
    }
  }
});
```

(detalhe: `fermata_deadline_label` precisa ser pré-formatado server-side em `CartItemProjection` para `Intl.DateTimeFormat` não rodar duas vezes — adicionar campo `fermata_deadline_display` na projeção.)

---

## 5. CTA "Ir para checkout" destacada

Quando `cart.has_arrived_items` é True (algum item é "chegou! confirme"), o botão de checkout do cart page/drawer ganha destaque visual + copy de urgência:

```html
{% if cart.has_arrived_items %}
<a href="{% url 'storefront:checkout' %}"
   class="btn-primary w-full mt-3 animate-pulse">
  <span class="material-symbols-rounded" aria-hidden="true">priority_high</span>
  Confirmar agora — produto pronto
</a>
{% else %}
<a href="{% url 'storefront:checkout' %}" class="btn-primary w-full mt-3">
  Finalizar pedido
</a>
{% endif %}
```

Adicionar `has_arrived_items: bool` ao `CartProjection` (computado no builder).

---

## 6. Vocabulário canônico — anexar ao AVAILABILITY-PLAN §2

Atualizar [AVAILABILITY-PLAN.md §2](AVAILABILITY-PLAN.md#2-vocabulário-canônico) com os dois estados novos do cart:

| Estado da linha do cart | Copy canônico |
|---|---|
| **Aguardando produção** (fermata pré) | Badge `Aguardando produção` + secondary `Avisamos quando chegar.` |
| **Chegou! Confirme** (fermata pós) | Badge `Chegou! Confirme até HH:MM` + countdown |

E na lista de proibidos: nenhum copy informal tipo "Tá vindo!" ou "Quase pronto!" — só os dois acima.

---

## 7. Refresh strategy

A UI precisa saber quando uma linha mudou de estado (sem reload manual). Três caminhos disponíveis:

### 7.1 Via `cartUpdated` event existente

Cada surface do cart (drawer + page) já escuta `cartUpdated` e refetch via HTMX. Quando o servidor processa qualquer ação do cart (set_qty, etc), um GET subsequente devolve o estado novo da linha — incluindo o flag de fermata recém-atualizado.

**Quando funciona**: usuário interage com o cart (set qty, abre drawer). Cobre o caso do "cliente clicou ir pro carrinho depois de receber o WhatsApp 'chegou!'".

**Quando NÃO funciona**: usuário tem o cart aberto e fica olhando — não recebe a transição de "Aguardando" → "Chegou!" sem interação.

### 7.2 Polling leve quando há fermata aberta

Se `cart.has_waiting_items`, plugar um poll a cada 30s no cart drawer/page:

```html
{% if cart.has_waiting_items %}
<div hx-get="{% url 'storefront:cart_drawer_content' %}"
     hx-trigger="every 30s"
     hx-target="#cart-drawer-body"
     hx-swap="innerHTML"></div>
{% endif %}
```

Polling **só** quando há fermata ativa. Sem fermata, zero polling.

### 7.3 Via SSE (futuro WP-AV-10)

Quando WP-AV-10 estiver pronto, evento `stock-update` para o SKU em fermata da sessão dispara refresh do cart automaticamente. Plugar como upgrade — não é pré-requisito deste plano.

**Recomendação**: implementar §7.1 + §7.2 nesta rodada. SSE entra como melhoria depois.

---

## 8. Edge cases

### 8.1 Cliente abre cart depois do TTL expirar

Hold materializou às 14:00, expira às 15:00. Cliente abre cart às 15:30:
- `Hold` já está expirado, libertou estoque.
- `_classify_fermata_for_session_sku` vê 0 holds ativos pra esse SKU.
- Linha do cart aparece como **Indisponível** (vocabulário existente).
- Operacionalmente: `availability.reconcile()` na próxima ação rejeita; UI mostra modal de erro com "Indisponível".

Sem mudanças necessárias — sistema atual lida.

### 8.2 Materialização parcial (split holds)

Cliente pediu 5 unidades, todas em fermata. Stockman materializou só 3:
- 3 holds ganharam `expires_at`, 2 ainda fermata.
- `_classify_fermata_for_session_sku`:
  - `is_waiting = True` (2 ainda esperando)
  - `is_arrived = False` (não TODOS materializaram)
- UI mostra **"Aguardando produção"** ainda (não "Chegou!"). Conservador — só vira "Chegou!" quando 100% materializou.

Alternativa mais granular: mostrar progresso "3 de 5 prontos". Mas é mais complexo de UX. Decisão: começar simples (binário), evoluir se demanda surgir.

### 8.3 Múltiplas linhas em fermata, expiram em horários diferentes

Cada linha tem seu próprio countdown Alpine. CTA "Confirmar agora" usa o `min` dos deadlines. Display: "Confirme antes de HH:MM" usa o mais próximo.

### 8.4 Cliente anônimo (sem customer associado)

Não recebe notify do WP-AV-12 (sem canal de notificação). Mas a UI ainda funciona: enquanto a aba estiver aberta, polling §7.2 detecta a transição.

Copy ajustado: "Mantenha esta janela aberta para receber a confirmação de chegada." (Aplicável quando `customer is None`.)

---

## 9. Trabalho desmembrado (sub-WPs)

### WP-FERMATA-UI-01 — Backfill da projeção

- Implementar `_classify_fermata_for_session_sku` em `shopman/shop/services/availability.py` (ou módulo apartado se ficar grande).
- Adicionar 3 fields ao `CartItemProjection`: `is_waiting_production`, `is_arrived_pending_confirmation`, `fermata_deadline_iso`, `fermata_deadline_display`.
- Adicionar 2 fields ao `CartProjection`: `has_waiting_items`, `has_arrived_items` (booleans agregados).
- Atualizar `CartService.get_cart` e `_build_item` para popular.
- Testes em `test_projections_cart.py`:
  - Hold com `expires_at=None` → linha aparece como `is_waiting_production=True`.
  - Hold pós-materialização (TTL longo, quant sem target_date) → `is_arrived_pending_confirmation=True`.
  - Hold normal (TTL curto, quant ready) → ambos False.

### WP-FERMATA-UI-02 — Badge "Aguardando produção"

- Adicionar bloco `{% if item.is_waiting_production %}` em [_cart_page_content.html](../../shopman/shop/templates/storefront/partials/_cart_page_content.html) e [cart_drawer.html](../../shopman/shop/templates/storefront/partials/cart_drawer.html).
- Copy: badge `Aguardando produção` + secondary "Avisamos quando chegar."
- Stepper desabilita o `+` (cliente não pode aumentar produto que ainda não foi feito).

### WP-FERMATA-UI-03 — Badge "Chegou!" + countdown

- Componente Alpine `fermataCountdown` em arquivo dedicado (`shopman/shop/static/storefront/js/fermata.js`) ou inline em base.
- Renderizar quando `is_arrived_pending_confirmation`.
- Tick a cada 1s até `expires_at`; ao expirar, dispara `cartUpdated` pra refresh do cart.
- Acessibilidade: `aria-live="polite"` no countdown.

### WP-FERMATA-UI-04 — CTA destacada no checkout

- `has_arrived_items` agregado no `CartProjection`.
- Trocar visual do botão checkout quando True.

### WP-FERMATA-UI-05 — Toast na transição

- Hook Alpine no cart watch das linhas detecta transição.
- Dispatch `notify` event.

### WP-FERMATA-UI-06 — Polling condicional

- Adicionar `hx-trigger="every 30s"` no cart drawer/page **só quando** `has_waiting_items`.

### WP-FERMATA-UI-07 — Vocabulário no plano-mãe

- Atualizar [AVAILABILITY-PLAN.md §2](AVAILABILITY-PLAN.md#2-vocabulário-canônico) com os dois novos estados.

### WP-FERMATA-UI-08 — Tests

- Projection: cobertura dos cenários §8.
- Template: render contém badge correto pra cada estado.
- E2E manual: criar Hold fermata, abrir cart, ver badge; simular materialização, ver transição + countdown.

---

## 10. Critério de saída

1. Cliente adiciona um produto `demand_ok` ao cart → linha mostra badge "Aguardando produção" + secondary.
2. Stepper `+` da linha em fermata está disabled.
3. Simular materialização (`StockPlanning.realize()`) → cart re-renderiza (via cartUpdated trigger ou polling 30s) → badge muda pra "Chegou! Confirme até HH:MM".
4. Countdown Alpine atualiza segundo a segundo.
5. Botão de checkout muda pro CTA "Confirmar agora — produto pronto".
6. Toast "produto chegou" aparece no momento da transição.
7. Quando countdown chega a zero, cart refresha e linha vira "Indisponível".
8. Suítes: framework + offerman + stockman verdes, com novos testes do WP-FERMATA-UI-01.

---

## 11. Perguntas abertas (Pablo)

1. **Agregação granular vs binária** (cf §8.2): mostrar "3 de 5 prontos" ou só "Chegou!" quando 100%? Default proposto: binário (simples). Confirma?
2. **CTA destacada usar `animate-pulse`** ou algo mais sutil? Hoje proposto pulsar; pode soar agressivo. Alternativa: só mudar copy + ícone.
3. **Polling de 30s** é razoável? Pode subir pra 60s pra economizar; subir custa: latência maior na percepção da chegada. Pra Nelson Boulangerie (poucos clientes simultâneos), 30s parece ok.

---

## 12. Pre-flight para o agente cold-start

Antes de tocar código:

1. Ler [AVAILABILITY-PLAN.md](AVAILABILITY-PLAN.md) §8 (fermata) e §9 (timeouts transparentes).
2. Ler memória [feedback_transparent_timeouts.md](../../.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/feedback_transparent_timeouts.md).
3. Ler:
   - [shopman/shop/web/cart.py::CartService.get_cart](../../shopman/shop/web/cart.py) — onde encaixar a classificação fermata.
   - [shopman/shop/projections/cart.py](../../shopman/shop/projections/cart.py) — `CartItemProjection` + `_build_item`.
   - [shopman/shop/adapters/stock.py::create_hold](../../shopman/shop/adapters/stock.py) — entender quando `expires_at=None` é setado (WP-AV-11).
   - [shopman/shop/handlers/_stock_receivers.py::on_holds_materialized](../../shopman/shop/handlers/_stock_receivers.py) — entender o fluxo de materialização e o notify de WP-AV-12.
   - [packages/stockman/shopman/stockman/services/planning.py::realize](../../packages/stockman/shopman/stockman/services/planning.py) — quando o `expires_at` ganha valor pós-materialização.
4. Confirmar com Pablo as perguntas §11 antes de codar.

---

## 13. Memória ao concluir

Gravar:

- `project_fermata_ui.md` — "Cart drawer/page mostram estado de fermata (Aguardando produção / Chegou! + countdown). Polling de 30s quando há fermata aberta. Toast de transição."
- Atualizar `project_availability_plan_status.md`: WP-AV-13 deixa de "diferido" e vira "concluído".

---

## 14. Não-objetivos (escopo fora deste plano)

- Implementar SSE push real-time (é WP-AV-10).
- Notificações WhatsApp/SMS/email — já em produção via WP-AV-12.
- Alterar mecânica de fermata (criação do hold, materialização) — base instalada via WP-AV-11.
- "Me avise quando voltar" sem hold (subscription avulsa) — feature separada [project_notify_me_pending](../../.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/project_notify_me_pending.md).
