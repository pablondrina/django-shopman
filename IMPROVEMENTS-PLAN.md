# IMPROVEMENTS-PLAN.md — Correções, Ajustes e Melhorias

> Resultado da análise crítica do Shopman App (março 2026).
> Cada WP é auto-contido, dimensionado para uma sessão do Claude Code.
> Prioridade: bugs → design → documentação → próximos passos.

---

## Contexto

A análise cobriu 74 arquivos em channels/, 7 em shop/, 50 de testes, toda a documentação e os 8 core apps. O App é sólido — arquitetura Protocol/Adapter bem executada, storefront funcional end-to-end, API REST implementada, dashboard operacional no admin. Mas há 3 bugs, inconsistências de design, planos desatualizados, e capacidades do Core subutilizadas.

**Referência**: Esta análise está documentada em detalhes na memória do projeto.

---

## WP-1: Bugfixes Críticos

**Objetivo**: Corrigir 3 bugs que afetam funcionalidade real.

### Bug 1: EmployeeDiscountModifier não persiste desconto

**Arquivo**: `shop/modifiers.py:271-284`
**Causa**: Modifica items in-place mas não chama `session.update_items(items)`.
Como `session.items` retorna `copy.deepcopy()`, as mudanças são descartadas.
**Comparação**: `D1DiscountModifier` (linha 84-85) e `DiscountModifier` (linha 216) fazem corretamente.

**Fix**: Adicionar `session.update_items(items)` ao final do `apply()`.

### Bug 2: HappyHourModifier não persiste desconto

**Arquivo**: `shop/modifiers.py:308-326`
**Causa**: Mesmo problema do Employee. Items modificados mas nunca salvos.

**Fix**: Adicionar `session.update_items(items)` ao final do `apply()`.

### Bug 3: `_on_cancelled()` órfão — holds não liberados ao cancelar

**Arquivo**: `channels/hooks.py:96-129`
**Causa**: Função existe (libera holds + notifica) mas não é chamada por ninguém.
`on_order_lifecycle()` dispara pipeline por status, mas não trata CANCELLED especificamente.

**Fix**: Em `on_order_lifecycle()`, quando `event_type == "status_changed"` e novo
status == `CANCELLED`, chamar `_on_cancelled(order, actor)`.

### Testes obrigatórios

- `test_employee_discount_persists_on_session` — verifica que items refletem desconto após apply
- `test_happy_hour_discount_persists_on_session` — idem
- `test_cancel_order_releases_holds` — verifica que holds são liberados ao cancelar
- `test_cancel_order_sends_notification` — verifica notificação de cancelamento

### Arquivos

- `shop/modifiers.py` — fix Employee + HappyHour
- `channels/hooks.py` — conectar _on_cancelled
- `tests/test_promotions.py` — testes Employee/HappyHour
- `tests/test_notification_handlers.py` ou novo arquivo — teste cancelamento

---

## WP-2: Limpeza de Design

**Objetivo**: Eliminar inconsistências e violações DRY.

### 2.1 Consolidar StockCheckValidator

**Problema**: Classe duplicada em `channels/handlers/stock.py:344-373` e inline em
`channels/setup.py:247-273`.

**Fix**: Manter definição apenas em `handlers/stock.py`. Em `setup.py`, importar.

### 2.2 Remover aliases backward-compat

**Problema**: `shop/modifiers.py:256-258` define `PromotionModifier = DiscountModifier`
e `CouponModifier = DiscountModifier`. Viola convenção "zero backward-compat aliases".

**Fix**: Remover aliases. Atualizar testes que usem os nomes antigos.

### 2.3 Padronizar registro de validators

**Problema**: Modifiers são importados de seus módulos e registrados em `setup.py`.
Validators são definidos inline em `setup.py` ou referenciados por string nos presets.

**Fix**: Mover todos os validators para `channels/validators.py` (ou manter em
`handlers/stock.py` para o stock validator). Em `setup.py`, importar e registrar
com o mesmo padrão dos modifiers.

### Testes

- `make test` passa sem alteração de comportamento
- `make lint` limpo

### Arquivos

- `channels/setup.py` — limpar inline, importar
- `channels/handlers/stock.py` — manter StockCheckValidator
- `shop/modifiers.py` — remover aliases
- `tests/test_promotions.py` — atualizar imports se necessário

---

## WP-3: D-1 — Restrição de Canal e Posição de Estoque

**Objetivo**: D-1 (ontem do dia anterior) é um produto de balcão/assistido, não de
e-commerce. Restringir disponibilidade por canal e posição de estoque.

### Contexto de negócio

D-1 é o pão de ontem na vitrine com 50% de desconto. O cliente vê fisicamente
no balcão, ou pede via WhatsApp com vendedor assistindo. Jamais estará disponível
para compra remota direta (storefront self-service). A posição de estoque é
específica (ex: "vitrine" ou "ontem") e pode não ser acessível diretamente pelo
canal remoto.

### O que o Core já oferece

- `Position.is_saleable` — flag que indica se estoque nessa posição pode ser vendido
- `Quant.position` — cada quant está em uma posição específica
- `ChannelConfig` — configuração por canal com rules
- `StockingBackend.check_availability()` — já filtra por `is_saleable`

### Abordagem

1. **Posição dedicada para D-1**: Criar Position `ref="ontem"` com `is_saleable=True`
   (acessível a canais que permitem).

2. **Filtro de disponibilidade por canal**:
   - `ChannelConfig.Stock` ganha campo opcional `allowed_positions: list[str] | None`
   - `None` = todas as posições saleable (default, backward-compat)
   - Lista explícita = só essas posições contam na disponibilidade
   - Preset `pos()`: `allowed_positions=None` (todas, incluindo ontem)
   - Preset `remote()`: `allowed_positions=["estoque", "producao"]` (exclui ontem)
   - Canal WhatsApp assistido: configurável para incluir ou não ontem

3. **StockingBackend**: Respeitar `allowed_positions` ao chamar `check_availability()`,
   filtrando Quants por posição.

4. **D1DiscountModifier**: Já funciona — só aplica se `is_d1=True` no item.
   Como o storefront remoto não verá stock D-1 (posição filtrada), o desconto
   simplesmente não se aplica. Zero mudança no modifier.

5. **Seed**: Criar Position "ontem", mover quants D-1 para lá.

