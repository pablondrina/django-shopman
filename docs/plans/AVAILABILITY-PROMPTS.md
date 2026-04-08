# AVAILABILITY-PROMPTS — Prompts Auto-Suficientes

> Cada prompt abaixo pode ser executado em uma sessão isolada do Claude Code.
> Contém todo o contexto necessário para execução sem equívoco.
> Executar na ordem indicada no AVAILABILITY-PLAN.md.

---

## WP-A1: Limpar D-1 do Storefront

```
Leia o plano docs/plans/AVAILABILITY-PLAN.md (seções Diagnóstico D1 e WP-A1).

CONTEXTO:
D-1 (estoque do dia anterior, batch "D-1", posição "ontem") está aparecendo para
clientes no storefront: badge "Últimas unidades", preço com desconto 50%, texto
"Produzido ontem". Isso viola uma regra de negócio: D-1 NUNCA aparece para o
cliente. D-1 é exclusivo do POS (balcão).

O canal web já tem allowed_positions que exclui "ontem" (ver seed.py ~linha 1229),
mas o badge system e o pricing do storefront tratam D-1 explicitamente.

ARQUIVOS PRINCIPAIS:
- framework/shopman/web/views/_helpers.py:
  - _line_item_is_d1() (linhas ~78-91): detecta se item é D-1 pelo badge
  - _availability_badge() (linhas ~92-132): retorna badge-d1 quando só há D-1
  - _annotate_products() (linhas ~237-380): calcula is_d1, d1_pct, preço D-1
- framework/shopman/templates/storefront/partials/product_card.html:
  - Badge de desconto D-1 (topo esquerdo), preço D-1 (vermelho)
- framework/shopman/templates/storefront/product_detail.html:
  - Badge "Dia Anterior", preço D-1, texto "Produzido ontem"
- framework/shopman/web/views/catalog.py:
  - ProductDetailView (~linha 284): cálculo de D-1

TAREFAS:
1. Leia TODOS os arquivos listados acima antes de fazer qualquer alteração.

2. Em _availability_badge(): Remover o estado badge-d1 / "Últimas unidades".
   Quando o breakdown mostra APENAS d1 > 0 (ready=0, in_production=0), retornar
   badge-sold-out ou badge-unavailable com label "Indisponível" e can_add_to_cart=False.

3. Em _annotate_products(): Remover toda lógica de is_d1, d1_pct, preço D-1 para
   o storefront. A variável is_d1 e d1_pct NÃO devem ser calculadas nem passadas
   ao template. Se houver lógica POS que dependa disso, isolar (o POS tem sua
   própria view em web/views/pos.py).

4. Em _line_item_is_d1(): Se é usada APENAS no storefront, remover. Se o POS
   usa, manter mas garantir que não é chamada pelas views do storefront.

5. Em product_card.html: Remover completamente o badge de desconto D-1, o preço
   D-1 formatado, e qualquer referência visual a D-1.

6. Em product_detail.html: Remover badge "Dia Anterior", preço D-1, texto
   "Produzido ontem — qualidade garantida, preço especial", e qualquer referência.

7. Verificar que o channel scope (allowed_positions) exclui "ontem" para o canal
   web, garantindo que availability_for_sku() com scope retorna d1=0.
   Não alterar o Stockman — ele está correto.

8. Rodar make test-framework para garantir que não quebrou nada.

REGRAS:
- NÃO alterar nada em packages/ (Core é sagrado).
- NÃO inventar features — apenas remover D-1 do storefront.
- Zero resíduos: se um bloco inteiro é removido, não deixar comentários "# removed".
- Se o POS usa D-1, manter para o POS (views/pos.py) mas isolar do storefront.
```

---

## WP-A2: Simplificar Badges para o Cliente

