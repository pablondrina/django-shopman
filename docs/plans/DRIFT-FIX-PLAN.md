# DRIFT-FIX-PLAN — Três correções críticas de drift entre camadas

**Contexto:** análise crítica em `docs/_inbox/django_shopman_analise_critica_atualizada_codigo.md`
identificou três pontos em que subdomínios amadurecidos não estão alinhados com o
framework orquestrador. Verificação no código confirmou os três como bugs reais:

1. **WP-DF-1** — Contrato adapter de pagamento está incompatível com `services/payment.py`
   (runtime-breaking na primeira chamada).
2. **WP-DF-2** — `flows.py` lê chaves planas de `channel.config` que não existem no
   schema, ignorando a `ChannelConfig` dataclass e seu cascade canal←loja←defaults.
3. **WP-DF-3** — Adoção de holds por SKU (não por quantidade) sangra estoque quando
   o carrinho tem múltiplas mutações.

Ordem de execução: **WP-DF-1 → WP-DF-2 → WP-DF-3**. São independentes, mas o #1
desbloqueia qualquer demo de e-commerce real e deve vir primeiro.

---

## WP-DF-1 — Unificar contrato dos adapters de pagamento

**Gravidade:** crítica. Bloqueia `RemoteFlow.on_confirmed → payment.initiate()`.

### Diagnóstico

`framework/shopman/services/payment.py` chama:

```python
intent = adapter.create_intent(
    amount_q=amount_q,
    currency="BRL",
    reference=order.ref,
    metadata={"method": method},
)
# depois acessa: intent.intent_id, intent.status, intent.client_secret,
#                intent.expires_at, intent.metadata
```

Os três adapters (`payment_mock.py`, `payment_stripe.py`, `payment_efi.py`) têm:

```python
def create_intent(order_ref: str, amount_q: int, method: str = "pix", **config) -> dict:
    ...
    return {"intent_ref": ..., "status": ..., "client_secret": ..., ...}
```

Incompatibilidades:

- `reference=` cai em `**config`; `order_ref` posicional falta → `TypeError`.
- Mesmo com chamada ajustada: retorno é `dict`, service acessa como objeto.
- `capture()` idem: service usa `result.success` / `result.transaction_id`, adapter
  retorna `dict`.
- Nome da chave de ID: service espera `intent_id`, adapter devolve `intent_ref`.

### Solução

Definir **DTOs tipados** (`@dataclass`) como contrato canônico dos adapters de
pagamento, expostos em `shopman.adapters.payment_types` (ou análogo dentro de
`framework/shopman/adapters/`). Todos os adapters passam a retornar instâncias dessas
dataclasses. O service passa a consumir por atributo, sem `.get()`.

**DTOs a criar** (esboço):

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class PaymentIntent:
    intent_ref: str            # ID canônico (alinhado com PaymentService.ref)
    status: str                # "pending" | "authorized" | "requires_action" | ...
    amount_q: int
    currency: str = "BRL"
    client_secret: str | None = None
    expires_at: datetime | None = None
    gateway_id: str | None = None
    metadata: dict = field(default_factory=dict)

@dataclass
class PaymentResult:
    success: bool
    transaction_id: str | None = None
    amount_q: int | None = None
    error_code: str | None = None
    message: str | None = None
```

**Assinatura canônica** (uniforme nos três adapters):

```python
def create_intent(
    *,
    order_ref: str,
    amount_q: int,
    currency: str = "BRL",
    method: str,
    metadata: dict | None = None,
    **config,
) -> PaymentIntent: ...

def capture(
    intent_ref: str,
    *,
    amount_q: int | None = None,
    **config,
) -> PaymentResult: ...

def refund(
    intent_ref: str,
    *,
    amount_q: int | None = None,
    reason: str = "",
    **config,
) -> PaymentResult: ...

