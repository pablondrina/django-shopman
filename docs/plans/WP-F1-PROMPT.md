# WP-F1 — Framework Rebuild Prompt

## Contexto

WP-K1 foi concluído com sucesso. O kernel (`packages/omniman`) foi limpo:
- `Channel.flow` → `Channel.kind`
- `Channel.listing_ref` removido (convenção: `listing.ref == channel.ref`)
- `Channel.config` removido do kernel (config é responsabilidade do framework)
- `order.snapshot["lifecycle"]` é onde lifecycle config é "baked" no commit
- `CommitService`, `ModifyService`, `ResolveService` aceitam `channel_config: dict | None`
- `ChannelConfig.for_channel()` é o método primário (cascade: canal ← loja ← defaults)
- 1.230+ testes passando

## Objetivo WP-F1

Reconstruir a camada de orquestração do framework para ser **simples, robusta e elegante**.
Zero legado. Zero gambiarras. Zero swallowing de exceções.

## Itens do WP-F1

### F1-1: Boot honesto — `apps.py` + `setup.py` + `handlers/__init__.py`

**Regra:** Required components raise on failure. Optional (not configured) are silent. Configured-but-wrong is fatal.

Tarefas:
- Auditar `framework/shopman/apps.py` — o `ready()` deve registrar handlers sem engolir exceções de componentes required
- Avaliar se `framework/shopman/setup.py` pode ser **deletado** (lógica migrada para `apps.py` diretamente ou para `handlers/__init__.py`)
- `framework/shopman/handlers/__init__.py` deve ter lista declarativa `ALL_HANDLERS` (sem separação artificial CORE/OPTIONAL)

### F1-2: `topics.py` → `directives.py`, `dispatch()` propaga, `for_channel()` completo

Tarefas:
- Renomear `framework/shopman/topics.py` → `framework/shopman/directives.py`
  - Zero residuals: atualizar todos os imports
- `framework/shopman/flows.py`: `dispatch()` deve **propagar** exceções (não engolir)
  - Orders stuck in inconsistent state são piores que um erro visível
- `ChannelConfig.for_channel()` em `framework/shopman/config.py`:
  - Implementar leitura de canal-level override via `_ChannelConfigRecord` (criado em F1-3)
  - Por ora está com comentário `# Canal-level override: WP-F1`

### F1-3: `ChannelConfig` storage model + Shop integrations

**O maior item.** Canal-level config precisa de um storage model interno.

Design:
```python
# framework/shopman/models/_channel_config.py  (ou em models/__init__.py)
class _ChannelConfigRecord(models.Model):
    """Storage interno para ChannelConfig canal-level. Prefixo _ = detalhe de implementação."""
    channel_ref = models.CharField(max_length=64, unique=True)
    data = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = "shopman"
```

- `ChannelConfig.for_channel(channel)` lê `_ChannelConfigRecord.objects.filter(channel_ref=channel.ref).first()`
- Admin de `_ChannelConfigRecord` via Unfold (ou embutido no Channel admin do framework)
- `Shop` recebe campos de integração (adapter selection): `notification_adapter`, `payment_adapters` etc. — **toda configuração de negócio deve ser Admin-configurável**

### F1-4: Payment state contract

`order.data["payment"]` deve conter **apenas** `{intent_ref, method}`.
Payman é a fonte canônica de status — nunca duplicar status em `order.data`.

Tarefas:
- Auditar todos os lugares que escrevem em `order.data["payment"]`
- Garantir que nenhum handler escreve `status`, `paid_at`, etc. em `order.data["payment"]`
- Documentar contrato em `docs/reference/data-schemas.md`

## Arquivos Chave

```
framework/shopman/
├── apps.py              # Boot — ready() com registro de handlers
├── setup.py             # Registro central — candidato a deletar
├── topics.py            # Constantes de tópicos — renomear para directives.py
├── flows.py             # BaseFlow, dispatch() — propagar exceções
├── config.py            # ChannelConfig dataclass — for_channel() completo
├── handlers/
│   ├── __init__.py      # Deve ter ALL_HANDLERS declarativo
│   ├── notification.py
│   ├── stock.py
│   ├── confirmation.py
│   ├── loyalty.py
│   └── ...
└── models/              # _ChannelConfigRecord vai aqui
```

## Convenções Ativas

- **Zero residuals**: em renames, zerar TUDO (imports, strings, comments)
- **Zero backward-compat aliases**: projeto novo, sem consumidores externos
- **Nomes sem prefixo `_`** em APIs públicas — `_` só para implementação interna
- **Toda config de negócio via Admin** (não em `settings.py`)
- **`channel.kind`** (estável, vocabulário do framework) — nunca `channel.ref` para dispatch de Flow
- **`listing.ref == channel.ref`** — convenção explícita, sem campo `listing_ref`

## Estado dos Testes

Rodar `make test` antes de começar para confirmar baseline. Esperado: ~1.230 testes passando.

## O Que NÃO Fazer

- Não inventar features além do escopo
- Não criar helpers desnecessários
- Não deixar `except Exception: pass` ou `except Exception: logger.warning(...)` em boot crítico
- Não criar `_ChannelConfigRecord` como model público (prefixo `_` intencional)
- Não duplicar lógica entre `setup.py` e `apps.py` — escolher um e eliminar o outro