```
Leia o plano docs/plans/AVAILABILITY-PLAN.md (seções DD-1, DD-2 e WP-A2).

PRÉ-REQUISITO: WP-A1 já foi executado (D-1 removido do storefront).

CONTEXTO:
Atualmente o badge system tem 6 estados (available, preparing, d1_only, planned,
sold-out, paused). O cliente não precisa ver conceitos internos como "Preparando"
ou "Em breve". Para o cliente existem apenas:
- Disponível: sem badge (implícito), pode comprar
- Indisponível: badge cinza "Indisponível", não pode comprar
- Esgotado (opcional): badge cinza "Esgotado" — tinha estoque mas acabou

O frontend NÃO deve consumir o breakdown {ready, in_production, d1} diretamente.
Deve consumir uma visão simplificada.

ARQUIVOS PRINCIPAIS:
- framework/shopman/web/views/_helpers.py:
  - _availability_badge() (linhas ~92-132): REFATORAR
  - _annotate_products() (linhas ~237-380): REFATORAR para usar visão simplificada
  - _get_availability() (se existir): helper que chama availability_for_sku
- packages/stockman/shopman/stocking/services/availability.py:
  - availability_for_sku() e availability_scope_for_channel(): NÃO ALTERAR (ler apenas)
- framework/shopman/templates/storefront/partials/product_card.html: ATUALIZAR
- framework/shopman/templates/storefront/product_detail.html: ATUALIZAR
- framework/shopman/web/cart.py: Cart get_cart() soma breakdown manualmente — SIMPLIFICAR
- framework/shopman/static/storefront/css/output.css: LIMPAR classes obsoletas

TAREFAS:
1. Leia TODOS os arquivos listados antes de alterar.

2. Criar helper storefront_availability(sku, channel_ref) em _helpers.py:
   - Chama availability_scope_for_channel(channel_ref) para obter scope
   - Chama availability_for_sku(sku, **scope)
   - Retorna dict simplificado:
     {
       "available_qty": Decimal,  # total_available do resultado (ready+in_prod, SEM d1)
       "can_order": bool,         # available_qty > 0 AND not is_paused
       "is_paused": bool,         # do resultado
       "had_stock": bool,         # True se já houve Quant para este SKU (ver nota)
     }
   - Para had_stock: verificar se existem Quants (físicos ou planejados) para o
     SKU, independente de qty atual. Query simples:
     Quant.objects.filter(sku=sku).exists(). Se custoso, usar is_planned do
     resultado original como proxy (se já foi planejado, "tinha" stock previsto).

3. Refatorar _availability_badge() para usar storefront_availability():
   - Se can_order=True: retornar badge-available (sem label, can_add_to_cart=True)
   - Se can_order=False e had_stock=True: retornar badge-sold-out
     (label="Esgotado", can_add_to_cart=False, css_class="badge-sold-out")
   - Se can_order=False e had_stock=False (ou is_paused): retornar badge-unavailable
     (label="Indisponível", can_add_to_cart=False, css_class="badge-unavailable")
   - Remover TODOS os estados antigos: badge-preparing, badge-planned, badge-d1

4. Refatorar _annotate_products() para usar storefront_availability() em batch.
   Usar availability_for_skus() para bulk query e converter para visão simplificada.
   Remover toda referência a breakdown, in_production, d1, is_d1, d1_pct.

5. Em cart.py (get_cart): Onde soma breakdown manualmente, usar available_qty da
   visão simplificada. Não somar ready+in_production+d1 — usar total_available
   (ou total_orderable, que já existe no resultado de availability_for_sku).

6. Atualizar product_card.html:
   - Apenas 2 classes de badge: badge-sold-out e badge-unavailable
   - Ambas com visual cinza, diferindo apenas no texto
   - Remover qualquer CSS de badge-preparing, badge-planned, badge-d1

7. Atualizar product_detail.html:
   - Mesma lógica: badge cinza com "Esgotado" ou "Indisponível"
   - Seção de alternativas: mostrar quando can_order=False (já existe, manter)
   - Remover info boxes de "Em preparo", "Produção planejada", etc.

8. Limpar CSS: remover classes badge-preparing, badge-planned, badge-d1 e
   variantes de cor associadas.

9. Rodar make test-framework.

REGRAS:
- NÃO alterar packages/ (Core é sagrado).
- availability_for_sku() continua retornando breakdown para uso interno. Apenas
  o storefront para de consumir o breakdown diretamente.
- Se had_stock for muito custoso (query extra por SKU), simplificar: usar apenas
  "Indisponível" para tudo que não pode comprar. Anotar como TODO para futuro.
```

---

## WP-A4: Wiring do Banner de Horário

