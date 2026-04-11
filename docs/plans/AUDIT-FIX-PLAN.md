# AUDIT-FIX-PLAN — Governança do framework e drift de convenção

**Origem:** auditoria severa de 2026-04-08 sobre `framework/shopman/`.
Achados documentados em `docs/_inbox/django_shopman_analise_critica_reconsiderada_v3.md`.

**Problema raiz:** agentes implementaram features sem verificar o entorno. O framework
acumulou dead code, vocabulário inconsistente, e código específico da instância Nelson
dentro do orquestrador genérico. O `instances/nelson/` existe mas está praticamente vazio.

**Princípio:** o framework deve ser uma implementação *correta, segura e genérica* dos
apps do core. Regras específicas de instância ficam em `instances/nelson/`.

---

## Tiers e ordem de execução

| Tier | Motivo | WPs |
|------|--------|-----|
| 1 — Bugs runtime | Afetam usuários em produção | AF-1, AF-2 |
| 2 — Dead code / vocabulário | Confundem agentes futuros | AF-3, AF-4 |
| 3 — Separação framework/instância | Violação arquitetural | AF-5, AF-6 |
| 4 — Limpeza | Sem risco, sem urgência | AF-7 |

Cada WP é independente e pode ser executado em branch próprio.
Recomendado: serializar dentro do mesmo tier.

---

## WP-AF-1 — Corrigir fonte de itens em notificações

**Gravidade: crítica (bug ativo)**

### Diagnóstico

`framework/shopman/handlers/notification.py:191` (método `_build_context`):

```python
"items": order.data.get("items", []),
```

`CommitService._do_commit()` copia chaves específicas de `session.data` para
`order.data` (linhas 271–279). A chave `"items"` **não está na lista**. Os itens
ficam em `order.snapshot["items"]`.

Resultado: toda notificação enviada ao cliente (`order_confirmed`, `order_ready`,
`order_dispatched`, etc.) tem `items: []`. O template recebe lista vazia.

### Solução

Alterar `_build_context` em `notification.py` para ler de `order.snapshot`:

```python
"items": order.snapshot.get("items", []),
```

Verificar se outros campos de contexto que deveriam vir do snapshot também estão
sendo lidos da fonte errada (`order.data` vs `order.snapshot`).

### Arquivos afetados

- `framework/shopman/handlers/notification.py` — corrigir `_build_context`.

### Testes obrigatórios

- `framework/shopman/tests/` — verificar/criar teste que valida que o contexto
  de notificação inclui os itens corretos após commit.
- Garantir que `NotificationSendHandler` processa corretamente uma directive
  `notification.send` para pedido com itens.

### Critério de conclusão

- [ ] `_build_context` lê `order.snapshot.get("items", [])`.
- [ ] Auditoria de outros campos em `_build_context` que possam ter o mesmo problema.
- [ ] Teste cobrindo itens no contexto de notificação.
- [ ] `make test` verde.

---

## WP-AF-2 — Alinhar Order.get_transitions() ao ChannelConfig

**Gravidade: alta (gap funcional silencioso)**

### Diagnóstico

`packages/orderman/shopman/orderman/models/order.py:136`:

```python
def get_transitions(self) -> dict:
    flow = (self.channel.config or {}).get("order_flow", {})
    return flow.get("transitions", self.DEFAULT_TRANSITIONS)
```

`ChannelConfig.Flow` expõe o mesmo dado em `flow.transitions` (não `order_flow.transitions`).
São caminhos JSON diferentes. Se alguém configura transições via `ChannelConfig` (chave
`flow.transitions` no JSON), `Order.get_transitions()` nunca as enxerga. Mesmo problema
para `get_terminal_statuses()` que lê `order_flow.terminal_statuses`.

A chave `order_flow` não existe no schema `ChannelConfig`. Nunca existiu.

### Solução

Reescrever `get_transitions()` e `get_terminal_statuses()` para usar `ChannelConfig`:

```python
def get_transitions(self) -> dict:
    from shopman.config import ChannelConfig
    flow_cfg = ChannelConfig.effective(self.channel).flow
    return flow_cfg.transitions or self.DEFAULT_TRANSITIONS

def get_terminal_statuses(self) -> list:
    from shopman.config import ChannelConfig
    flow_cfg = ChannelConfig.effective(self.channel).flow
    return flow_cfg.terminal_statuses or self.TERMINAL_STATUSES
```