def cancel(intent_ref: str, **config) -> PaymentResult: ...
```

Service adaptado: `reference=order.ref` vira `order_ref=order.ref`; acessos passam
a ser `intent.intent_ref` (renomear `intent_id` → `intent_ref` em `order.data["payment"]`
também, para alinhar com o core `payman`).

### Arquivos afetados

- `framework/shopman/adapters/payment_types.py` — **novo**: dataclasses `PaymentIntent`, `PaymentResult`.
- `framework/shopman/adapters/payment_mock.py` — retornar DTOs.
- `framework/shopman/adapters/payment_stripe.py` — retornar DTOs.
- `framework/shopman/adapters/payment_efi.py` — retornar DTOs.
- `framework/shopman/services/payment.py` — ajustar chamada e acessos; renomear
  `intent_id` → `intent_ref` na persistência em `order.data["payment"]`.
- `framework/shopman/webhooks/efi.py`, `webhooks/stripe.py` — auditar consumers de `order.data["payment"]["intent_id"]`.
- `framework/shopman/web/views/checkout.py` — idem.
- `framework/shopman/web/views/pedidos.py` — idem.
- Qualquer template/API que leia `order.data["payment"]["intent_id"]`.

### Testes obrigatórios

- `tests/test_payment_contract.py` — **novo**:
  - Exercita `adapter.create_intent` → `PaymentIntent` para mock/stripe/efi (mockando SDK).
  - Exercita `adapter.capture` → `PaymentResult`.
  - Garante que `services.payment.initiate(order)` roda fim-a-fim com adapter mock real
    e grava `order.data["payment"]["intent_ref"]`.
- `tests/test_flows.py` (novo ou adicionar): `WebFlow.on_confirmed` → `payment.initiate` → não explode.

### Convenções

- **Zero backward-compat aliases** (memória `feedback_zero_residuals`). Nada de
  `intent_id = intent_ref` property. Renomear a chave e atualizar todos os callers.
- **Zero gambiarras** (memória `feedback_zero_gambiarras`). Se um adapter tem
  complexidade de SDK, a dataclass é construída no adapter, não no service.

### Critério de conclusão

- [ ] DTOs definidos em `payment_types.py`.
- [ ] Três adapters retornam DTOs em todas as funções públicas (`create_intent`,
      `capture`, `refund`, `cancel`).
- [ ] `services/payment.py` consome por atributo, sem `.get()` em retorno de adapter.
- [ ] `order.data["payment"]` usa `intent_ref` (não `intent_id`).
- [ ] `grep -rn 'intent_id' framework/` retorna só ocorrências do core `payman` interno.
- [ ] `make test` verde.

---

## WP-DF-2 — Integrar `ChannelConfig` no orquestrador

**Gravidade:** alta. Configuração por canal é silenciosamente descartada.

### Diagnóstico

`framework/shopman/config.py` define `ChannelConfig` dataclass com:
- 7 sub-dataclasses tipadas (`Confirmation`, `Payment`, `Stock`, `Pipeline`, `Notifications`, `Rules`, `Flow`);
- método `from_dict()` com `_safe_init` filtrando campos desconhecidos;
- método `effective(channel)` com cascade canal←loja←defaults via `deep_merge`;
- método `validate()`.

`framework/shopman/flows.py:84-87` ignora tudo isso:

```python
def _channel_config(order, key: str, default=None):
    config = getattr(order.channel, "config", None) or {}
    return config.get(key, default)
```

E lê chaves que **não existem no schema**:

| `flows.py` lê | Schema diz | Resultado |
|---|---|---|
| `config["confirmation_mode"]` | `config["confirmation"]["mode"]` | sempre cai em default `"immediate"` |
| `config["confirmation_timeout"]` | `config["confirmation"]["timeout_minutes"]` | sempre cai em default `300` |
| `config["flow"]` como string | `config["flow"]` é dict `{transitions, ...}` | `_registry.get(dict, BaseFlow)` falha silencioso |

Impacto: qualquer canal configurado no admin com `confirmation.mode = "optimistic"`
continua rodando como `"immediate"`. Shop defaults nunca são aplicados.

### Solução

#### (a) Resolver ambiguidade do "flow"

O schema trata `flow` como customização de transições (dict). Mas `flows.py` precisa
de um **nome de classe** para resolver no `_registry`. São duas coisas distintas.
Separar:

- **Novo campo no model:** `Channel.flow = CharField(max_length=32, default="base")`.
  Identifica qual classe do registry (`BaseFlow`, `LocalFlow`, `WebFlow`, etc.).
- **`ChannelConfig.flow`** (dentro do JSONField `config`) continua sendo o sub-objeto
  de customização de transições. Namespaces distintos: `channel.flow` é o model field,
  `channel.config["flow"]` é a estrutura de transitions/terminal_statuses.

#### (b) Fazer `flows.py` usar `ChannelConfig.effective()`

```python
from shopman.config import ChannelConfig

def get_flow(order) -> BaseFlow:
    name = getattr(order.channel, "flow", None) or "base"
    cls = _registry.get(name, BaseFlow)
    return cls()

def _effective_config(order) -> ChannelConfig:
    return ChannelConfig.effective(order.channel)

class BaseFlow:
    def handle_confirmation(self, order):
        cfg = _effective_config(order).confirmation
        if cfg.mode == "immediate":
            order.transition_status(...)
        elif cfg.mode == "optimistic":
            expires_at = timezone.now() + timedelta(minutes=cfg.timeout_minutes)
            ...