```
Leia o plano docs/plans/AVAILABILITY-PLAN.md (seções DD-3 e WP-A4).

CONTEXTO:
O banner de horário de funcionamento já está implementado em 3 partes, mas nunca
foi conectado (wired):
1. _shop_status() em _helpers.py (~382-456): retorna {is_open, opens_at, closes_at, message}
2. Banner em base.html (~75-80): renderiza shop_status.message com cor verde/vermelha
3. _format_opening_hours() em _helpers.py (~457-527): formata horários para footer

O context_processors.py (~11-52) tem shop() e cart_count(), mas NÃO inclui
shop_status nem opening_hours_display.

ARQUIVOS:
- framework/shopman/context_processors.py (linhas 11-52)
- framework/shopman/web/views/_helpers.py (linhas 382-527)
- framework/shopman/templates/storefront/base.html (linhas 75-80, 97-102)
- framework/shopman/models/shop.py: Shop.opening_hours (JSONField)
- framework/shopman/management/commands/seed.py: popular opening_hours

TAREFAS:
1. Leia TODOS os arquivos listados antes de alterar.

2. Em context_processors.py, na função shop():
   - Importar _shop_status e _format_opening_hours de _helpers
   - Adicionar ao dict retornado:
     "shop_status": _shop_status(shop_obj),
     "opening_hours_display": _format_opening_hours(shop_obj),
   - Atenção: shop_obj é o Shop singleton. Se não existir (first run), retornar
     valores default (is_open=True, message=None, opening_hours_display=[]).

3. Verificar _shop_status():
   - Mensagens devem ser claras: "Aberto até 19h", "Fechado — abrimos às 7h",
     "Fechamos em 30 min", "Abrimos em 15 min".
   - Ajustar mensagens se necessário. Usar timezone.localtime() para hora local.
   - Se Shop.opening_hours não configurado: retornar is_open=True, message=None.

4. Verificar base.html:
   - Banner condicional: só aparece se shop_status.message existe
   - Verde se is_open=True, vermelho se is_open=False
   - Fixo no topo, abaixo do header
   - Confirmar que renderiza corretamente com os dados do context processor.

5. Verificar footer e home:
   - base.html tem placeholder para horários no footer
   - Confirmar que opening_hours_display é consumido corretamente
   - Formato esperado: [{"label": "Terça a Sábado", "hours": "7h — 19h"}, ...]

6. Em seed.py: garantir que Shop.opening_hours é populado com dados realistas.
   Se já existe, verificar formato. Exemplo:
   {"tuesday": {"open": "07:00", "close": "19:00"},
    "wednesday": {"open": "07:00", "close": "19:00"},
    ...
    "sunday": {"open": "07:00", "close": "13:00"}}
   Segunda fechado (boulangerie típica).

7. Rodar make test-framework.

REGRAS:
- NÃO alterar packages/.
- NÃO bloquear nada com business hours — apenas informativo.
- O banner é sutil, não modal. Informação, não barreira.
```

---

## WP-A6: Validação Server-Side de Slots

```
Leia o plano docs/plans/AVAILABILITY-PLAN.md (seções DD-8 e WP-A6).

CONTEXTO:
O campo delivery_time_slot no checkout aceita qualquer valor submetido pelo
cliente. Não há validação server-side. O cliente pode enviar slots inexistentes,
passados, ou manipulados via devtools. A validação atual é apenas client-side
(Alpine.js no template checkout.html, ~514-524).

ARQUIVOS:
- framework/shopman/web/views/checkout.py:
  - delivery_time_slot lido em ~201
  - Armazenado em checkout_data em ~317-318
- framework/shopman/services/pickup_slots.py:
  - Slots configurados via Shop.defaults["pickup_slots"]
  - get_slots(): retorna lista de slots configurados
  - annotate_slots_for_checkout(): retorna {pickup_slots, earliest_slot_ref, ...}
- framework/shopman/templates/storefront/checkout.html: (~514-524)
- framework/shopman/models/shop.py: Shop.defaults JSONField

TAREFAS:
1. Leia checkout.py e pickup_slots.py antes de alterar.

2. Em checkout.py, no método post() (ou num helper dedicado), ANTES de chamar
   checkout_process(), validar delivery_time_slot:

   a) Se delivery_time_slot está preenchido:
      - Buscar slots configurados via get_slots() ou Shop.defaults["pickup_slots"]
      - Validar que o ref submetido existe na lista de slots configurados
      - Se a data é hoje (delivery_date == today ou não é preorder):
        validar que slot.starts_at > now (hora atual)
      - Se a data é futura: qualquer slot válido é aceito
      - Se inválido: adicionar erro ao form (errors["delivery_time_slot"])

   b) Se delivery_time_slot está vazio e fulfillment_type é "pickup":
      - Exigir seleção de slot (erro se vazio)

3. Criar testes em framework/shopman/tests/:
   - test_slot_inexistente: slot "slot-99" → erro
   - test_slot_passado_hoje: slot "slot-09" às 15h → erro
   - test_slot_futuro_hoje: slot "slot-15" às 10h → OK
   - test_slot_data_futura: qualquer slot → OK
   - test_slot_vazio_pickup: fulfillment_type="pickup" sem slot → erro
   - test_slot_vazio_delivery: fulfillment_type="delivery" sem slot → OK

4. Rodar make test-framework.

REGRAS:
- NÃO alterar packages/.
- Validação simples e direta. Sem overengineering.
- Mensagem de erro clara: "Horário de retirada inválido" ou similar.
```

---

## WP-A3: Remover Restrições Artificiais de Encomenda

