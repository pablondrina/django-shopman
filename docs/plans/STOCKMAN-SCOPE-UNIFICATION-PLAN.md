# STOCKMAN-SCOPE-UNIFICATION-PLAN

**Status:** draft aprovado em 2026-04-18. Plano isolado, executado por sessão paralela.

**Relação com outros planos:** peer do [AVAILABILITY-PLAN](AVAILABILITY-PLAN.md) — **pré-requisito** para que vários WPs daquele plano funcionem de verdade. Deve concluir antes de WP-AV-04 avançar.

**Escopo:** unificar o conceito de "quais quants são elegíveis para um SKU × canal × data" em **um único ponto de verdade** no Stockman, eliminando a divergência atual entre `availability_for_sku()` (usada pela `check()`) e `_find_quant_for_hold()` (usada pela `stock.hold()`). Simultaneamente, ativar a regra de negócio que exclui produtos D-1 (posição `ontem`) dos canais remotos.

---

## 1. Resumo executivo

Hoje o Stockman tem **dois filtros diferentes** para decidir quais quants "pertencem" a um SKU/canal/data. O resultado é que:

- `availability.check(sku, qty)` reporta `available_qty = 52` (soma canal-aware).
- `availability.reserve(sku, 52)` tenta criar o hold e só alcança `30` (soma hold-aware, mais restritiva).
- Cliente vê "Apenas 52 disponíveis" no modal, clica aceitar, o servidor retorna 422 (shortage), UI faz nada.

Isso é **bug real**, estrutural, afeta qualquer SKU com `shelf_life_days` curto + estoque `target_date=None` antigo — padrão de qualquer padaria.

**Solução adotada (Opção C do diagnóstico):** criar uma função canônica `quants_eligible_for(sku, *, channel_ref, target_date)` em Stockman e fazer AMBAS as funções (availability e hold) consumirem-na. Divergência futura fica impossível por construção.

**Regra de negócio a encodar no processo:** produtos em posição `ontem` (D-1) **não aparecem em canais remotos** (`web`, `delivery`, `whatsapp`, `ifood`). Só staff via POS (`balcao`) pode vendê-los. Hoje o sistema suporta isso via `ChannelConfig.stock.allowed_positions` mas NÃO está configurado — remote channels veem `ontem` por default.

---

## 2. Evidência do bug (reprodução)

### 2.1 Setup

Dados reais no dev (instância Nelson Boulangerie) para BAGUETE:

| Quant | Position | Target | Qty | Saleable | Notas |
|---|---|---|---|---|---|
| 51 | vitrine | None | 25 | ✓ | Estoque fresco de hoje |
| 83 | ontem | None | 27 | ✓ | D-1 — não deveria ser visível a cliente |
| 89 | — | 2026-04-17 | 2 | — | Possivelmente lixo acumulado |
| 93 | — | 2026-04-18 | 30 | — | Materialização de hoje |

### 2.2 Comando de reprodução

```bash
.venv/bin/python -c "
import django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); django.setup()
from decimal import Decimal
from shopman.shop.services import availability
from shopman.stockman import Hold
from shopman.stockman.models.enums import HoldStatus
Hold.objects.filter(sku='BAGUETE').update(status=HoldStatus.RELEASED)
c = availability.check('BAGUETE', Decimal('52'), channel_ref='web')
print('CHECK:', c['ok'], 'avail=', c['available_qty'])
r = availability.reserve('BAGUETE', Decimal('52'), session_key='DEMO', channel_ref='web')
print('RESERVE:', r['ok'], 'avail=', r['available_qty'])
Hold.objects.filter(sku='BAGUETE').update(status=HoldStatus.RELEASED)
"
```

### 2.3 Output esperado (comportamento atual, bugado)

```
CHECK: True avail= 52.000
RESERVE: False avail= 30
```

`check` diz que 52 está promissível; `reserve` só consegue 30. Inconsistência.

### 2.4 Critério de saída deste plano

Mesmo comando deve devolver:

```
CHECK: True avail= 25
RESERVE: True avail= 25
```

(25 = só vitrine; ontem excluído; planned = hoje, varia por cenário.)