Verificar se existem entradas no banco com `config["order_flow"]` (migration de dados
pode ser necessária para renomear a chave para `flow` se houver configs salvas).

### Arquivos afetados

- `packages/orderman/shopman/orderman/models/order.py` — reescrever os dois métodos.
- Possivelmente: migration de dados para renomear `order_flow` → `flow` em configs
  de canais existentes (verificar com `Channel.objects.filter(config__order_flow__isnull=False)`).

### Testes obrigatórios

- Verificar/criar teste que configura `channel.config = {"flow": {"transitions": {...}}}`
  e valida que `order.can_transition_to()` respeita a config.
- Teste de regressão: canal sem config usa `DEFAULT_TRANSITIONS`.

### Critério de conclusão

- [ ] `get_transitions()` e `get_terminal_statuses()` usam `ChannelConfig.effective`.
- [ ] Chave `order_flow` eliminada do código (zero ocorrências em `grep -rn 'order_flow'`).
- [ ] Testes verdes.
- [ ] `make test` verde.

---

## WP-AF-3 — Remover ChannelConfig.Pipeline e unificar vocabulário de pagamento

**Gravidade: alta (dead code + vocabulário confuso)**

### Diagnóstico

**`ChannelConfig.Pipeline` é completamente órfã:**
- Definida em `framework/shopman/config.py:66-88` com campos `on_commit`,
  `on_confirmed`, `on_payment_confirmed`, etc.
- Nenhum código do framework lê `channel_config.pipeline.*`.
- O sistema migrou inteiramente para `flows.dispatch(order, "on_paid")`.

**Três nomes para a mesma fase de pagamento:**
- `config.py:87` → `Pipeline.on_payment_confirmed` (órfão)
- `webhooks/stripe.py:120`, `webhooks/efi.py:146` → `auto_transitions.get("on_payment_confirm")` (sem "d")
- `lifecycle.py` → `Flow.on_paid()` (o real, em produção)

Risco concreto: se alguém configurar `auto_transitions: {on_payment_confirmed: "confirmed"}`
seguindo o nome do Pipeline, não vai funcionar — o webhook procura `on_payment_confirm`.

### Solução

1. **Remover `ChannelConfig.Pipeline`** do `config.py` integralmente.
   - Remover o campo `pipeline` da dataclass `ChannelConfig`.
   - Remover o parse de `pipeline` em `from_dict()`.
   - Buscar e remover qualquer referência remanescente.

2. **Padronizar chave de auto-transition para `on_paid`** (alinhado com `lifecycle.py`):
   - `webhooks/stripe.py:120`: `auto_transitions.get("on_payment_confirm")` → `auto_transitions.get("on_paid")`
   - `webhooks/efi.py:146`: idem.
   - Documentar no docstring de `ChannelConfig.Flow.auto_transitions` que a chave
     canônica é `on_paid`.

3. **Atualizar seed/fixtures** se existirem configs com `pipeline` ou `on_payment_confirm`.

### Arquivos afetados

- `framework/shopman/config.py` — remover `Pipeline`, remover `pipeline` field.
- `framework/shopman/webhooks/stripe.py` — renomear chave.
- `framework/shopman/webhooks/efi.py` — renomear chave.
- `framework/shopman/management/commands/seed.py` — remover quaisquer configs com `pipeline`.

### Testes obrigatórios

- Verificar que `ChannelConfig.from_dict({"pipeline": {...}})` não quebra (campo
  desconhecido é ignorado via `_safe_init` — confirmar).
- Teste de webhook: `auto_transitions: {on_paid: "confirmed"}` dispara transição.

### Critério de conclusão

- [ ] `Pipeline` removido de `config.py`.
- [ ] `grep -rn 'pipeline' framework/shopman/` retorna zero (exceto comentários históricos).
- [ ] `grep -rn 'on_payment_confirm' framework/` retorna zero.
- [ ] Webhooks usam `on_paid` como chave canônica.
- [ ] `make test` verde.

---

## WP-AF-4 — CommitService: required_checks via ChannelConfig.rules.checks

**Gravidade: média/alta (inconsistência de configuração)**

### Diagnóstico

`packages/orderman/shopman/orderman/services/commit.py:202`:

```python
required_checks = channel.config.get("required_checks_on_commit", [])
```