```

Remover o helper `_channel_config(order, key, default)` — ele era a porta de entrada
do bug.

#### (c) Auditar outros consumidores de `order.channel.config`

```bash
grep -rn 'channel\.config\.' framework/shopman/ packages/
grep -rn '\.config\.get(' framework/shopman/services/ framework/shopman/handlers/
```

Todo consumer que lê `channel.config.get(...)` com chave semântica (não operacional)
deve passar a usar `ChannelConfig.effective(channel)` para herdar o cascade.

### Arquivos afetados

- `packages/omniman/shopman/omniman/models/channel.py` — adicionar `flow` field.
- `packages/omniman/shopman/omniman/migrations/` — nova migração.
- `framework/shopman/flows.py` — substituir `_channel_config` por `ChannelConfig.effective`.
- `framework/shopman/config.py` — `Flow` dataclass fica como está (transitions/terminal_statuses).
- `framework/shopman/admin/shop.py` (ou onde Channel é administrado) — expor `flow` no admin.
- `framework/shopman/management/commands/seed.py` (Nelson) — popular `flow` nos canais seed.
- Outros call sites descobertos na auditoria (b).

### Testes obrigatórios

- `tests/test_channel_config.py` — **novo ou expandir**:
  - Cascade defaults → shop → channel com `confirmation.mode` vindo de cada nível.
  - `ChannelConfig.effective(channel)` retorna cascade correto.
- `tests/test_flows_config.py` — **novo**:
  - `BaseFlow.handle_confirmation` respeita `confirmation.mode = "optimistic"` do config.
  - `BaseFlow.handle_confirmation` respeita `confirmation.timeout_minutes`.
  - `get_flow(order)` resolve `WebFlow` para `channel.flow = "web"`.
  - Canal sem `flow` cai em `BaseFlow`.

### Critério de conclusão

- [ ] `Channel.flow` adicionado + migração.
- [ ] `flows.py` não tem mais `_channel_config`; usa `ChannelConfig.effective(order.channel)`.
- [ ] Teste de cascade verde.
- [ ] Teste de confirmation modes (immediate/optimistic/manual) verde.
- [ ] `grep -rn '_channel_config' framework/` retorna zero.
- [ ] Auditoria de outros call sites completa e documentada no PR.
- [ ] `make test` verde.

---

## WP-DF-3 — Corrigir adoção de holds por quantidade

**Gravidade:** alta. Sangra estoque silenciosamente.

### Diagnóstico

Fluxo real (verificado em `web/cart.py:84-142` + `services/stock.py:208-222`):

1. Cliente adiciona SKU X qty 2 → `availability.reserve(delta=2)` → Hold A (qty=2, ref=session_key).
2. Cliente clica "adicionar 2" → `availability.reserve(delta=2)` → Hold B (qty=2, ref=session_key).
3. Carrinho consolida linha: `(X, qty=4)`. Dois holds (A, B) no Stockman.
4. Commit → `stock.hold(order)` → item (X, 4). `_pop_matching_hold` pop-a apenas Hold A.
5. `stock.py:94-96`: Hold B vai pra `leftover_ids` e é **liberado**.
6. Pedido com qty=4 adota reserva de qty=2. **Sangra 2 unidades.**

Pior ainda:
- `update_qty` (`cart.py:145-154`) e `remove_item` (`cart.py:156-166`) **não mexem nos holds**.
  Stepper de quantidade fica completamente desacoplado da reserva.

### Solução

Duas peças independentes:

#### (a) Adotar holds por quantidade, não por SKU-first

Reescrever `_load_session_holds` + `_pop_matching_hold` para casar quantidade agregada:

```python
def _load_session_holds(session_key: str) -> dict[str, list[tuple[str, Decimal]]]:
    """Index session holds by SKU, preserving (hold_id, qty) pairs."""
    from shopman.stockman.models import Hold
    from shopman.stockman.models.enums import HoldStatus

    holds = Hold.objects.filter(
        metadata__reference=session_key,
        status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
    )
    indexed: dict[str, list[tuple[str, Decimal]]] = {}
    for h in holds:
        indexed.setdefault(h.sku, []).append((h.hold_id, h.qty))
    return indexed


def _adopt_holds_for_qty(
    indexed: dict[str, list[tuple[str, Decimal]]],
    sku: str,
    required_qty: Decimal,
) -> tuple[list[str], Decimal]:
    """Consume session holds for `sku` until `required_qty` is met.

    Returns (adopted_hold_ids, unmet_qty). If session holds fall short,
    caller creates a fresh hold via the adapter for the remainder.
    """
    bucket = indexed.get(sku, [])
    adopted: list[str] = []
    remaining = required_qty
    while bucket and remaining > 0:
        hold_id, hold_qty = bucket.pop(0)
        adopted.append(hold_id)
        remaining -= hold_qty
    return adopted, max(remaining, Decimal("0"))