---

## 3. Root cause técnico

### 3.1 Caminho `check()` — canal-aware

`shopman.shop.services.availability.check()` → `decide()` → `adapter.get_promise_decision()` → [`packages/stockman/shopman/stockman/services/availability.py::availability_for_sku`](../../packages/stockman/shopman/stockman/services/availability.py).

Filtragem de quants:
- `Quant.objects.filter(sku=sku, _quantity__gt=0)`
- `target_date IS NULL OR target_date <= today` (permissivo)
- `position__ref IN allowed_positions` (se canal setou) — **default None = todas**
- Remove quants de `Batch` expirado

Bucketing por `position.is_saleable`:
- position saleable + não-future → `ready`
- position not-saleable ou kind=process → `in_production`
- is_future → `planned`
- batch=D-1 → `d1`

`total_promisable = ready - held_ready - safety_margin` (se `stock_only`), ou variantes pra `planned_ok` e `demand_ok`.

**Não aplica `shelf_life_days`.**

### 3.2 Caminho `stock.hold()` — não canal-aware, aplica shelflife

[`packages/stockman/shopman/stockman/services/holds.py::StockHolds.hold`](../../packages/stockman/shopman/stockman/services/holds.py) chama `_find_quant_for_hold(sku, product, target_date, qty)`.

Filtragem de quants:
- `Quant.objects.filter(sku=sku)`
- **`filter_valid_quants(quants, product, target_date)`** ([shelflife.py:48](../../packages/stockman/shopman/stockman/shelflife.py)):
  - Se `product.shelf_life_days` não é None: filtra quants cuja validade caiu fora da janela `[today - shelflife, target_date]`.
  - Sem isso: apenas `target_date IS NULL OR target_date <= target_date_param`.
- **NÃO filtra por `allowed_positions`** — o hold vê posições que o canal exclui.
- **NÃO filtra por `position.is_saleable`** — pode holdar em posição não-vendável.

Depois itera por `created_at` (FIFO) buscando UM quant com `available >= qty`.

### 3.3 Consequência da divergência

Para BAGUETE (shelf_life_days curto, ex.: 1):
- `check` com canal web (sem allowed_positions override): conta `ready = Quant 51 (vitrine, 25) + Quant 83 (ontem, 27) = 52`. Retorna `total_promisable = 52`.
- `_find_quant_for_hold` com shelflife filter: Quants 51 e 83 (`target_date=None`) são filtrados por `created_at >= today - 1` → **excluídos se criados antes disso**. Sobram só Quants 89 e 93 (target dentro da janela).
- Binary search em `_reserve_across_quants` consegue no máximo `Quant 93 (30) + Quant 89 (2) = 32` teórico, e em prática só `30` por granularidade do halving.

Inconsistência = bug.

---

## 4. Solução: Opção C — função canônica

Criar **um único lugar** que define "quais quants estão elegíveis pra este SKU × canal × data". Ambos `availability_for_sku` e `_find_quant_for_hold` consomem-na.

### 4.1 Assinatura proposta

```python
# packages/stockman/shopman/stockman/services/scope.py (NOVO módulo)

def quants_eligible_for(
    sku: str,
    *,
    channel_ref: str | None = None,
    target_date: date | None = None,
    include_reserved: bool = True,
) -> QuerySet[Quant]:
    """Canonical queryset of quants a caller may consider for this SKU, channel and date.

    Applies, in order:
    1. ``sku`` match + ``_quantity > 0``
    2. ``target_date`` gate (no future quants beyond target)
    3. Channel scope (``allowed_positions`` from ChannelConfig.stock)
    4. Shelflife window (``product.shelf_life_days``) — quants whose validity
       sits outside ``[target_date - shelflife, target_date]`` are excluded
    5. Batch expiry (expired batch refs filtered out)

    Both availability reads (check) and physical holds (reserve) consume
    this queryset — impossible for the two to disagree about which quants
    are "ours" to work with.
    """
```

### 4.2 Implementação