### Tarefas

1. `channels/config.py`: Adicionar `allowed_positions: list[str] | None = None`
   ao `StockConfig` dataclass.

2. `channels/presets.py`: Atualizar `remote()` para excluir posição de ontem.
   `pos()` mantém `None` (acesso total).

3. `channels/backends/stock.py`: `StockingBackend.check_availability()` filtra
   Quants por `allowed_positions` (se não None). Idem para `get_alternatives()`.

4. `shop/management/commands/seed.py`: Criar Position "ontem", mover quants
   de produtos D-1 para essa posição.

5. Testes:
   - `test_remote_channel_excludes_d1_position`
   - `test_pos_channel_sees_d1_position`
   - `test_d1_modifier_only_applies_when_d1_visible`

### Arquivos

- `channels/config.py` — StockConfig.allowed_positions
- `channels/presets.py` — remote() com exclusão
- `channels/backends/stock.py` — filtro por posição
- `shop/management/commands/seed.py` — Position "ontem"
- `tests/test_inventory_handlers.py` — testes de filtragem

---

## WP-4: Product.meta no Core + DayClosing Model + Admin

**Objetivo**: Criar a infraestrutura (campo extensível no Core + modelo de fechamento
no App) que será usada pelas telas de operação em WP-5 e WP-6.

### Product.meta — Ponto de extensão genérico

O Core não tem ponto de extensão genérico no Product. O App precisa de atributos
extras (ex: `allows_next_day_sale`) sem poluir o Core com conceitos específicos.

**Solução**: `meta = JSONField(default=dict, blank=True)` no Product.
Mesmo padrão já usado no Core: `Customer.metadata`, `Session.data`, `Order.data`.

**Uso no App**: `product.meta["allows_next_day_sale"]` — boolean. Indica se o
produto pode ser vendido no dia seguinte com desconto D-1.

- `shelf_life_days = 0`: qualidade/planejamento ("melhor consumir hoje")
- `meta["allows_next_day_sale"] = True`: política comercial ("aceitável amanhã a 50%")
- São conceitos ortogonais. Nem todo shelf_life_days=0 é D-1 eligible.

### DayClosing — Registro de fechamento

Novo model no App para registrar fechamento do dia (auditoria).

### Tarefas

1. **Core: Product.meta**
   - `shopman-core/offering/shopman/offering/models/product.py`: adicionar campo
   - Nova migração no offering

2. **App: DayClosing model**
   - `shop/models.py`: DayClosing (date unique, closed_by FK User, closed_at, notes, data JSON)
   - `data` = lista [{sku, qty_remaining, qty_d1, qty_loss}]
   - Nova migração no shop

3. **App: ProductAdmin — allows_next_day_sale como checkbox**
   - `shop/admin.py`: custom form no ProductAdmin que renderiza
     `meta["allows_next_day_sale"]` como BooleanField checkbox
   - Ao salvar: escreve de volta no product.meta

4. **App: DayClosingAdmin — read-only após criado**
   - `shop/admin.py`: registrar DayClosingAdmin
   - list_display: date, closed_by, closed_at
   - Campos read-only após save (has_change_permission=False ou readonly_fields)
   - Detalhe mostra data JSON formatado

5. **Seed**: Marcar 3-4 produtos como allows_next_day_sale=True (pão de forma, etc.)

6. **Testes**:
   - test_product_meta_default_empty_dict
   - test_product_meta_allows_next_day_sale_queryable
   - test_day_closing_one_per_day_constraint
   - test_day_closing_data_snapshot_format

### Arquivos

- `shopman-core/offering/shopman/offering/models/product.py` — meta field
- `shopman-core/offering/shopman/offering/migrations/` — nova migração
- `shop/models.py` — DayClosing
- `shop/admin.py` — ProductAdmin form + DayClosingAdmin
- `shop/migrations/` — DayClosing migration
- `shop/management/commands/seed.py` — meta nos produtos
- `tests/test_day_closing.py` — NOVO

---

## WP-5: Tela de Produção Rápida

**Objetivo**: Operador registra produção do dia via formulário rápido no admin.
Por baixo, cria WorkOrder + fecha + atualiza estoque.

**Pré-requisito**: WP-4 concluído (Product.meta existe).

### Contexto técnico

- WorkOrder no Crafting já existe: status OPEN→DONE, produced, recipe FK
- Integração Crafting→Stocking: ao fechar WO, move de estoque é criado
- Admin usa Unfold (django-unfold)

### Padrão de custom view no Unfold (já usado no projeto)

Custom pages no admin seguem este padrão (ver merge/admin.py no Core):
```python
class MyModelAdmin(ModelAdmin):
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("minha-view/",
                 self.admin_site.admin_view(self.minha_view),
                 name="app_model_minhaview"),
        ]
        return custom + urls

    def minha_view(self, request):
        context = {
            **self.admin_site.each_context(request),  # sidebar Unfold
            "title": "Minha View",
        }
        return TemplateResponse(request, "admin/app/template.html", context)
```

Template estende `admin/base.html` e usa componentes Unfold:
`{% component "unfold/components/card.html" %}`, `{% include "unfold/components/table.html" %}`.

### Interface

Tela admin: "Registro de Produção" (acessível via sidebar ou link no dashboard).

1. **Formulário rápido** (topo da página):
   - Selecionar Receita (dropdown: recipe.code — recipe.output_ref)
   - Quantidade produzida (number input)
   - Posição de destino (dropdown de Positions, default: estoque principal)
   - Botão "Registrar Produção"

2. **Ao salvar** (POST):
   - Criar WorkOrder(recipe=selecionada, quantity=informada, status=OPEN)
   - Fechar imediatamente: WO.status=DONE, WO.produced=quantity
   - Usar serviço do Crafting para fechar (se existir) ou manipular diretamente
   - Move no Stocking criado pela integração existente (ou criar manualmente)
   - Redirect com success message

3. **Lista do dia** (abaixo do formulário):
   - Tabela: WorkOrders de hoje (recipe.output_ref, quantity, produced, hora, status)
   - Ação: "Estornar" (void WO) para corrigir erros
   - Usar componente table do Unfold

### Permissões

- Grupo Django "Produção"
- Verificar `request.user.has_perm("crafting.add_workorder")` na view
- Link no sidebar só aparece se tem permissão

### Tarefas