```
Leia o plano docs/plans/AVAILABILITY-PLAN.md (seções DD-3, DD-9 e WP-A3).

PRÉ-REQUISITO: WP-A4 já foi executado (banner de horário funcional).

CONTEXTO:
O checkout tem restrições artificiais que impedem encomendas legítimas:
1. Cutoff hour 18h: bloqueia pedidos para amanhã após 18h (checkout.py ~537)
2. Janela de 7 dias: máximo de pré-pedido (checkout.py ~533)
3. Min quantity para pré-pedidos: restrição de qtd mínima (checkout.py ~547)

O cliente deveria poder encomendar a qualquer hora, para qualquer data dentro
de uma janela configurável (default 30 dias), respeitando apenas disponibilidade
(produção planejada ou estoque) e datas fechadas do calendário do shop.

ARQUIVOS:
- framework/shopman/web/views/checkout.py:
  - _validate_preorder() (~523-553): lógica a refatorar
  - post() método: fluxo de checkout
- framework/shopman/templates/storefront/checkout.html: date picker
- framework/shopman/models/shop.py: Shop.defaults
- framework/shopman/management/commands/seed.py: popular defaults

TAREFAS:
1. Leia checkout.py completamente (especialmente _validate_preorder) e o template.

2. Refatorar _validate_preorder():
   - REMOVER: cutoff hour logic (bloquear por horário). O cliente encomenda quando quiser.
   - ALTERAR: max_date de 7 dias para Shop.defaults.get("max_preorder_days", 30) dias.
   - REMOVER: preorder_min_quantity check. Sem quantidade mínima para encomendas.
   - MANTER: validação de data no passado (não pode encomendar para ontem).
   - ADICIONAR: validação de closed_dates.

3. Implementar leitura de closed_dates:
   - Ler Shop.defaults.get("closed_dates", [])
   - Formato: [{"date": "2026-12-25", "label": "Natal"},
               {"from": "2026-01-15", "to": "2026-01-31", "label": "Férias"}]
   - Se delivery_date cai em closed_date: erro com label ("Fechado: Natal")
   - Criar helper is_closed_date(date, closed_dates) -> (bool, label|None)

4. Atualizar template checkout.html:
   - Date picker: max date = hoje + max_preorder_days
   - Desabilitar datas fechadas no picker (passar closed_dates para o Alpine)
   - Remover qualquer referência a cutoff hour no JS/Alpine
   - Remover referência a quantidade mínima de pré-pedido

5. Em seed.py: popular Shop.defaults com:
   - "max_preorder_days": 30
   - "closed_dates": [
       {"date": "2026-12-25", "label": "Natal"},
       {"date": "2026-12-31", "label": "Réveillon"},
       {"date": "2026-01-01", "label": "Confraternização Universal"},
     ]

6. Rodar make test-framework.

REGRAS:
- NÃO alterar packages/.
- NÃO inventar features — remover restrições e adicionar configurabilidade.
- Datas fechadas editáveis via admin (Shop.defaults no Unfold).
- O cliente encomenda a qualquer hora. Horário é informativo (banner), não bloqueante.
```

---

## WP-A5: Centralizar Serviço de Alternativas