`ChannelConfig.Rules` já tem o campo `checks: list[str]` que serve exatamente esse
propósito. São duas linguagens de configuração para o mesmo conceito:

| Caminho raw JSON | Caminho tipado |
|---|---|
| `channel.config["required_checks_on_commit"]` | `ChannelConfig.rules.checks` |

O caminho tipado beneficia do cascade loja←canal←defaults. O caminho raw não.

### Solução

Reescrever `CommitService._do_commit()` para usar `ChannelConfig`:

```python
from shopman.config import ChannelConfig
...
cfg = ChannelConfig.effective(channel)
required_checks = cfg.rules.checks
```

Verificar se existem canais configurados com `required_checks_on_commit` no banco e
migrar os valores para a chave `rules.checks` no JSON do canal.

### Arquivos afetados

- `packages/orderman/shopman/orderman/services/commit.py` — substituir leitura.
- Possivelmente: script de migração de dados para renomear chave em configs existentes.

### Testes obrigatórios

- Verificar/criar teste que configura canal com `rules.checks = ["availability"]` e
  valida que CommitService exige o check antes de confirmar.

### Critério de conclusão

- [ ] `required_checks_on_commit` eliminado do código.
- [ ] `CommitService` usa `ChannelConfig.effective(channel).rules.checks`.
- [ ] Testes verdes.
- [ ] `make test` verde.

---

## WP-AF-5 — Extrair lógica Nelson-específica de services/customer.py

**Gravidade: alta (violação framework/instância)**

### Diagnóstico

`framework/shopman/services/customer.py` discrimina o handler de cliente por
`channel_ref` e `handle_type`:

```python
if handle_type == "manychat":
    customer = _handle_manychat(order)
elif channel_ref == "ifood":
    customer = _handle_ifood(order)
elif channel_ref == "balcao":          # ← NELSON-ESPECÍFICO
    customer = _handle_balcao(order)   # ← resolve CPF + balcão/counter
else:
    customer = _handle_phone(order)
```

- `manychat` e `ifood` são canais genéricos (padrões de mercado).
- `balcao` é específico de Nelson: implica CPF, atendimento presencial, PDV.
  O framework não deveria saber o nome do canal de balcão de nenhuma instância.

### Solução

Converter `ensure_customer()` para um **registry de strategies**:

```python
# framework/shopman/services/customer.py

_STRATEGIES: dict[str, Callable] = {}

def register_strategy(key: str, fn: Callable) -> None:
    _STRATEGIES[key] = fn

def ensure_customer(order) -> Customer | None:
    channel_ref = order.channel.ref
    handle_type = order.handle_type or ""

    # Lookup order: handle_type first, then channel_ref
    fn = _STRATEGIES.get(handle_type) or _STRATEGIES.get(channel_ref)
    if fn:
        return fn(order)
    return _handle_phone(order)  # default genérico

# Strategies genéricas registradas no framework:
register_strategy("manychat", _handle_manychat)
register_strategy("ifood", _handle_ifood)
```

A instância Nelson registra a strategy `balcao` no seu `AppConfig.ready()`:

```python
# instances/nelson/apps.py (ou shopman_config.py)
from shopman.services.customer import register_strategy
register_strategy("balcao", nelson_handle_balcao)
```

### Arquivos afetados

- `framework/shopman/services/customer.py` — refatorar para registry pattern;
  remover `_handle_balcao` e toda discriminação por `channel_ref == "balcao"`.
- `instances/nelson/` — criar módulo com `nelson_handle_balcao` e registro no AppConfig.

### Testes obrigatórios

- Verificar que `ensure_customer` com `handle_type="manychat"` ainda funciona.
- Verificar que strategy customizada registrada é chamada para o channel_ref correto.
- Verificar fallback para `_handle_phone` quando nenhuma strategy registrada.

### Critério de conclusão

- [ ] `_handle_balcao` removido de `services/customer.py`.
- [ ] `grep -rn 'balcao' framework/shopman/services/` retorna zero.
- [ ] Registry pattern implementado e documentado.
- [ ] Instância Nelson registra strategy no lugar adequado.
- [ ] `make test` verde.

---

## WP-AF-6 — Parametrizar STOREFRONT_CHANNEL_REF via settings

**Gravidade: média (bloqueia outras instâncias)**

### Diagnóstico

