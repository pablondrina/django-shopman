# ADR-007: Lifecycle dispatch funcional e config-driven

**Status:** Aceito
**Data:** 2026-04-15
**Atualizado:** 2026-04-25

---

## Contexto

O orquestrador coordena dois ciclos de vida:

1. **Order** — pedido do cliente, coordenado por `shopman/shop/lifecycle.py`.
2. **WorkOrder** — produção, coordenada por `shopman/shop/production_lifecycle.py`.

Ambos usam o mesmo padrão arquitetural: uma tabela explícita de fases mapeia o nome do evento para uma função pequena. Não existem classes de lifecycle, registry dinâmico, aliases de compatibilidade ou taxonomia antiga.

## Decisão

Lifecycle no Shopman é funcional, explícito e orientado por configuração:

```python
_PHASE_HANDLERS = {
    "on_commit": _on_commit,
    "on_confirmed": _on_confirmed,
}

def dispatch(order, phase):
    config = ChannelConfig.for_channel(order.channel_ref)
    _PHASE_HANDLERS[phase](order, config)
```

Produção segue a mesma leitura:

```python
_PRODUCTION_PHASE_HANDLERS = {
    "standard": {
        "on_planned": _standard_on_planned,
        "on_finished": _standard_on_finished,
    },
}

def dispatch_production(work_order, phase):
    lifecycle_name = production_lifecycle_name_for(work_order.recipe)
    _PRODUCTION_PHASE_HANDLERS[lifecycle_name][phase](work_order)
```

Para pedidos, a variação vem de `ChannelConfig`. Para produção, a variação vem de `recipe.meta["production_lifecycle"]`. Em ambos os casos, o ponto canônico é o mesmo: dado explícito seleciona função explícita.

## Consequências

- **Um jeito canônico:** lifecycle é tabela de fases + função. Nova fase entra como função e linha na tabela.
- **Sem herança:** nenhuma lógica de negócio depende de subclasses para alterar comportamento.
- **Sem conceito obsoleto:** o vocabulário público é `lifecycle`; nomes antigos não aparecem como API, config ou modelo mental.
- **Teste arquitetural:** `shopman/shop/tests/test_invariants.py` bloqueia classes em `lifecycle.py` e `production_lifecycle.py`.
- **Leitura simples:** contributor não precisa aprender dois padrões para entender Order e WorkOrder.

## Como estender

Para adicionar uma fase de Order:

1. Criar função privada em `lifecycle.py`.
2. Registrar em `_PHASE_HANDLERS`.
3. Cobrir com teste de dispatch e efeito de service.
4. Se a variação for por canal, adicionar campo em `ChannelConfig` apenas quando for dimensão real de negócio.

Para adicionar um lifecycle de produção:

1. Criar funções privadas em `production_lifecycle.py`.
2. Registrar em `_PRODUCTION_PHASE_HANDLERS` sob um nome canônico.
3. Selecionar via `recipe.meta["production_lifecycle"]`.
4. Cobrir com teste de dispatch e efeitos de produção.

## Referências

- [`shopman/shop/lifecycle.py`](../../shopman/shop/lifecycle.py)
- [`shopman/shop/production_lifecycle.py`](../../shopman/shop/production_lifecycle.py)
- [`shopman/shop/config.py`](../../shopman/shop/config.py)
- [`shopman/shop/tests/test_invariants.py`](../../shopman/shop/tests/test_invariants.py)