```
Leia o plano docs/plans/AVAILABILITY-PLAN.md (seções DD-5 e WP-A5).

PRÉ-REQUISITO: WP-A2 já foi executado (badge simplificado com storefront_availability).

CONTEXTO:
A busca de alternativas está fragmentada em 3 camadas:
1. Offerman: find_alternatives() em packages/offerman/shopman/offering/contrib/suggestions/suggestions.py (~60-79)
   — busca por keywords + collection + score. NÃO ALTERAR.
2. Adapter: get_alternatives() em framework/shopman/adapters/stock_internal.py (~217-247)
   — filtra por estoque. Responsabilidade errada (adapter de stock fazendo busca de alternativas).
3. Views: _load_alternatives() em framework/shopman/web/views/catalog.py (~226-239)
   — bridge para views. Cada view importa de forma diferente.

Consumidores atuais:
- catalog.py: ProductDetailView usa _load_alternatives() para PDP
- catalog.py: CartAlternativesView (~256-265) para carrinho
- handlers/stock.py: _build_issue() busca alternativas no handler
- api/catalog.py: endpoint REST

TAREFAS:
1. Leia TODOS os arquivos/funções listados antes de alterar.

2. Criar framework/shopman/services/alternatives.py:

   from decimal import Decimal
   from shopman.offering.contrib.suggestions import find_alternatives as _find_candidates

   def find(sku: str, *, qty: Decimal = Decimal("1"), channel: str = None, limit: int = 4) -> list[dict]:
       """
       Busca alternativas disponíveis para o canal.
       Ponto único de consumo para todos os contextos.
       """
       # 1. Buscar candidatos via Offerman (keywords + collection + score)
       candidates = _find_candidates(sku, limit=limit * 2)  # pegar extras para filtrar

       # 2. Filtrar por disponibilidade no canal
       #    Usar storefront_availability() de _helpers.py (ou inline similar)
       #    Apenas candidatos com available_qty >= qty

       # 3. Anotar com preço (CatalogService.unit_price) e badge simplificado

       # 4. Retornar top <limit> dicts:
       #    [{"sku", "name", "price_q", "price_display", "available_qty", "can_order"}, ...]

       # Graceful: se qualquer erro, return []

3. Refatorar consumidores para usar o serviço centralizado:

   a) catalog.py _load_alternatives(): delegar para services.alternatives.find()
      (manter a função como thin wrapper se necessário para anotação de template)

   b) catalog.py CartAlternativesView: usar services.alternatives.find()

   c) handlers/stock.py _build_issue(): usar services.alternatives.find()
      ao invés de backend.get_alternatives()

   d) api/catalog.py: usar services.alternatives.find()

4. Remover get_alternatives() de adapters/stock_internal.py.
   Alternativas NÃO são responsabilidade do adapter de estoque.
   Se o StockBackend protocol define get_alternatives(), manter no protocol
   mas marcar como deprecated. Se só o adapter usa, remover.

5. Verificar protocols.py: se Alternative dataclass e get_alternatives no
   StockBackend protocol, avaliar se faz sentido manter. Se nenhum outro
   backend implementa, remover do protocol.

6. Rodar make test-framework.

REGRAS:
- NÃO alterar packages/offerman/.../suggestions.py (lógica de scoring funciona).
- NÃO alterar packages/stockman/ (Core é sagrado).
- Serviço centralizado = um import para todos os contextos.
- Graceful degradation: se falhar, retorna []. Nunca quebra o fluxo principal.
```

---

## WP-A7: Elevar craft.suggest() a First-Class