`framework/shopman/web/cart.py:14`:
```python
CHANNEL_REF = "web"
```

`framework/shopman/web/constants.py:39` (ou equivalente):
```python
STOREFRONT_CHANNEL_REF = "web"
```

Qualquer instância que nomear seu canal storefront diferente de `"web"` (ex: `"site"`,
`"storefront"`, `"loja"`) tem o storefront quebrado silenciosamente.

### Solução

```python
# framework/shopman/web/cart.py
from django.conf import settings

CHANNEL_REF = getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web")
```

Documentar `SHOPMAN_STOREFRONT_CHANNEL_REF` no README ou `project/settings.py`.
A instância Nelson define `SHOPMAN_STOREFRONT_CHANNEL_REF = "web"` no seu `settings.py`
(ou simplesmente herda o default).

### Arquivos afetados

- `framework/shopman/web/cart.py` — ler de settings.
- `framework/shopman/web/constants.py` — idem (se houver constante duplicada).
- `instances/nelson/project/settings.py` — adicionar a variável explicitamente.

### Critério de conclusão

- [ ] `CHANNEL_REF = "web"` hardcoded removido.
- [ ] Lê `settings.SHOPMAN_STOREFRONT_CHANNEL_REF` com default `"web"`.
- [ ] `make test` verde.

---

## WP-AF-7 — Limpeza: docstrings, help texts e seed data Nelson

**Gravidade: baixa (não afeta runtime)**

### Diagnóstico

Resíduos de nomes antigos e dados Nelson em código não-executável:

| Arquivo | Problema |
|---------|----------|
| `framework/shopman/setup.py:4-5` | Fala em "offering", "stocking", "crafting", "ordering" |
| `framework/shopman/lifecycle.py:17` | "KDSInstance (models), Recipe (crafting), CollectionItem (offering)" |
| `framework/shopman/management/commands/seed.py:4-5` | "catalogo (offering), estoque (stocking), receitas (crafting), clientes (customers), canais (ordering)" |
| `framework/shopman/models/shop.py` | help_text com `nelsonboulangerie.com.br` |
| `framework/shopman/management/commands/seed.py` | emails e URLs de Nelson |
| `framework/shopman/services/production.py:5` | "contrib/stocking" |

### Solução

- Substituir nomes antigos em docstrings/comments:
  - `offering` → `offerman`
  - `stocking` → `stockman`
  - `crafting` → `craftsman`
  - `ordering` → `orderman`
- Substituir referências Nelson em help texts por placeholders genéricos
  (ex: `"https://instagram.com/suanomequi"` → `"https://instagram.com/example"`).
- No `seed.py`: substituir emails/URLs Nelson por genéricos (`admin@example.com`, etc.).
  **Não quebrar a funcionalidade do seed** — só os valores de exemplo.

### Arquivos afetados

Veja tabela acima. Executar grep para encontrar todas as ocorrências antes de editar:
```bash
grep -rn 'offering\|stocking\|crafting\|ordering\|nelsonboulangerie' \
  framework/shopman/ --include="*.py"
```

### Critério de conclusão

- [ ] `grep -rn 'offering\|stocking\|crafting\|ordering' framework/shopman/ --include="*.py"`
  retorna zero (exceto imports onde o nome é correto, ex: `from shopman.offerman`).
- [ ] `grep -rn 'nelsonboulangerie\|nelson\.com\.br' framework/shopman/` retorna zero.
- [ ] `make test` verde.

---

## Ordem de execução recomendada

```
AF-1  (bug crítico)
AF-2  (bug silencioso)
AF-3  (dead code / vocabulário)
AF-4  (config inconsistente)
AF-5  (separação instância)
AF-6  (parametrização)
AF-7  (limpeza)
```

Cada WP tem um critério de conclusão verificável. Executar `make test` ao final de
cada WP antes de passar para o próximo.

## Notas de princípio

- **Zero backward-compat**: renomear `on_payment_confirm` → `on_paid` em tudo.
  Não criar alias. O projeto não tem consumidores externos.
- **Zero gambiarras**: registry pattern em AF-5 é a solução correta, não um `if` extra.
- **Core é sagrado**: todos os WPs tocam apenas no framework orquestrador ou na
  instância. Nenhum WP modifica `packages/` exceto AF-2 e AF-4 que tocam em
  `packages/orderman/` com cirurgia mínima.
