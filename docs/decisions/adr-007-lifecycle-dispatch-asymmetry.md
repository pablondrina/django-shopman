# ADR-007: Dois padrões de dispatch de lifecycle — por quê

**Status:** Aceito
**Data:** 2026-04-15
**Contexto:** Coexistência de `shopman/shop/lifecycle.py` (dict de fases) e `shopman/shop/production_lifecycle.py` (Strategy com herança)

---

## Contexto

O orquestrador coordena dois ciclos de vida distintos:

1. **Order** — pedido do cliente. Coordenado por `shopman/shop/lifecycle.py` via um dicionário `_PHASE_HANDLERS` que mapeia nome da fase → função. `dispatch(order, phase)` resolve `ChannelConfig` e chama a função correspondente. Invariante [`test_invariants.TestNoFlowClassesInLifecycle`](../../shopman/shop/tests/test_invariants.py) proíbe qualquer classe `*Flow*` neste arquivo.

2. **WorkOrder** (produção) — coordenado por `shopman/shop/production_lifecycle.py` via um registry (`@production_flow("standard")`) de classes `BaseProductionFlow` (`StandardFlow`, `ForecastFlow`, `SubcontractFlow`), selecionadas por `recipe.meta["production_flow"]`.

Um leitor que passa pelos dois arquivos razoavelmente suspeita de duplicação: *"são dois mecanismos de dispatch de ciclo de vida coabitando o mesmo orquestrador — por que não unificar?"*

Esta ADR responde: **porque as duas formas de variação são estruturalmente diferentes, e cada abstração casa com a forma da sua.**

## Decisão

O orquestrador mantém dois padrões de dispatch. Cada um é a abstração correta para o tipo de variação que o seu domínio exibe.

### Order: variação paramétrica → dict de fases

Order tem **uma única receita de comportamento** e **10 fases fixas** (`on_commit`, `on_confirmed`, `on_paid`, `on_preparing`, `on_ready`, `on_dispatched`, `on_delivered`, `on_completed`, `on_cancelled`, `on_returned`). Todos os canais de venda compartilham a mesma máquina de estados `Order.Status` e a mesma sequência de fases.

A variação entre canais é **paramétrica e ortogonal**:

- `config.payment.timing` ∈ `{external, at_commit, post_commit}`
- `config.fulfillment.timing` ∈ `{external, at_commit, post_commit}`
- `config.confirmation.mode` ∈ `{immediate, auto_confirm, auto_cancel, manual}`
- `config.stock.check_on_commit` ∈ `{true, false}`
- etc.

As combinações plausíveis são o produto cartesiano dessas dimensões. Nenhuma dessas combinações constitui um "tipo" no sentido de OO — um canal `storefront` (post_commit, post_commit, auto_confirm) e um canal iFood (external, external, immediate) não são subtipos de nada; são configurações.

A abstração que casa é o `dict` de fases:

```python
_PHASE_HANDLERS = {
    "on_commit": _on_commit,
    "on_confirmed": _on_confirmed,
    ...
}

def dispatch(order, phase):
    config = ChannelConfig.for_channel(order.channel_ref)
    _PHASE_HANDLERS[phase](order, config)
```

Cada função de fase lê `config` e decide: `if config.payment.timing == "at_commit": payment.initiate(order)`. Clarividente, sem polimorfismo, sem herança, sem registry dinâmico. O invariante arquitetural bloqueia qualquer regressão para Flow classes.

### WorkOrder: variação estrutural → Strategy com herança

WorkOrder tem **fluxos categoricamente distintos**, selecionados por `recipe.meta["production_flow"]`:

- `standard` — plano → produzir → finalizar, emite bens no finish
- `forecast` — mesmo pipeline, mas com política de conferência extra no finish (herda de `StandardFlow`)
- `subcontract` — tem operação terceirizada no meio, notificações com chaves distintas, e é candidato natural a ganhar fases próprias no futuro (`on_sent_to_subcontractor`, `on_returned_from_subcontractor`)

A variação não é "ligado/desligado de um parâmetro" — é "algoritmo diferente, com potencial de diferentes fases". Herança (`ForecastFlow(StandardFlow)`) expressa "igual a standard, exceto em um hook".

A abstração que casa é Strategy:

```python
@production_flow("standard")
class StandardFlow(BaseProductionFlow):
    def on_planned(self, wo): ...
    def on_finished(self, wo): ...

@production_flow("subcontract")
class SubcontractFlow(BaseProductionFlow):
    ...

def dispatch_production(work_order, phase):
    flow = get_production_flow(work_order.recipe)
    getattr(flow, phase)(work_order)
```