1. **View**: `shop/views/production.py`
   - `ProductionView(View)` com GET (formulário + lista) e POST (criar + fechar WO)
   - `ProductionVoidView(View)` com POST (estornar WO)

2. **Template**: `shop/templates/admin/shop/production.html`
   - Extends `admin/base.html`
   - Formulário com componentes Unfold (card, form fields)
   - Tabela do dia com componente table do Unfold

3. **URL registration**: Registrar via `ShopAdmin.get_urls()` ou `AdminSite.get_urls()`
   - path: `admin/shop/production/`
   - name: `shop_production`

4. **Sidebar**: Adicionar link em settings.py UNFOLD["SIDEBAR"]
   - `{"title": "Produção", "icon": "manufacturing", "link": reverse_lazy("admin:shop_production"), "permission": lambda request: request.user.has_perm("crafting.add_workorder")}`

5. **Testes**:
   - test_production_page_requires_permission
   - test_production_creates_workorder_and_closes
   - test_production_updates_stock
   - test_production_void_reverts
   - test_production_lists_today_only

### Arquivos

- `shop/views/production.py` — NOVO
- `shop/templates/admin/shop/production.html` — NOVO
- `shop/admin.py` — registrar URL (get_urls)
- `project/settings.py` — sidebar link
- `tests/test_production_quick.py` — NOVO

### Leia PRIMEIRO

- `shop/dashboard.py` — padrão de dashboard_callback (contexto Unfold)
- `shop/templates/admin/index.html` — padrão de template Unfold (componentes)
- `shopman-core/crafting/shopman/crafting/models/` — Recipe, WorkOrder
- `shopman-core/crafting/shopman/crafting/services/execution.py` — close_work_order (se existir)
- `shopman-core/stocking/shopman/stocking/services/movements.py` — record_move
- `shopman-core/customers/shopman/customers/contrib/merge/admin.py` — padrão get_urls + custom view
- `project/settings.py` — UNFOLD config (SIDEBAR, TABS)

---

## WP-6: Fechamento do Dia + Cleanup D-1 + Dashboard Widget

**Objetivo**: Operador faz fechamento diário — informa não-vendidos, sistema move
para posição "ontem" (D-1) ou registra perda. Cleanup automático de D-1 vencido.
Dashboard mostra estoque D-1.

**Pré-requisitos**:
- WP-3 concluído: Position "ontem" existe, ChannelConfig.Stock.allowed_positions funciona
- WP-4 concluído: Product.meta existe, DayClosing model existe
- WP-5 concluído (recomendado): padrão de custom view já estabelecido

### Contexto de negócio

Ao final do expediente, operador informa quantidades não vendidas por SKU:
- Produtos com `product.meta["allows_next_day_sale"]=True` → move para posição "ontem"
- Produtos sem essa flag (perecíveis sem D-1) → registra como perda
- Não perecíveis (shelf_life_days > 0 ou None) → permanecem no estoque normal
- Sistema cria DayClosing record com snapshot completo (auditoria)

### Padrão de custom view (mesmo de WP-5)

Custom page no admin via `get_urls()` + `admin_site.admin_view()` + `TemplateResponse`.
Template estende `admin/base.html`, usa componentes Unfold.

### Interface — Tela de Fechamento

1. **Ao abrir** (GET):
   - Consultar Quants em posições de venda (`is_saleable=True`, exceto "ontem")
   - Agrupar por SKU: soma qty disponível
   - Para cada SKU: mostrar nome, qty atual, indicador D-1 elegível
   - Indicador visual:
     - Verde: `product.meta.get("allows_next_day_sale", False) == True` → vai para "ontem"
     - Vermelho: perecível sem D-1 (shelf_life_days == 0, allows_next_day_sale=False) → perda
     - Neutro: não perecível → permanece (nenhuma ação necessária, pode ocultar)
   - Campo editável: "Não vendidos" por SKU (default: qty restante)
   - Verificar se já existe DayClosing para hoje (se sim, mostrar read-only)
   - Alertar se há D-1 de ontem ainda na posição "ontem" (>1 dia)

2. **Ao confirmar** (POST):
   - Para cada SKU com qty "não vendidos" > 0:
     - **D-1 elegível**: 2 Moves — saída da posição atual + entrada na posição "ontem"
       - Move(sku, delta=-qty, position=origem, reason="fechamento:YYYY-MM-DD")
       - Move(sku, delta=+qty, position="ontem", reason="d1:YYYY-MM-DD")
     - **Perda**: 1 Move negativo
       - Move(sku, delta=-qty, position=origem, reason="perda:YYYY-MM-DD")
   - Criar DayClosing(date=hoje, closed_by=request.user, data=[snapshot])
   - Redirect com success message

### Management Command — cleanup_d1

- `shop/management/commands/cleanup_d1.py`
- Roda no início do expediente (cron diário)
- Busca Quants na posição "ontem" com moves mais antigos que 1 dia
- Move para perda: Move(sku, delta=-qty, position="ontem", reason="perda_d1_vencido:YYYY-MM-DD")
- Log: lista SKUs removidos e quantidades
- Idempotente: se qty já é 0, skip

### Dashboard Widget — Estoque D-1

- `shop/dashboard.py`: nova seção no dashboard_callback
- Widget "Estoque D-1": Quants na posição "ontem" com qty > 0
- Tabela: SKU, nome, qty, data de entrada (extraída do move mais recente)
- Link para tela de fechamento
- Se posição "ontem" não existe ou não tem estoque: ocultar seção

### Permissões

- Grupo Django "Caixa" ou "Gerência"
- Verificar `request.user.has_perm("shop.add_dayclosing")` na view
- Link no sidebar com permission lambda

### Tarefas

1. **View**: `shop/views/closing.py`
   - `DayClosingView(View)` com GET (lista SKUs) e POST (executar fechamento)

2. **Template**: `shop/templates/admin/shop/closing.html`
   - Extends `admin/base.html`
   - Tabela de SKUs com campos editáveis e indicadores coloridos
   - Alerta de D-1 vencido no topo (se houver)
   - Botão "Confirmar Fechamento"

3. **URL + Sidebar**: Mesmo padrão de WP-5
   - path: `admin/shop/closing/`
   - Sidebar: `{"title": "Fechamento", "icon": "point_of_sale", ...}`