```
Leia o plano docs/plans/AVAILABILITY-PLAN.md (seções DD-6 e WP-A7).

CONTEXTO:
craft.suggest() calcula sugestões de produção baseando-se em demanda histórica.
Atualmente é funcional mas limitado:
- Sem sazonalidade (não distingue verão de inverno)
- Sem análise de waste (campo wasted existe em DailyDemand mas é ignorado)
- soldout_at nunca é populado pelo OrderingDemandBackend
- Sem indicador de confiança da sugestão
- Safety stock (20%) não editável pelo admin

ARQUIVOS PRINCIPAIS (LER ANTES DE ALTERAR):
- packages/craftsman/shopman/crafting/services/queries.py:
  - suggest() method e _estimate_demand() (~87-239)
  - Suggestion dataclass
- packages/craftsman/shopman/crafting/protocols/demand.py:
  - DemandProtocol, DailyDemand dataclass (~27+)
- packages/craftsman/shopman/crafting/contrib/demand/backend.py:
  - OrderingDemandBackend.history() (~34-76) — popula DailyDemand
- packages/craftsman/shopman/crafting/conf.py:
  - SAFETY_STOCK_PERCENT, HISTORICAL_DAYS, SAME_WEEKDAY_ONLY
- packages/craftsman/shopman/crafting/tests/test_vnext.py: testes existentes

MODELO DE SAZONALIDADE:
- Quente: Out(10), Nov(11), Dez(12), Jan(1), Fev(2), Mar(3)
- Meia estação: Abr(4), Mai(5), Set(9)
- Frio: Jun(6), Jul(7), Ago(8)
- Configurável via Shop.defaults["seasons"] (framework, editável no admin)
- Para o Craftsman (package puro): receber como parâmetro season_months

CONFIANÇA:
- Baseada em sample_size (quantos dias de histórico foram usados):
  - >= 8: "high" (padrão consolidado)
  - 3-7: "medium" (razoável)
  - < 3: "low" (poucos dados)
  - 0: não sugere (skip recipe)
- Aparece no basis dict e no output do suggest_production

FATORES DE ALTA DEMANDA:
- Sexta-feira, sábado: demanda naturalmente maior
- Véspera de feriado: demanda maior
- Multiplicador configurável: Shop.defaults["high_demand_multiplier"] (default 1.2)
- Para o Craftsman: receber como parâmetro high_demand_multiplier

TAREFAS:
1. Leia TODOS os arquivos do Craftsman listados antes de alterar.

2. Em queries.py, refatorar suggest():

   a) Novo parâmetro season_months: list[int] | None = None
      Se fornecido, filtrar histórico para incluir apenas dias cujo mês está
      em season_months. Exemplo: season_months=[10,11,12,1,2,3] para "hot".
      O filtro de weekday (SAME_WEEKDAY_ONLY) continua ativo DENTRO da estação.

   b) Novo parâmetro high_demand_multiplier: Decimal | None = None
      Se fornecido E a data alvo é sexta(4) ou sábado(5): multiplicar sugestão
      por este fator. weekday() == 4 ou 5.
      O DemandProtocol.history() pode também receber informação de feriados para
      filtrar, mas v1 pode ser simples: apenas weekday.

   c) Incluir waste na análise:
      Na iteração do histórico, calcular waste_rate = sum(wasted) / sum(sold).
      Se waste_rate > 0.15 (15%): reduzir sugestão proporcionalmente.
      Lógica: se desperdiça 20%, produzir 20% menos que a média sugere.
      Adicionar waste_rate ao basis dict.

   d) Confiança:
      Após calcular sample_size, determinar confidence:
      - len(estimates) >= 8: "high"
      - len(estimates) >= 3: "medium"
      - len(estimates) >= 1: "low"
      - 0: skip (não gera Suggestion)
      Adicionar confidence ao Suggestion.basis dict.

   e) Expandir basis dict para incluir:
      "season": "hot" | "mild" | "cold" | None,
      "waste_rate": Decimal | None,
      "confidence": "high" | "medium" | "low",
      "high_demand_applied": bool,

3. Em conf.py: Verificar que SAFETY_STOCK_PERCENT é configurável. Não precisa
   mudar nada se já está no CRAFTING dict. O framework (não o package) cuidará
   de expor em Shop.defaults.

4. Em backend.py (OrderingDemandBackend.history()):
   - Investigar como popular soldout_at. Opções:
     a) Se existe registro de quando estoque zerou (Move com resultado 0),
        usar esse timestamp como soldout_at.
     b) Se não há dado direto, manter soldout_at=None (a extrapolação não
        ativa, mas o suggest funciona sem ela).
   - Se a opção (a) for viável e simples, implementar. Senão, anotar como TODO.

5. Atualizar management command suggest_production para exibir confidence e
   waste_rate no output.

6. Atualizar testes em test_vnext.py:
   - test_suggest_with_season_filter: histórico com meses variados, só hot filtrado
   - test_suggest_confidence_levels: sample_size 1, 5, 10
   - test_suggest_waste_adjustment: waste_rate > 15% reduz sugestão
   - test_suggest_high_demand_friday: multiplicador aplicado em sexta

7. Rodar make test (todos — inclui craftsman).

REGRAS:
- Alterações APENAS em packages/craftsman/ (e management command no framework).
- suggest() recebe parâmetros opcionais — backward compatible.
- Sem breaking changes: quem chama suggest() sem novos params tem comportamento idêntico.
- O framework (não o package) cuida de ler Shop.defaults e passar os parâmetros.
```

---

## WP-A8: Validação de Remanejo no adjust()