Forçar isso num `dict` achataria a herança (`ForecastFlow` teria que copiar `StandardFlow` inteiro) e dificultaria a adição de uma quarta variedade de flow — cada nova adição exigiria mexer num switch central.

## O teste diagnóstico

Quando usar cada padrão:

| Forma da variação | Sinal | Abstração |
|---|---|---|
| **Paramétrica ortogonal** | variação é produto cartesiano de flags/enums independentes; todos os "tipos" compartilham a mesma máquina de estados e as mesmas fases | `dict` de fases + config-driven |
| **Estrutural categórica** | variação é seleção de um tipo fechado; tipos podem ter fases próprias; herança "igual a X, exceto…" é natural | Strategy com registry + herança |

Os sinais de alerta que obrigariam migrar de um padrão para o outro:

**Order → Strategy (hoje não acontece):**
- Uma fase passa a ter `if channel_type == "marketplace": … elif channel_type == "ifood": …` (taxonomia vazando para dentro da fase).
- Um canal introduz uma fase que nenhum outro canal tem (ex.: `on_courier_assigned`).
- `ChannelConfig` cresce acima de ~12 campos por aspecto para emular polimorfismo.

**Production → dict-driven (hoje não acontece, mas vale monitorar):**
- Se após um ano `SubcontractFlow` ainda diferir de `StandardFlow` apenas em prefixos de string e nenhum flow novo surgiu, a Strategy está over-dressed — vale introduzir uma `ProductionConfig` simétrica a `ChannelConfig` e achatar.

Em ambos os casos a regra é a mesma: **a abstração tem que casar com a forma real da variação. Quando deixa de casar, refatora.**

## Consequências

### Positivas

- **Cada domínio usa a abstração certa para sua forma de variação.** Order não paga o custo de classes combinatórias (3×3×3 seria absurdo). Production está preparado para divergência estrutural.
- **Os dois arquivos são pequenos e legíveis**. `lifecycle.py` é uma tabela de 10 funções; `production_lifecycle.py` é 3 classes com 4 métodos cada.
- **Invariante arquitetural (`test_invariants.py` #4)** ancora a regra para Order — Flow classes em `lifecycle.py` quebram o build.

### Negativas

- **Leitor desavisado suspeita de duplicação.** Ler os dois arquivos em sequência sugere redundância que não existe. Esta ADR é a mitigação documental.
- **Assimetria pede consciência.** Contribuidor que adiciona uma terceira máquina de estados (ex.: lifecycle de `Directive`) precisa escolher deliberadamente qual padrão usar — não há "o jeito do projeto", há dois, e a escolha é diagnóstica.

### Mitigações

- Esta ADR existe.
- A tabela diagnóstica acima vai para `docs/guides/lifecycle.md` como referência rápida.
- Se um terceiro ciclo de vida for adicionado, uma nota no PR deve referenciar esta ADR e justificar a escolha.

## Alternativas consideradas

### A. Unificar tudo em Strategy

Rejeitada. Force 27 classes combinatórias para Order (ou clusters arbitrários em "famílias de canais" que não refletem nada no domínio). Perde a clareza do `dict` e rompe o invariante existente.

### B. Unificar tudo em dict-driven

Rejeitada. Force `ForecastFlow` a duplicar `StandardFlow`, perde herança como forma natural de expressar "igual a X, exceto…". Dificulta adicionar um quarto flow sem mexer num switch central.

### C. Um único mecanismo polimórfico que aceita os dois

Considerada e rejeitada. Um hipotético `dispatch(entity, phase)` genérico que resolve tanto `ChannelConfig` quanto `production_flow` da receita acumularia lógica de detecção de tipo, e a simplicidade dos dois arquivos atuais se perderia.

## Referências

- [`shopman/shop/lifecycle.py`](../../shopman/shop/lifecycle.py) — dispatch de Order
- [`shopman/shop/production_lifecycle.py`](../../shopman/shop/production_lifecycle.py) — dispatch de WorkOrder
- [`shopman/shop/config.py`](../../shopman/shop/config.py) — `ChannelConfig` (o "dado" que Order lê)
- [`shopman/shop/tests/test_invariants.py`](../../shopman/shop/tests/test_invariants.py) — invariante #4 ancora o padrão de Order
- ADR-001: Protocol/Adapter para variação real
- ADR-005: orquestrador como centro de coordenação
- ADR-006: semântica de `Order.Status`