4. **Command**: `shop/management/commands/cleanup_d1.py`
   - Busca Quants posição "ontem", moves >1 dia
   - Move para perda, log resultado

5. **Dashboard**: `shop/dashboard.py`
   - Adicionar seção "Estoque D-1" ao dashboard_callback
   - Consulta Quants posição "ontem" com qty > 0

6. **Testes**:
   - test_closing_page_requires_permission
   - test_closing_moves_eligible_to_ontem_position
   - test_closing_registers_loss_for_ineligible
   - test_closing_creates_day_closing_record
   - test_closing_blocks_duplicate_for_same_day
   - test_closing_shows_d1_vencido_alert
   - test_cleanup_d1_removes_old_stock
   - test_cleanup_d1_idempotent
   - test_dashboard_shows_d1_widget

### Arquivos

- `shop/views/closing.py` — NOVO
- `shop/templates/admin/shop/closing.html` — NOVO
- `shop/management/commands/cleanup_d1.py` — NOVO
- `shop/dashboard.py` — widget D-1
- `shop/admin.py` — registrar URL closing
- `project/settings.py` — sidebar link
- `tests/test_day_closing.py` — NOVO (ou expandir do WP-4)

### Leia PRIMEIRO

- `shop/views/production.py` — padrão de custom view (criado em WP-5)
- `shop/templates/admin/shop/production.html` — padrão de template (criado em WP-5)
- `shop/dashboard.py` — dashboard_callback existente
- `shop/models.py` — DayClosing model (criado em WP-4)
- `shopman-core/stocking/shopman/stocking/models/` — Quant, Move, Position
- `shopman-core/stocking/shopman/stocking/services/movements.py` — record_move
- `shopman-core/offering/shopman/offering/models/product.py` — Product.meta (criado em WP-4)

---

## WP-7: Atualizar Documentação (Planos vs Realidade)

**Objetivo**: Alinhar EVOLUTION-PLAN e PARITY-PLAN com o que já foi implementado.

### Itens já implementados (total ou parcialmente)

| Plano | WP | Status real | Evidência |
|-------|-----|-------------|-----------|
| EVOLUTION | WP-E1 (Disponibilidade) | **~90% implementado** | `catalog.py` mostra badges, alternativas, warnings; `cart.py` tem CartCheckView; templates existem |
| EVOLUTION | WP-E2 (Loyalty) | **~70% implementado** | `handlers/loyalty.py` existe; topic registrado; handler registrado em setup.py; falta UI na account |
| EVOLUTION | WP-E4 (Dashboard) | **~80% implementado** | `shop/dashboard.py` com 425 linhas: KPIs, charts, tables |
| EVOLUTION | WP-E5 (Notificações) | **~80% implementado** | EmailBackend + SMS backend; fallback chain phone-first (manychat→sms→email); on_processing notifica; 6 templates |
| EVOLUTION | WP-E6 (API REST) | **~70% implementado** | `api/catalog.py` e `api/tracking.py` implementados; falta account/history |
| PARITY | WP-P3 (Coupon UX) | **~80% implementado** | `ApplyCouponView` + `RemoveCouponView` implementados em cart.py |
| PARITY | WP-P4 (Fulfillment tracking) | **~70% implementado** | TrackingView com carrier links no web; API tracking implementado |

### Tarefas

1. **EVOLUTION-PLAN.md**: Atualizar status de cada WP. Marcar o que está feito.
   Reduzir tarefas pendentes ao que realmente falta.

2. **PARITY-PLAN.md**: Idem. WP-P3 e WP-P4 estão quase completos.

3. **docs/architecture.md**: Refletir handlers atuais (loyalty, returns adicionados).

4. **docs/reference/protocols.md**: Verificar se reflete todos os backends atuais.

5. **CLAUDE.md**: Atualizar contagem de testes e status do projeto.

### Arquivos

- `EVOLUTION-PLAN.md`
- `PARITY-PLAN.md`
- `docs/architecture.md`
- `docs/reference/protocols.md`
- `CLAUDE.md`

---

## WP-8: Testes para Gaps Identificados

**Objetivo**: Cobrir áreas sem testes que podem quebrar silenciosamente.

### Gaps prioritários

1. **EmployeeDiscountModifier** — zero testes dedicados (bugs 1-2 de WP-1)
2. **HappyHourModifier** — zero testes dedicados
3. **BusinessHoursValidator** — zero testes unitários
4. **MinimumOrderValidator** — zero testes unitários
5. **Dashboard queries** — parcial (test_dashboard.py existe mas é superficial)
6. **Cancellation flow** — holds release + notification não testado

### Tarefas

1. `tests/test_promotions.py` (ou novo arquivo): testes Employee + HappyHour
   - test_employee_discount_applies_to_staff
   - test_employee_discount_skips_non_staff
   - test_happy_hour_applies_in_window
   - test_happy_hour_skips_outside_window
   - test_happy_hour_skips_employee_items
   - test_both_modifiers_persist_changes (pós WP-1)

2. `tests/test_web_business_rules.py` (ou existente): validators
   - test_business_hours_rejects_outside_hours
   - test_business_hours_allows_within_hours
   - test_minimum_order_rejects_below_threshold
   - test_minimum_order_allows_above_threshold
   - test_minimum_order_only_applies_to_delivery

3. `tests/test_dashboard.py`: queries e formatação
   - test_dashboard_order_counts_by_status
   - test_dashboard_revenue_comparison
   - test_dashboard_handles_missing_apps

### Arquivos

- `tests/test_promotions.py`
- `tests/test_web_business_rules.py`
- `tests/test_dashboard.py`

---

## WP-9: Capacidades Core Subutilizadas — Quick Wins

**Objetivo**: Ativar capacidades do Core que estão prontas mas não expostas.

### 6.1 CostBackend adapter (Crafting → Offering)

O Core de Offering define `CostBackend` protocol para cálculo de margem.
O Crafting sabe o custo de produção (soma de RecipeItems).
Falta um adapter que conecte os dois.

**Fix**: `channels/backends/cost.py` com `CraftingCostBackend` que implementa
`get_cost(sku)` lendo receita + preço de insumos.
Registrar via `OFFERING["COST_BACKEND"]` no settings.

### 6.2 Batch traceability no admin

O Core de Stocking tem `Batch` (production_date, expiry_date, supplier).
O admin não expõe Batch de forma útil.

