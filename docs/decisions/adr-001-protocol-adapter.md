# ADR-001: Cores independentes, framework integrador, Protocol/Adapter para substituição

**Status:** Aceito
**Data:** 2026-04-14 (reescrita)
**Supera:** versão original de 2025-01-20

---

## Contexto

A suite Shopman é composta por oito core apps pip-instaláveis em `packages/`
(`utils`, `offerman`, `stockman`, `craftsman`, `orderman`, `guestman`, `doorman`,
`payman`) e uma aplicação integradora em `framework/shopman/` que compõe esses
cores em um produto utilizável.

Dois mecanismos convivem no código:

1. Services do framework que importam diretamente services de múltiplos cores
   (`CheckoutService` chama `CatalogService.price()`, `StockService.hold()`,
   `CustomerService.identify()`).
2. Protocols e Adapters que abstraem pontos de integração — `PaymentBackend`,
   `FiscalBackend`, `NotificationBackend`, `StockBackend` — cada um com múltiplas
   implementações selecionadas via settings.

A pergunta arquitetural é: **quando usar qual?** A versão original desta ADR
(2025-01-20) dizia "toda comunicação entre apps usa Protocol/Adapter". Isso
envelheceu: não descreve o que o código realmente faz nem por quê. Esta
reescrita fixa a lei atual na forma positiva.

## Decisão

### 1. Cada core é uma biblioteca de domínio completa

Um core em `packages/` responde uma pergunta canônica de negócio e a resolve
inteiramente dentro do seu próprio código. Ele expõe services públicos, modela
suas entidades, define seus sinais e emite seus eventos. É testável e
instalável isoladamente. Nenhum core importa outro core — a única dependência
permitida é `shopman.utils`.

```python
# packages/stockman/shopman/stockman/services.py
class StockService:
    @classmethod
    def hold(cls, sku: str, quantity: Decimal, ...) -> Hold: ...

# packages/orderman/shopman/orderman/services/commit.py
class CommitService:
    # não importa nada de outros cores além de utils
    ...
```

### 2. O framework importa e compõe

`framework/shopman/` é o único lugar onde services de múltiplos cores se
encontram. Ele importa cada core diretamente, sem intermediários, e coordena
processos de negócio cross-domain em `services/`, `lifecycle.py`, `handlers/`
e `rules/`.

```python
# framework/shopman/services/checkout.py
from shopman.offerman.services import CatalogService
from shopman.stockman.services import StockService
from shopman.guestman.services import CustomerService

class CheckoutService:
    def commit(self, session) -> Order:
        price = CatalogService.price(sku, channel)
        hold = StockService.hold(sku, qty)
        customer = CustomerService.identify(session.data["customer"])
        ...
```

Não há Protocol nesse caminho. Os cores são dependências conhecidas e estáveis
do framework — não há razão para abstrair.

### 3. Protocol/Adapter isola pontos de variação real

Usa-se `typing.Protocol` com `@runtime_checkable` + Adapter apenas quando a
implementação **precisa** variar. Os casos reais hoje:

| Protocol | Implementações | Razão |
|---|---|---|
| `PaymentBackend` | `MockPaymentBackend`, `StripeBackend`, `EfiPixBackend` | Troca de gateway por método/ambiente |
| `FiscalBackend` | `MockFiscalBackend`, `FocusBackend` | Troca de emissor fiscal |
| `AccountingBackend` | `MockAccountingBackend`, `ContaazulBackend` | Troca de ERP contábil |
| `NotificationBackend` | `ConsoleBackend`, `ManychatBackend`, `EmailBackend`, `SmsBackend`, `WhatsappBackend`, `WebhookBackend` | Routing por canal + ambiente dev/prod |
| `StockBackend` | `StockmanAdapter` (real), `NoopStockBackend` (testes) | Permite teste sem DB real |
| `PricingBackend` | 4 estratégias coexistentes | Diferentes políticas de preço |

Em todos os casos há duas ou mais implementações reais (não apenas
"talvez-no-futuro"). O protocol descreve o contrato do ponto de substituição;
o adapter é injetado via settings:

```python
# framework/shopman/protocols.py
@runtime_checkable
class PaymentBackend(Protocol):
    def create_intent(self, amount_q: int, ...) -> PaymentIntent: ...
    def capture(self, intent_id: str, ...) -> CaptureResult: ...

# config/settings.py
SHOPMAN_PAYMENT_BACKEND = "shopman.shop.adapters.payment_efi.EfiPixBackend"
```

### 4. Invariantes

- **Independência dos cores é invariante absoluto.** Nenhum core importa outro
  core (exceto `utils`). Violações são bloqueadas por testes de invariante.
- **Substituibilidade é decisão pontual.** Novos Protocols precisam de uma razão
  concreta — pelo menos duas implementações reais previstas, ou necessidade de
  mock em testes. "Pode ser útil um dia" não justifica.

## Consequências

### Positivas

- **Cores testáveis isoladamente.** `make test-stockman` roda sem precisar do
  framework. CI dos cores pode rodar em paralelo aos do framework.
- **Deploy independente futuro.** Cada core vira `pip install shopman-<persona>`
  sem arrastar framework junto.
- **Código mais direto.** Services do framework não dançam com `get_adapter()`
  para chamar cores — importam direto. Menos indireção, menos arquivos, menos
  navegação.
- **Protocols onde há valor.** Cada Protocol existente tem uso concreto (gateway
  real, mock de teste, routing). Nenhum é decorativo.
- **Ponto único de composição.** Todo fluxo cross-domain passa pelo framework.
  Debug, auditoria e teste de integração sabem exatamente onde olhar.

### Negativas

- **Framework conhece todos os cores.** Isso é intencional (ver ADR-005) — o
  framework é o integrador. Mas significa que mudanças cross-domain tocam o
  framework, não podem ser feitas "só no core".
- **Substituir um core requer mais trabalho.** Trocar stockman inteiro por
  outro sistema exigiria reescrever os pontos do framework que o usam. Não é
  plug-and-play — mas também não é a realidade que o projeto otimiza para.

### Mitigações

- Testes de invariante (`framework/shopman/tests/test_invariants.py`) garantem
  que cores não importam outros cores.
- A lista de Protocols está documentada em `docs/reference/protocols.md` e é
  regenerada a partir do código.
- `MockStockBackend`, `MockPaymentBackend` etc. permitem testar o framework sem
  DBs reais.

## Referências

- ADR-005: por que o framework é intencionalmente um ponto de coordenação
- `docs/constitution.md` §3.4: definições canônicas de core/plugin/adapter/framework
- `docs/reference/protocols.md`: inventário atualizado de Protocols e Adapters