- Move o filtro de `filter_valid_quants` pra dentro dessa função (shelflife).
- Move o filtro de `allowed_positions` pra dentro dessa função (canal).
- Move o filtro de batch expirado pra dentro dessa função.
- Retorna QuerySet sem evaluar — callers aplicam bucketing ou FIFO por cima.

### 4.3 Refactor

**`availability_for_sku` / `availability_for_skus`**: substituir a query inicial de Quants por `quants_eligible_for(sku, channel_ref=?, target_date=?)`. O `channel_ref` precisa chegar até aqui (hoje só recebe `allowed_positions + safety_margin`); passar explícito ou recomputar via `availability_scope_for_channel`. Como esses métodos já recebem `allowed_positions`, pode-se adaptar: se o caller passar `allowed_positions`, usa esse; senão usa o canal. Manter backwards-compat.

**`_find_quant_for_hold`**: substituir `Quant.objects.filter(sku=sku)` + `filter_valid_quants` pela mesma chamada. `stock.hold` precisa receber `channel_ref` para passar. Propagar pela cadeia:

- `shopman.shop.adapters.stock.create_hold(channel_ref=...)` — adicionar parâmetro.
- `shopman.shop.services.availability.reserve` — já tem `channel_ref`, passa ao adapter.
- `shopman.stockman.services.holds.StockHolds.hold` — adicionar parâmetro.
- `_find_quant_for_hold` — adicionar parâmetro.

### 4.4 Remoção

Depois que tudo estiver passando pelo novo gate:
- `filter_valid_quants` pode ficar para uso legado em queries internas (ex.: `stock.available`) ou ser absorvida. Avaliar no momento.
- Callers que passavam `allowed_positions` explícito continuam funcionando (a nova função os respeita).

---

## 5. Regra de negócio: D-1 (posição "ontem") só acessível a staff

Hoje o sistema suporta a regra via `ChannelConfig.stock.allowed_positions`, mas **não está configurada**. Remote channels (`web`, `delivery`, `whatsapp`, `ifood`) veem `ontem` via default (`None = todas posições`).

### 5.1 Decisão fechada (Pablo, 2026-04-18)

- **Canais remotos** não ofertam produtos em posição `ontem`. Quantos com `position__ref='ontem'` são invisíveis a `check()` e `reserve()` nesses canais.
- **Canal `balcao`** (POS) e demais staff-facing veem `ontem` normalmente — é onde o operador vende o D-1 com markdown.
- **Gestor de pedidos (Unfold admin / operator UI)** também precisa poder incluir D-1 em pedidos manuais. A regra é "staff-facing channel = ok; remote channel = block".

### 5.2 Implementação

Configurar `allowed_positions` nos canais remotos. Opções:

**A)** Override por canal via `ChannelConfig.stock.allowed_positions = ['deposito', 'vitrine', 'producao']` (lista positiva, exclui `ontem` implicitamente).

**B)** Introduzir `ChannelConfig.stock.excluded_positions = ['ontem']` (lista negativa, mais simples).

Recomendo **B** — é uma linha por canal, não precisa repetir todas as posições válidas.

Requer:
- Campo novo no `ChannelConfig.stock` dataclass.
- Propagação em `availability_scope_for_channel` + `quants_eligible_for`.
- Configuração explícita em `remote()` preset de channel (`shopman.shop.config`).
- Confirmação de que `pos()` preset NÃO exclui nada.
- Teste que valida: `web` não vê `ontem`, `balcao` vê.

### 5.3 Verificação pré-execução

O agente deve confirmar, ANTES de alterar código:

- Existe doc em `docs/business-rules.md` (seção A.5) listando posições com `Vendável = sim` para `ontem`. Isso hoje reflete "operacionalmente vendável" — não "em qual canal aparece". Ajustar texto do doc pra deixar claro: `ontem` é vendável APENAS via staff; remote channels excluem.

---

## 6. Perguntas abertas para o agente paralelo

### 6.1 Shelf life: dias ou data de vencimento?

Hoje `product.shelf_life_days` é inteiro (dias). `Quant` não tem `expiry_date` próprio — a janela de validade é inferida de `target_date` ± `shelf_life_days`.