**Fix**: Registrar `BatchAdmin` com filtros por expiry_date e supplier.
Inline em `QuantAdmin` mostrando batch de cada quant.

### 6.3 RFM context em promoções (preparação)

O `CustomerBackend` já retorna `CustomerContext` com segmento RFM.
Promotions não usam para targeting. Não é para implementar agora,
mas preparar o campo: adicionar `customer_segments: list[str]` ao
modelo Promotion (JSON, padrão []).

### Tarefas

1. `channels/backends/cost.py` — CraftingCostBackend
2. `project/settings.py` — OFFERING["COST_BACKEND"] apontando para adapter
3. `shop/admin.py` — BatchAdmin + inline
4. `shop/models.py` — Promotion.customer_segments (preparação)
5. Testes para CostBackend adapter

### Arquivos

- `channels/backends/cost.py` — NOVO
- `project/settings.py`
- `shop/admin.py`
- `shop/models.py`

---

---

## Ordem de Execução

```
WP-1 (bugfixes)              ← URGENTE: 3 bugs
  │
WP-2 (limpeza design)        ← rápido, melhora manutenção
  │
WP-3 (D-1 canal/posição)     ← cria posição "ontem" + allowed_positions
  │
WP-4 (meta + DayClosing)    ← Product.meta no Core + modelo de fechamento
  │
WP-5 (produção rápida)      ← tela admin de registro de produção
  │
WP-6 (fechamento + cleanup) ← tela de fechamento + cleanup_d1 + dashboard D-1
  │
WP-7 (docs)                  ← alinha planos com realidade
  │
WP-8 (testes)                ← cobre gaps após WP-1 a WP-6
  │
WP-9 (quick wins Core)       ← ativa capacidades prontas
```

WP-1 primeiro (bugs). WP-2 e WP-3 podem ser paralelos. WP-4→WP-5→WP-6 sequenciais
(cada um depende do anterior). WP-7 após WP-6. WP-8 após WP-7. WP-9 por último.

---

## Critério de Aceite Global

1. `make test` — 0 failures
2. `make lint` — 0 warnings
3. Employee/HappyHour discounts persistem corretamente
4. Cancelamento de pedido libera holds
5. D-1 não aparece no storefront remoto self-service
6. Product.meta funcional com allows_next_day_sale no admin
7. Operador registra produção via tela rápida
8. Fechamento do dia move não-vendidos para "ontem" ou perda
9. Dashboard mostra estoque D-1
10. cleanup_d1 remove D-1 vencido automaticamente
11. Documentação reflete estado real
12. Testes cobrem modifiers, validators, cancelamento, operações

---

## Prompts de Execução

### WP-1 — Bugfixes Críticos
```
Execute WP-1 do IMPROVEMENTS-PLAN.md: Bugfixes Críticos.

3 bugs identificados na análise crítica do App:

Bug 1 — EmployeeDiscountModifier não persiste:
- shop/modifiers.py:271-284
- Modifica items in-place mas não chama session.update_items(items)
- session.items retorna copy.deepcopy() → mudanças são descartadas
- Comparar com D1DiscountModifier (linha 84-85) que faz corretamente

Bug 2 — HappyHourModifier não persiste:
- shop/modifiers.py:308-326
- Mesmo problema: items modificados mas nunca salvos

Bug 3 — _on_cancelled() órfão:
- channels/hooks.py:96-129
- Função existe (libera holds + notifica) mas nunca é chamada
- on_order_lifecycle() não trata CANCELLED especificamente

Leia PRIMEIRO:
- shop/modifiers.py (comparar D1Discount vs Employee vs HappyHour)
- channels/hooks.py (on_order_lifecycle + _on_cancelled)
- shopman-core/ordering/shopman/ordering/models/session.py:172-182 (items API com deepcopy)

Fixes:
1. Employee: adicionar session.update_items(items) ao final de apply()
   (precisa flag modified como D1Discount, ou chamar sempre)
2. HappyHour: idem
3. hooks.py: em on_order_lifecycle(), detectar status CANCELLED e chamar _on_cancelled()

Testes:
- test_employee_discount_persists_on_session
- test_happy_hour_discount_persists_on_session
- test_cancel_order_releases_holds
- test_cancel_order_sends_notification

make test + make lint ao final.
```

### WP-2 — Limpeza de Design
```
Execute WP-2 do IMPROVEMENTS-PLAN.md: Limpeza de Design.

3 inconsistências:

1. StockCheckValidator duplicado:
   - channels/handlers/stock.py:344-373 define StockCheckValidator
   - channels/setup.py:247-273 define classe inline quase idêntica
   - Fix: manter em handlers/stock.py, importar em setup.py

2. Aliases backward-compat:
   - shop/modifiers.py:256-258: PromotionModifier = DiscountModifier, CouponModifier = DiscountModifier
   - Viola convenção "zero backward-compat aliases"
   - Fix: remover. Atualizar testes que usem nomes antigos.

3. Registro inconsistente de validators vs modifiers:
   - Modifiers: importados de módulos, registrados em setup.py
   - Validators: definidos inline em setup.py
   - Fix: importar validators de seus módulos, registrar com mesmo padrão

Leia PRIMEIRO:
- channels/setup.py (toda a função de registro)
- channels/handlers/stock.py (StockCheckValidator)
- shop/modifiers.py (aliases no final)
- Grep por PromotionModifier e CouponModifier nos testes

make test + make lint ao final.
```

### WP-3 — D-1 Canal/Posição
```
Execute WP-3 do IMPROVEMENTS-PLAN.md: D-1 — Restrição de Canal e Posição de Estoque.

Regra de negócio: D-1 (produção do dia anterior, 50% off) é produto de balcão ou
venda assistida (WhatsApp com vendedor). NUNCA disponível no storefront remoto
self-service. A posição de estoque é específica ("ontem") e canais remotos
não devem enxergá-la.

O Core já oferece:
- Position.is_saleable — flag por posição
- Quant.position — cada quant em uma posição
- ChannelConfig — configuração por canal

Abordagem:
1. ChannelConfig.Stock ganha allowed_positions: list[str] | None
   - None = todas (default, backward-compat)
   - Lista = só essas posições contam na disponibilidade

2. Presets:
   - pos(): allowed_positions=None (todas, incluindo ontem)
   - remote(): allowed_positions exclui "ontem"

3. StockingBackend: check_availability() filtra Quants por allowed_positions

4. D1DiscountModifier: sem mudança (se D-1 não é visível, desconto não se aplica)

5. Seed: criar Position "ontem", mover quants D-1 para lá

Leia PRIMEIRO:
- channels/config.py (ChannelConfig, StockConfig)
- channels/presets.py (pos, remote, marketplace)
- channels/backends/stock.py (StockingBackend.check_availability)
- shopman-core/stocking/shopman/stocking/models/position.py (Position)
- shopman-core/stocking/shopman/stocking/models/quant.py (Quant)
- shop/modifiers.py (D1DiscountModifier — para entender fluxo)

Testes:
- test_remote_channel_excludes_d1_position
- test_pos_channel_sees_d1_position
- test_d1_modifier_noop_when_position_hidden

make test + make lint ao final.
```