```
Leia o plano docs/plans/AVAILABILITY-PLAN.md (seções DD-7 e WP-A8).

CONTEXTO:
O remanejo de produção é redistribuir quantidades entre WorkOrders OPEN que
compartilham o mesmo insumo. Hoje, adjust() aceita qualquer quantidade sem
validar insumos nem compromissos com clientes. Mantemos OPEN/DONE/VOID (sem
novo status PROCESSING — KISS).

CENÁRIO REAL:
Massa de tradição: 52kg planejados. 4 WOs OPEN na mesma data:
- WO-1 BAGUETTE 20un (10kg massa)
- WO-2 BÂTARD 20un (12kg massa)
- WO-3 FENDU 30un (15kg massa)
- WO-4 TABATIÈRE 30un (15kg massa)
Operador quer remanejar para 40/0/50/10. Sistema deve validar:
- BÂTARD pode ir a 0? Só se não há holds (encomendas) para BÂTARD na data.
- TABATIÈRE pode cair para 10? Só se holds <= 10.
- Total de massa após remanejo (50kg) <= disponível (52kg)? Sim.

ARQUIVOS PRINCIPAIS (LER ANTES DE ALTERAR):
- packages/craftsman/shopman/crafting/services/scheduling.py:
  - CraftPlanning.adjust() (~182-220+)
- packages/craftsman/shopman/crafting/services/queries.py:
  - needs() — calcula BOM para WOs OPEN numa data
- packages/craftsman/shopman/crafting/protocols/inventory.py:
  - InventoryProtocol (available, reserve, etc.)
- packages/craftsman/shopman/crafting/adapters/stocking.py:
  - StockingBackend — implementa InventoryProtocol
- packages/craftsman/shopman/crafting/models/work_order.py:
  - WorkOrder model, Recipe relation
- packages/craftsman/shopman/crafting/exceptions.py:
  - CraftError — para novos códigos de erro

TAREFAS:
1. Leia TODOS os arquivos listados antes de alterar.

2. Em scheduling.py, no método adjust(), APÓS as validações existentes
   (status == OPEN, quantity > 0, rev check), adicionar:

   V1 — Validar holds do SKU de saída:
   - Obter committed = DemandProtocol.committed(output_ref, scheduled_date)
     OU consultar InventoryProtocol (depende de como committed está acessível)
   - Se quantity < committed:
     raise CraftError("COMMITTED_HOLDS", committed=float(committed),
                       requested=float(quantity),
                       message=f"Há {committed} unidades comprometidas em encomendas")
   - ATENÇÃO: committed() pode não estar acessível se DEMAND_BACKEND não configurado.
     Nesse caso, skip V1 (graceful — sem backend = sem validação de holds).

   V2 — Validar insumos compartilhados:
   - Calcular o consumo de insumos desta WO com a nova quantidade:
     coefficient_new = quantity / recipe.batch_size
     Para cada RecipeItem: needed_new = ri.quantity * coefficient_new
   - Calcular o consumo TOTAL de TODAS as outras WOs OPEN na mesma data que
     usam os mesmos insumos (via BOM):
     other_wos = WorkOrder.objects.filter(
       status=OPEN, scheduled_date=order.scheduled_date
     ).exclude(pk=order.pk).select_related("recipe").prefetch_related("recipe__items")
     Para cada other_wo, para cada RecipeItem: somar consumo por input_ref
   - Para cada insumo: total_needed = own_new + others_existing
   - Verificar disponível via InventoryProtocol.available() ou StockQueries.available()
   - Se total_needed > available para qualquer insumo:
     raise CraftError("INSUFFICIENT_MATERIALS",
                       shortages=[{"sku": ref, "needed": total, "available": avail}])
   - ATENÇÃO: Se INVENTORY_BACKEND não configurado, skip V2 (graceful).
   - ATENÇÃO: Usar mesma lógica de coefficient = qty / batch_size do needs().

   V3 — Quantidade zero:
   - Se quantity == 0: ao invés de ajustar, chamar cls.void(order, reason="Remanejo: zerado")
   - Retornar o resultado de void() ao invés de continuar adjust()

3. Proteção warn+confirm para ajuste de WO de insumo (pré-preparo):
   - Se a WO sendo ajustada é de um insumo (output_ref usado como input_ref
     em outras receitas), verificar se reduzir afeta WOs dependentes.
   - Calcular déficit: quanto falta para WOs dependentes após redução.
   - Se force=False (default) e há déficit:
     raise CraftError("DOWNSTREAM_DEFICIT",
                       deficit=[{"wo_code": ..., "sku": ..., "shortage": ...}],
                       message="Insumo insuficiente para produção planejada")
   - Se force=True: permitir, log warning.
   - Adicionar parâmetro force=False ao adjust().

4. Em exceptions.py: Adicionar códigos de erro se não existirem:
   - COMMITTED_HOLDS
   - INSUFFICIENT_MATERIALS
   - DOWNSTREAM_DEFICIT

5. Testes (em tests/ do craftsman):
   - test_adjust_below_committed_holds: qty < holds → CraftError
   - test_adjust_exceeds_shared_ingredient: total > disponível → CraftError
   - test_adjust_within_limits: remanejo válido → OK
   - test_adjust_to_zero_voids: qty=0 → void()
   - test_adjust_downstream_deficit_blocked: reduz insumo → CraftError sem force
   - test_adjust_downstream_deficit_forced: reduz insumo com force=True → OK + warning
   - test_adjust_no_backend_skips_validation: sem INVENTORY_BACKEND → adjust sem V1/V2

6. Rodar make test (todos — inclui craftsman).

REGRAS:
- Alterações APENAS em packages/craftsman/.
- Backward compatible: adjust() sem novos params tem mesmo comportamento
  (V1/V2 só ativam se backends estão configurados).
- Sem novo status. Sem migração. Apenas lógica de validação no adjust() existente.
- Graceful: se backends não configurados, validações são skipped.
```

---

## WP-A9: Seed com Dados Realistas