Pergunta: migrar para `expiry_date` em `Quant` seria mais honesto (data real de validade vs. aproximação)?

**Pendência:** Pablo ainda não decidiu. Se mudar de días → data, é mudança de schema no Stockman — escopo grande. **Sugestão**: ficar com `shelf_life_days` nesta rodada (semântica atual) e abrir plano separado se o refactor for aprovado depois.

### 6.2 Quant 89 (target no passado)

Quant 89 tem `target_date=2026-04-17` (hoje é 2026-04-18) com 2 unidades. Não materializado, não expirou, sem posição.

Pergunta: isso é lixo acumulado de testes, ou estado operacional válido (produção planejada que não virou materialização)?

**Passos para o agente:**
1. Grep por `Quant.objects.create` + `target_date` em código e fixtures para entender quando isso é esperado.
2. Consultar Craftsman: produção planejada que não foi realizada deixa lixo ou é limpa?
3. Se for lixo: script de cleanup em `management/commands/` ou migração de dados.
4. Se for estado válido: deixar como está, mas o filtro de `target_date <= today` em `quants_eligible_for` já remove do ciclo ativo.

---

## 7. Work Packages

### WP-SCOPE-01 — `quants_eligible_for` canônica

Criar `packages/stockman/shopman/stockman/services/scope.py` com a função descrita em §4.1. Sem callers ainda — apenas a função + testes unitários isolados cobrindo:
- Filtragem por canal (`allowed_positions`)
- Filtragem por shelflife
- Filtragem por batch expirado
- Filtragem por `target_date`
- Combinações de 2+

### WP-SCOPE-02 — Refactor `availability_for_sku` e `availability_for_skus`

Substituir query inicial por chamada a `quants_eligible_for`. Preservar bucketing (`ready`, `in_production`, `planned`, `d1`). Remover código duplicado de filtragem por batch expirado (agora centralizado).

Teste: comportamento idêntico ao anterior EXCETO quando shelflife agora filtra quants antes ignorados. Atualizar testes que dependiam do antigo output.

### WP-SCOPE-03 — Propagar `channel_ref` até `_find_quant_for_hold`

Adicionar parâmetro `channel_ref` na cadeia:
- `availability.reserve(..., channel_ref=...)` já tem
- `adapter.create_hold(..., channel_ref=...)` — **adicionar**
- `StockHolds.hold(..., channel_ref=...)` — **adicionar**
- `_find_quant_for_hold(..., channel_ref=...)` — **adicionar**

Dentro de `_find_quant_for_hold`, substituir `Quant.objects.filter(sku=sku) + filter_valid_quants(...)` por `quants_eligible_for(sku, channel_ref=channel_ref, target_date=target_date)`.

Teste: `check()` e `reserve()` agora devolvem o MESMO `available_qty` para um SKU+canal+qty dado.

### WP-SCOPE-04 — Configurar `allowed_positions` (ou `excluded_positions`) nos canais remotos

Preferência por **excluded_positions** (§5.2 opção B):
- Adicionar campo `excluded_positions: list[str]` em `ChannelConfig.stock` (dataclass em `shopman/shop/config.py`).
- `remote()` preset: `excluded_positions=['ontem']`.
- `pos()` preset: `excluded_positions=[]` (staff vê tudo).
- `marketplace()` preset: `excluded_positions=['ontem']` (iFood não recebe D-1).
- `availability_scope_for_channel` devolve também `excluded_positions`.
- `quants_eligible_for` aplica `.exclude(position__ref__in=excluded_positions)`.

Teste:
- `availability.check('BAGUETE', 1, channel_ref='web')` NÃO conta Quant 83 (`pos=ontem`).
- `availability.check('BAGUETE', 1, channel_ref='balcao')` CONTA Quant 83.
- `availability.reserve('BAGUETE', 1, channel_ref='web')` nunca cria hold em quant de `ontem`.

### WP-SCOPE-05 — E2E regression: modal diz N, aceitar N → 200

Teste integrado com `Client`:

1. Seed: produto com estoque fragmentado + shelflife + alguma stock em `ontem`.
2. `POST /cart/add/` com qty > total → 422 + modal mostra "Apenas N disponíveis".
3. Extrair N do HTML do modal.
4. `POST /cart/set-qty/` com qty=N → 200.
5. `GET /cart/` → linha com qty=N presente.

Trava o contrato: "modal nunca promete mais do que reserve consegue entregar".

### WP-SCOPE-06 — Investigar/limpar Quant 89 (lixo planejamento)

Conforme §6.2. Se confirmar lixo:
- Script idempotente em `management/commands/cleanup_stale_planning.py`: remove Quants com `target_date < today`, `position IS NULL`, sem holds ativos nem moves vinculados.
- Adicionar ao cronograma de manutenção (documentar).

### WP-SCOPE-07 — Doc + testes de regressão

Atualizar `docs/business-rules.md`:
- Seção A.5: tornar explícito que `ontem` é **staff-only** (remote channels excluem).
- Adicionar seção sobre o contrato `check() == reserve() available_qty`.

Rodar suíte completa: stockman + framework + todos packages. Zero regressão.

---

## 8. Critério de saída

1. Comando de repro em §2.2 retorna `CHECK == RESERVE` para qualquer SKU + canal.
2. `availability.check('BAGUETE', ?, channel_ref='web')` não inclui Quant em `pos=ontem`.
3. `availability.check('BAGUETE', ?, channel_ref='balcao')` inclui Quant em `pos=ontem`.
4. Suíte de testes completa passa (stockman 173, framework 1034, todos packages).
5. E2E do WP-SCOPE-05 verde.
6. Pergunta §6.1 (days vs date) documentada e decidida (ou deferida explicitamente).
7. Pergunta §6.2 (Quant 89) resolvida (lixo → cleanup; estado válido → documentado).

---

## 9. Coexistência com AVAILABILITY-PLAN

Este plano **não conflita** com AVAILABILITY-PLAN, mas tem dependência de ordem:

- AVAILABILITY-PLAN WP-AV-04 (PDP own-hold-aware) assume que `check()` e `reserve()` concordam. Se este plano não fechar antes, WP-AV-04 vai parecer quebrado mesmo sem regressão real.
- AVAILABILITY-PLAN WP-AV-14 (E2E cross-surface) depende de modal+accept funcionar no fluxo de Ajuste. Este plano conserta isso.

**Ordem recomendada**: STOCKMAN-SCOPE-UNIFICATION completo ANTES de seguir para WP-AV-04 do AVAILABILITY-PLAN.

---

## 10. Pre-flight para o agente cold-start

Antes de escrever qualquer código:

1. Ler [AVAILABILITY-PLAN.md](AVAILABILITY-PLAN.md) §1–§3 para entender o contexto maior.
2. Rodar comando de repro em §2.2 e confirmar saída bugada.
3. Ler:
   - [`packages/stockman/shopman/stockman/services/availability.py`](../../packages/stockman/shopman/stockman/services/availability.py) completo
   - [`packages/stockman/shopman/stockman/services/holds.py::StockHolds.hold`](../../packages/stockman/shopman/stockman/services/holds.py) + `_find_quant_for_hold`
   - [`packages/stockman/shopman/stockman/shelflife.py`](../../packages/stockman/shopman/stockman/shelflife.py)
   - [`shopman/shop/adapters/stock.py`](../../shopman/shop/adapters/stock.py)
   - [`shopman/shop/services/availability.py`](../../shopman/shop/services/availability.py) `reserve` + `_reserve_across_quants`
   - [`shopman/shop/config.py::Stock`](../../shopman/shop/config.py)
   - [`docs/business-rules.md`](../business-rules.md) seção A.5 (posições)
4. Confirmar que o fix de `release_hold → release_holds` (plural) já está aplicado em `shopman/shop/services/availability.py:534` — é um fix pré-requisito já feito em sessão anterior, não retrabalhar.
5. Responder Pablo sobre §6.1 e §6.2 antes de tocar código.

---

## 11. Memória associada

Gravar após conclusão (sucesso):

- `project_stockman_scope_unified.md` — "Scope de quants agora é canônico via `quants_eligible_for`; D-1 é staff-only por default em remote channels".