### WP-4 — Product.meta + DayClosing Model + Admin
```
Execute WP-4 do IMPROVEMENTS-PLAN.md: Product.meta no Core + DayClosing Model + Admin.

Objetivo: Criar infraestrutura para as telas de operação (WP-5, WP-6).

PARTE 1 — Product.meta no Core:

O Core não tem campo extensível no Product. Outros models já usam esse padrão:
- Customer.metadata (shopman-core/customers)
- Session.data (shopman-core/ordering)
- Order.data (shopman-core/ordering)

Tarefa:
- shopman-core/offering/shopman/offering/models/product.py:
  Adicionar: meta = JSONField(default=dict, blank=True)
- Nova migração no offering

Leia PRIMEIRO:
- shopman-core/offering/shopman/offering/models/product.py (Product atual)
- shopman-core/customers/shopman/customers/models/customer.py (Customer.metadata)

PARTE 2 — DayClosing model no App:

Novo model para registrar fechamento diário (auditoria):
- shop/models.py: DayClosing
  - date = DateField(unique=True)  # um por dia
  - closed_by = ForeignKey(User, null=True, on_delete=SET_NULL)
  - closed_at = DateTimeField(auto_now_add=True)
  - notes = TextField(blank=True)
  - data = JSONField(default=list)  # [{sku, qty_remaining, qty_d1, qty_loss}]
- Nova migração no shop

Leia PRIMEIRO:
- shop/models.py (models existentes: Shop, Promotion, Coupon)

PARTE 3 — ProductAdmin: allows_next_day_sale como checkbox:

O operador não lida com JSON. Precisa ver um checkbox normal no admin.

Tarefa:
- shop/admin.py: criar custom form para ProductAdmin
- Form tem campo extra: allows_next_day_sale = BooleanField(required=False)
- __init__: lê product.meta.get("allows_next_day_sale", False)
- save: escreve de volta no product.meta
- Verificar se Product já tem admin registrado no offering app (se sim, fazer
  unregister + register com a versão estendida, ou usar inlines)

Leia PRIMEIRO:
- shop/admin.py (admin existente — ver como estende core models)
- shopman-core/offering/shopman/offering/admin.py (ProductAdmin do core)

PARTE 4 — DayClosingAdmin:

- shop/admin.py: registrar DayClosingAdmin
- list_display: date, closed_by, closed_at
- list_filter: date
- Read-only após criação (has_change_permission retorna False)
- Detail: mostra data JSON como tabela formatada (readonly widget ou custom template)

PARTE 5 — Seed:

- shop/management/commands/seed.py: marcar 3-4 produtos como
  allows_next_day_sale=True (ex: Pão de Forma, Baguete, Focaccia)

Testes:
- test_product_meta_default_empty_dict
- test_product_meta_allows_next_day_sale_queryable
  (Product.objects.filter(meta__allows_next_day_sale=True))
- test_day_closing_one_per_day_constraint
- test_day_closing_data_snapshot_format
- test_product_admin_shows_checkbox
- test_product_admin_saves_meta

Convenções (CLAUDE.md): ref not code, centavos _q, zero residuals.

make test + make lint ao final.
```

### WP-5 — Tela de Produção Rápida
```
Execute WP-5 do IMPROVEMENTS-PLAN.md: Tela de Produção Rápida.

Pré-requisito: WP-4 concluído (Product.meta existe no Core).

Objetivo: Operador registra produção via formulário rápido no admin Unfold.
Por baixo dos panos, cria WorkOrder no Crafting + fecha + atualiza estoque.

CONTEXTO TÉCNICO:
- WorkOrder no Crafting: status OPEN→DONE, campos quantity/produced, recipe FK
- Ao fechar WO com produced > 0: integração Crafting→Stocking cria Moves
- Admin usa django-unfold (Unfold)

PADRÃO DE CUSTOM VIEW NO UNFOLD (já usado no projeto):
O projeto já tem custom views no admin. O padrão é:

1. Registrar URL via get_urls() em um ModelAdmin (ou AdminSite):
   path("minha-view/", self.admin_site.admin_view(self.minha_view), name="...")
   IMPORTANTE: admin_site.admin_view() garante login + permissões

2. Na view, montar contexto com each_context:
   context = {**self.admin_site.each_context(request), "title": "..."}
   return TemplateResponse(request, "admin/shop/template.html", context)

3. Template estende admin/base.html e usa componentes Unfold:
   {% load unfold %}
   {% component "unfold/components/card.html" %} ... {% endcomponent %}
   {% include "unfold/components/table.html" with ... %}

Ver referência:
- shop/templates/admin/index.html (dashboard Unfold existente)
- shopman-core/customers/shopman/customers/contrib/merge/admin.py (custom view)

INTERFACE:

Tela "Registro de Produção" no admin.

1. Formulário (topo):
   - Recipe: dropdown (recipe.code — recipe.output_ref por nome do produto)
   - Quantidade produzida: number input
   - Posição destino: dropdown de Positions (default: posição is_default=True)
   - Botão "Registrar Produção"

2. Ao POST:
   - Criar WorkOrder(recipe=selecionada, quantity=qty, status="open")
   - Fechar: status="done", produced=qty, finished_at=now
   - Se Crafting tem service de close: usar. Senão, manipular diretamente.
   - Move de estoque: criado pela integração ou manualmente via Stocking services
   - Redirect com success message (django.contrib.messages)

3. Lista do dia (abaixo do formulário):
   - Tabela: WOs de hoje (output_ref, quantity, produced, status, hora)
   - Ação "Estornar": void WO (status="void") — link POST com confirmação
   - Usar componente table do Unfold

PERMISSÕES:
- request.user.has_perm("crafting.add_workorder")
- Sidebar link com permission lambda

SIDEBAR:
- project/settings.py → UNFOLD["SIDEBAR"]:
  {"title": "Produção", "icon": "manufacturing",
   "link": reverse_lazy("admin:shop_production"),
   "permission": lambda request: request.user.has_perm("crafting.add_workorder")}

Leia PRIMEIRO:
- shop/dashboard.py (padrão dashboard_callback, contexto Unfold)
- shop/templates/admin/index.html (template Unfold com componentes)
- shopman-core/crafting/shopman/crafting/models/ (Recipe, WorkOrder, CodeSequence)
- shopman-core/crafting/shopman/crafting/services/ (se existir close/execution service)
- shopman-core/stocking/shopman/stocking/models/position.py (Position, is_default)
- shopman-core/stocking/shopman/stocking/services/movements.py (record_move)
- shopman-core/customers/shopman/customers/contrib/merge/admin.py (padrão custom view)
- project/settings.py (UNFOLD config, SIDEBAR)

ARQUIVOS A CRIAR/MODIFICAR:
- shop/views/production.py — NOVO (view GET+POST)
- shop/templates/admin/shop/production.html — NOVO (template Unfold)
- shop/admin.py — registrar URL via get_urls
- project/settings.py — sidebar link
- tests/test_production_quick.py — NOVO

Testes:
- test_production_page_requires_permission
- test_production_page_loads_recipes
- test_production_creates_and_closes_workorder
- test_production_updates_stock_quantity
- test_production_void_reverts_workorder
- test_production_lists_today_only

Convenções (CLAUDE.md): ref not code, centavos _q, zero residuals.

make test + make lint ao final.
```

