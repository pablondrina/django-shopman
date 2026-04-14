# Referência — Rules Engine

> Modelo de governança das regras de negócio configuráveis.

---

## Duas Camadas, Separadas Intencionalmente

O framework usa duas camadas de configuração de comportamento:

### 1. Handlers — Estáticos, Boot-time

Handlers são registrados **uma vez**, em `setup.register_all()`, chamado por
`ShopmanConfig.ready()`. São os processadores de Directives que conectam o
lifecycle: `NotificationSendHandler`, `ConfirmationTimeoutHandler`,
`NFCeEmitHandler`, etc.

- **Onde**: `shopman/shop/handlers/` + `shopman/shop/setup.py`
- **Quando muda**: requer deploy
- **Propósito**: expressa *como o sistema funciona*

### 2. Rules — Dinâmicas, DB-driven

`RuleConfig` rows no banco configuram validators e pricing modifiers. Operadores
podem ativar/desativar rules, ajustar parâmetros e restringir a canais — sem
deploy. O cache é invalidado a cada `RuleConfig.save()` ou `delete()`.

- **Onde**: `shopman/shop/rules/`, model `RuleConfig`
- **Quando muda**: admin do operador, sem deploy
- **Propósito**: expressa *como o negócio se comporta*

```
Boot:
  setup.register_all()         → registra handlers (estáticos)
  rules.register_active_rules() → registra validators do DB (dinâmicos)

Runtime:
  order.modify() → validators rodam (inclui rules dinâmicas)
  order.commit() → validators rodam
  RuleConfig.save → cache invalidado → próxima avaliação usa novo config
```

---

## Rules Disponíveis

### Validators

| Code | Classe | Params | Efeito |
|------|--------|--------|--------|
| `business_hours` | `BusinessHoursRule` | `open_hour`, `close_hour` | Seta flag `outside_business_hours` em `session.data`. NÃO bloqueia checkout — apenas informa |
| `minimum_order` | `MinimumOrderRule` | `amount_q: int` | Bloqueia commits abaixo do valor mínimo com issue `minimum_order_not_met` |

### Modifiers (Pricing)

| Code | Classe | Params | Efeito |
|------|--------|--------|--------|
| `d1_discount` | `D1Discount` | `percent: int` | Desconto automático em produtos D-1 |
| `promotion` | `PromotionDiscount` | — | Aplica promoções ativas do admin |
| `employee_discount` | `EmployeeDiscount` | `percent: int` | Desconto para clientes do grupo "funcionário" |
| `happy_hour` | `HappyHour` | `percent: int`, `start_hour`, `end_hour` | Desconto em faixa horária |

---

## Registro de uma Nova Rule

1. Crie a classe em `shopman/shop/rules/` (validator ou modifier)
2. A classe deve implementar o protocol `Validator` ou `Modifier` de Orderman
3. Adicione uma linha em `RuleConfig` via admin com o `rule_path` correto
4. A rule entra em vigor imediatamente (cache invalidado)

```python
# Exemplo: validator mínimo
class MinimumOrderRule:
    rule_type = "validator"
    code = "minimum_order"

    def __init__(self, amount_q: int):
        self.amount_q = amount_q

    def validate(self, session, context) -> list[dict]:
        if session.total_q < self.amount_q:
            return [{"code": "minimum_order_not_met", "blocking": True, ...}]
        return []
```

---

## ChannelConfig.rules — Ativação por Canal

`ChannelConfig.rules` controla quais validators e modifiers rodam por canal:

```python
# config.py
@dataclass
class RulesConfig:
    validators: list[str] = field(default_factory=list)
    modifiers:  list[str] = field(default_factory=list)
    checks:     list[str] = field(default_factory=list)
```

Exemplo no Channel.config:
```json
{
  "rules": {
    "validators": ["business_hours", "minimum_order"],
    "modifiers": ["d1_discount", "promotion"]
  }
}
```

Ver também: [`data-schemas.md § Channel.config`](data-schemas.md#6-rules--quais-validatorsmodifiers-ativar).