```

E `stock.hold(order)` passa a adotar uma lista de hold_ids por item, possivelmente
complementando com um fresh hold do adapter para o `unmet_qty`.

**Caso over-adoption** (adotou holds que somam mais que o necessário): aceitar — o
primeiro commit consolida tudo em `order.data["hold_ids"]`, depois `fulfill_hold`
dá baixa normal. Alternativa seria split do último hold, mas isso exige API no
Stockman e complica desnecessariamente. A diferença é absorvida.

#### (b) Reconciliar holds em `update_qty` / `remove_item`

Adicionar um service `availability.reconcile(session_key, sku, new_qty)` que:
- Carrega holds ativos daquela session+SKU.
- Se `new_qty > current_hold_qty`: cria hold adicional pelo delta.
- Se `new_qty < current_hold_qty`: libera holds até cobrir a diferença (FIFO).
- Se `new_qty == 0`: libera todos os holds do SKU.

`CartService.update_qty` e `CartService.remove_item` passam a chamar `reconcile`
antes de `ModifyService.modify_session`. Se `reconcile` não consegue criar hold
adicional (estoque esgotou entre cart e ajuste), devolve `CartUnavailableError`
como `add_item` já faz.

### Arquivos afetados

- `framework/shopman/services/stock.py` — reescrever `_load_session_holds` e
  `_pop_matching_hold` → `_adopt_holds_for_qty`; ajustar `hold(order)`.
- `framework/shopman/services/availability.py` — novo verbo `reconcile()`.
- `framework/shopman/web/cart.py` — `update_qty` e `remove_item` chamam `reconcile`.
- `framework/shopman/tests/test_services.py` — expandir.
- `framework/shopman/tests/test_concurrent_checkout.py` — exercitar mutação repetida.

### Testes obrigatórios

- `tests/test_hold_adoption.py` — **novo**:
  - **add X twice**: add(X, 2) + add(X, 2) → commit → pedido adota dois holds
    totalizando qty=4. `order.data["hold_ids"]` tem dois entries (ou um consolidado,
    dependendo da decisão final).
  - **add then update up**: add(X, 2) + update(X, 5) → commit → reserva total=5.
  - **add then update down**: add(X, 5) + update(X, 2) → commit → reserva total=2;
    holds excedentes foram liberados em `update_qty`.
  - **add then remove**: add(X, 5) + remove(X) → commit sem item X → zero holds.
  - **reconcile shortage**: add(X, 5) + update(X, 999) quando só há 10 → erro.
  - **leftover release**: add(X, 2) + add(Y, 2) + remove(Y) + commit → Hold Y
    liberado em `remove_item`, não em leftover.

### Critério de conclusão

- [ ] `_pop_matching_hold` eliminado; `_adopt_holds_for_qty` no lugar.
- [ ] `availability.reconcile` implementado.
- [ ] `CartService.update_qty` / `remove_item` chamam `reconcile`.
- [ ] Todos os testes acima passando.
- [ ] Teste de invariante: "soma de `order.data['hold_ids'][*]['qty']` ≥ soma de
  `order.snapshot['items'][*]['qty']` por SKU" (com bundle expansion).
- [ ] `make test` verde.

---

## Ordem de execução e PRs

| WP | Depende de | PR |
|---|---|---|
| WP-DF-1 | — | PR isolado. Desbloqueia pagamento digital. |
| WP-DF-2 | — | PR isolado. Pode rodar em paralelo com WP-DF-1. |
| WP-DF-3 | — | PR isolado. Pode rodar em paralelo. |

Nenhum dos três depende dos outros. Se houver capacidade, podem rodar em paralelo
em branches separados, mas recomendo serializar para facilitar revisão.

## Notas de princípio

- **Respeitar o core** (memória `feedback_respect_core_no_reinvent`): os três fixes
  são no framework orquestrador, não nos packages. O core `payman` está correto, o
  core `stockman` está correto, o core `omniman` está correto. É o glue code que
  ficou pra trás.
- **Zero resíduos** (memória `feedback_zero_residuals`): renomear `intent_id` →
  `intent_ref` em tudo. Não deixar alias.
- **Sem inventar features** (memória `feedback_no_invented_features`): o plano
  resolve os três bugs identificados. Nenhuma "melhoria" oportunista anexada.