### WP-6 — Fechamento do Dia + Cleanup D-1 + Dashboard Widget
```
Execute WP-6 do IMPROVEMENTS-PLAN.md: Fechamento do Dia + Cleanup + Dashboard.

Pré-requisitos (já concluídos):
- WP-3: Position "ontem" existe. ChannelConfig.Stock.allowed_positions funciona.
  remote() exclui "ontem", pos() inclui tudo.
- WP-4: Product.meta existe (com allows_next_day_sale). DayClosing model existe.
- WP-5: Padrão de custom view admin Unfold está estabelecido em
  shop/views/production.py e shop/templates/admin/shop/production.html.

CONTEXTO DE NEGÓCIO:
Ao final do expediente, operador informa quantidades não vendidas:
- Produtos com product.meta["allows_next_day_sale"]=True → move para posição "ontem"
  (serão vendidos amanhã com 50% off via D1DiscountModifier, apenas em canais presenciais)
- Produtos perecíveis sem essa flag (shelf_life_days==0) → registra como perda
- Não perecíveis (shelf_life_days > 0 ou None) → permanecem no estoque (nenhuma ação)

PARTE 1 — Tela de Fechamento do Dia:

View: shop/views/closing.py (mesmo padrão de production.py)
Template: shop/templates/admin/shop/closing.html

GET (abrir tela):
- Consultar Quants em posições de venda (Position.is_saleable=True, excluir ref="ontem")
- Agrupar por SKU (sku → sum(quantity))
- Para cada SKU, buscar Product (nome, shelf_life_days, meta)
- Classificar cada item:
  - D-1 elegível: meta.get("allows_next_day_sale", False) == True
  - Perda: shelf_life_days == 0 e not allows_next_day_sale
  - Neutro: shelf_life_days > 0 ou None (não perecível)
- Mostrar tabela com: SKU, nome, qty disponível, classificação (badge colorido),
  campo "não vendidos" (editável, default=qty)
- Se DayClosing para hoje já existe: mostrar read-only com dados do fechamento
- Se há estoque em "ontem" com moves >1 dia: mostrar alerta no topo

POST (confirmar fechamento):
- Validar: não existe DayClosing para hoje
- Para cada SKU com qty_nao_vendido > 0:
  - D-1 elegível:
    Move(sku=sku, delta=-qty, quant__position=origem, reason="fechamento:YYYY-MM-DD")
    Move(sku=sku, delta=+qty, quant__position="ontem", reason="d1:YYYY-MM-DD")
  - Perda:
    Move(sku=sku, delta=-qty, quant__position=origem, reason="perda:YYYY-MM-DD")
  - Neutro: skip (não perecível, fica no estoque)
- Criar DayClosing(date=hoje, closed_by=request.user,
  data=[{sku, qty_remaining, qty_d1, qty_loss} para cada item])
- messages.success + redirect

URL: admin/shop/closing/ (name: shop_closing)
Permissão: request.user.has_perm("shop.add_dayclosing")
Sidebar: {"title": "Fechamento", "icon": "point_of_sale", ...}

PARTE 2 — Management Command cleanup_d1:

shop/management/commands/cleanup_d1.py

Roda no início do expediente (cron diário). Remove D-1 vencido.

Lógica:
- Buscar Quants na posição "ontem" com quantity > 0
- Para cada quant: verificar move mais recente (reason starts with "d1:")
  - Se data do move > 1 dia atrás: mover para perda
  - Move(sku, delta=-qty, position="ontem", reason="perda_d1_vencido:YYYY-MM-DD")
- Idempotente: se qty já é 0, skip
- Log: self.stdout.write(f"Removido: {sku} x{qty}")

Uso: python manage.py cleanup_d1
Cron: executar diariamente antes da abertura (ex: 05:00)

PARTE 3 — Dashboard Widget D-1:

shop/dashboard.py: adicionar ao dashboard_callback existente.

Nova seção "Estoque D-1":
- Consultar Quants na posição ref="ontem" com quantity > 0
- Tabela: SKU, nome do produto, qty, data de entrada
- Link para tela de fechamento
- Se posição "ontem" não existe ou sem estoque: ocultar seção
- Usar mesmo padrão das outras tabelas do dashboard (dicts com keys para template)

Leia PRIMEIRO:
- shop/views/production.py (padrão de view Unfold — criado em WP-5)
- shop/templates/admin/shop/production.html (padrão de template — criado em WP-5)
- shop/dashboard.py (dashboard_callback existente — ver como monta contexto)
- shop/templates/admin/index.html (template dashboard — ver componentes usados)
- shop/models.py (DayClosing — criado em WP-4)
- shopman-core/stocking/shopman/stocking/models/ (Quant, Move, Position)
- shopman-core/stocking/shopman/stocking/services/movements.py (record_move)
- shopman-core/offering/shopman/offering/models/product.py (Product.meta — criado em WP-4)

ARQUIVOS A CRIAR/MODIFICAR:
- shop/views/closing.py — NOVO
- shop/templates/admin/shop/closing.html — NOVO
- shop/management/commands/cleanup_d1.py — NOVO
- shop/dashboard.py — adicionar seção D-1
- shop/admin.py — registrar URL closing
- project/settings.py — sidebar link "Fechamento"
- tests/test_day_closing.py — expandir com testes de closing + cleanup

Testes:
- test_closing_page_requires_permission
- test_closing_page_lists_skus_with_stock
- test_closing_moves_d1_eligible_to_ontem
- test_closing_registers_loss_for_ineligible
- test_closing_skips_non_perishable
- test_closing_creates_day_closing_record
- test_closing_blocks_duplicate_same_day
- test_closing_shows_alert_for_old_d1
- test_cleanup_d1_removes_old_stock
- test_cleanup_d1_idempotent_on_zero_qty
- test_dashboard_shows_d1_widget_when_stock_exists
- test_dashboard_hides_d1_widget_when_empty

Convenções (CLAUDE.md): ref not code, centavos _q, zero residuals.

make test + make lint ao final.
```