```
Leia o plano docs/plans/AVAILABILITY-PLAN.md (seção WP-A9).

PRÉ-REQUISITO: WP-A7 e WP-A8 já executados.

CONTEXTO:
O seed atual cria apenas 7 dias de histórico de pedidos, sem soldout_at, sem
waste, sem sazonalidade. Isso faz com que craft.suggest() não tenha dados
suficientes para funcionar corretamente (precisa de 28+ dias).

ARQUIVOS:
- framework/shopman/management/commands/seed.py:
  - _seed_orders() (~1253-1377): cria pedidos históricos
  - _seed_shop() ou equivalente: configura Shop.defaults
  - _seed_stock() (~703-770): estoque inicial

TAREFAS:
1. Leia seed.py completamente, especialmente _seed_orders() e _seed_shop().

2. Expandir histórico de pedidos para 35 dias (5 semanas):
   - Manter a lógica de pedidos aleatórios, mas para 35 dias ao invés de 7.
   - Variar quantidades por dia da semana:
     - Seg-Qui: base normal
     - Sex-Sáb: base × 1.3 (alta demanda)
     - Dom: base × 0.7 (menor demanda)
   - Variar por "estação" simulada (usar mês atual do sistema):
     - hot months: × 1.1 para itens frios (sucos, saladas)
     - cold months: × 1.2 para itens quentes (sopas, pães)
     - Pode ser simples: ajustar proporcionalmente sem complicar demais.

3. Adicionar waste a alguns dias:
   - 20-30% dos dias devem ter waste > 0 para alguns SKUs
   - waste = unidades produzidas mas não vendidas
   - Criar WorkOrderItems com kind="waste" para esses dias
   - Proporção realista: 5-15% do produzido como waste

4. Adicionar soldout_at a alguns dias:
   - 10-15% dos dias, 1-2 SKUs esgotaram antes do fim do expediente
   - Se o OrderingDemandBackend.history() já suporta soldout_at: popular
   - Se não: verificar se WP-A7 implementou isso. Se não, skip e anotar TODO.

5. Criar WorkOrders históricas com finished_at:
   - Para cada dia no histórico, criar WOs com status=DONE e finished_at
   - Horários típicos: pães 05:30-07:00, confeitaria 09:00-11:00
   - Isso alimenta o sistema de pickup slots (median finish times)

6. Popular Shop.defaults com todas as configs:
   ```python
   shop.defaults.update({
       "max_preorder_days": 30,
       "closed_dates": [
           {"date": "2026-12-25", "label": "Natal"},
           {"date": "2026-12-31", "label": "Réveillon"},
           {"date": "2026-01-01", "label": "Confraternização Universal"},
       ],
       "seasons": {
           "hot": [10, 11, 12, 1, 2, 3],
           "mild": [4, 5, 9],
           "cold": [6, 7, 8],
       },
       "high_demand_multiplier": "1.2",
       "safety_stock_percent": "0.20",
       # pickup_slots e pickup_slot_config já devem existir, manter
   })
   ```

7. Garantir que Shop.opening_hours está populado:
   ```python
   shop.opening_hours = {
       "tuesday": {"open": "07:00", "close": "19:00"},
       "wednesday": {"open": "07:00", "close": "19:00"},
       "thursday": {"open": "07:00", "close": "19:00"},
       "friday": {"open": "07:00", "close": "19:00"},
       "saturday": {"open": "07:00", "close": "19:00"},
       "sunday": {"open": "07:00", "close": "13:00"},
       # monday: fechado (boulangerie típica)
   }
   ```

8. Rodar make seed && make test-framework.

REGRAS:
- Seed deve ser idempotente (rodar múltiplas vezes sem duplicar).
- Dados devem ser realistas para uma boulangerie.
- Não inventar SKUs novos — usar os existentes no seed.
- Manter _seed_stock_alerts() e outros seeders existentes.
```

---

## Instrução para Iniciar

Para começar a implementação em uma nova sessão do Claude Code:

```
Leia docs/plans/AVAILABILITY-PLAN.md e docs/plans/AVAILABILITY-PROMPTS.md.

Vamos executar o plano AVAILABILITY na seguinte ordem:

LOTE 1 (paralelo): WP-A1, WP-A4, WP-A6
LOTE 2 (sequencial após lote 1): WP-A2, WP-A3, WP-A5
LOTE 3 (paralelo): WP-A7, WP-A8
LOTE 4 (final): WP-A9

Comece pelo LOTE 1. Execute WP-A1 primeiro (é o mais crítico — violação ativa).
O prompt completo para WP-A1 está em AVAILABILITY-PROMPTS.md.

Após cada WP: rode make test-framework (ou make test para WPs de packages/).
Após completar cada WP: marque como concluído no AVAILABILITY-PLAN.md
(adicionar ✅ ao título do WP).

Convenções do projeto: leia CLAUDE.md. Core (packages/) é sagrado — não alterar
sem necessidade comprovada. Zero resíduos em renames. Ref not code. Centavos com _q.
```