### WP-7 — Atualizar Documentação
```
Execute WP-7 do IMPROVEMENTS-PLAN.md: Atualizar Documentação.

Os planos EVOLUTION-PLAN e PARITY-PLAN estão desatualizados. Vários WPs foram
parcial ou totalmente implementados sem atualizar os planos.

Leia PRIMEIRO (código real vs plano):
- EVOLUTION-PLAN.md (todos os WPs)
- PARITY-PLAN.md (todos os WPs)
- channels/web/views/catalog.py (WP-E1 implementado?)
- channels/handlers/loyalty.py (WP-E2 implementado?)
- shop/dashboard.py (WP-E4 implementado?)
- channels/backends/notification_email.py + templates/ (WP-E5 implementado?)
- channels/api/catalog.py + api/tracking.py (WP-E6 implementado?)
- channels/web/views/cart.py (WP-P3 coupon views?)
- channels/web/views/tracking.py (WP-P4 tracking?)

Tarefas:
1. EVOLUTION-PLAN.md: Para cada WP, marcar status real:
   - COMPLETO: se 100% implementado
   - PARCIAL (X%): listar o que falta
   - PENDENTE: se ainda não começou
   Manter apenas tarefas realmente pendentes.

2. PARITY-PLAN.md: Idem.

3. docs/architecture.md: Verificar se reflete handlers/backends atuais.

4. CLAUDE.md: Atualizar descrição do estado do projeto.

5. Documentar WP-4/b/c (Product.meta, operações, fechamento) nos guias.

Não alterar código — apenas documentação.
```

### WP-8 — Testes para Gaps
```
Execute WP-8 do IMPROVEMENTS-PLAN.md: Testes para Gaps Identificados.

Gaps de teste prioritários:

1. EmployeeDiscountModifier — zero testes dedicados
2. HappyHourModifier — zero testes dedicados
3. BusinessHoursValidator — zero testes unitários
4. MinimumOrderValidator — zero testes unitários
5. Cancellation flow (holds release + notification)
6. DayClosing + produção rápida (WP-4/b/c)

Nota: Os bugs de persistência (WP-1) já devem estar corrigidos neste ponto.

Leia PRIMEIRO:
- shop/modifiers.py (Employee, HappyHour)
- shop/validators.py (BusinessHours, MinimumOrder)
- channels/hooks.py (_on_cancelled)
- tests/test_promotions.py (padrão existente de testes de modifiers)
- tests/web/test_web_business_rules.py (se existir)

Testes a criar:
- test_employee_discount_applies_to_staff
- test_employee_discount_skips_non_staff
- test_employee_discount_amount_correct
- test_happy_hour_applies_in_window
- test_happy_hour_skips_outside_window
- test_happy_hour_skips_employee_discounted_items
- test_business_hours_rejects_outside
- test_business_hours_allows_within
- test_minimum_order_rejects_below
- test_minimum_order_allows_above
- test_minimum_order_only_for_delivery

make test + make lint ao final.
```

### WP-9 — Quick Wins Core
```
Execute WP-9 do IMPROVEMENTS-PLAN.md: Capacidades Core Subutilizadas.

3 quick wins para ativar capacidades prontas no Core:

1. CostBackend adapter (Crafting → Offering):
   - Core define CostBackend protocol em Offering
   - Crafting sabe custo de produção (Recipe + RecipeItems)
   - Criar channels/backends/cost.py com CraftingCostBackend
   - get_cost(sku): busca Recipe por output_ref=sku, soma custo de RecipeItems
   - Registrar em settings: OFFERING["COST_BACKEND"]

2. Batch traceability no admin:
   - Core de Stocking tem Batch (production_date, expiry_date, supplier)
   - Registrar BatchAdmin em shop/admin.py
   - Filtros: expiry_date, supplier
   - Inline em QuantAdmin (se registrado)

3. Promotion.customer_segments (preparação):
   - Adicionar campo JSONField customer_segments=[] ao Promotion
   - Sem lógica de matching ainda — apenas campo no model
   - Migration

Leia PRIMEIRO:
- shopman-core/offering/shopman/offering/cost.py (CostBackend protocol)
- shopman-core/crafting/shopman/crafting/models/ (Recipe, RecipeItem)
- shopman-core/stocking/shopman/stocking/models/batch.py (Batch)
- shop/models.py (Promotion)
- shop/admin.py (admin existente)

make test + make lint ao final.
```

---

## Protocolo de Execução

Ao concluir cada WP:
1. `make test` + `make lint` — 0 failures, 0 warnings
2. Reportar resultado e arquivos alterados
3. Se último WP: "Improvements completo."

Sequência: WP-1 → WP-2 → WP-3 → WP-4 → WP-5 → WP-6 → WP-7 → WP-8 → WP-9
