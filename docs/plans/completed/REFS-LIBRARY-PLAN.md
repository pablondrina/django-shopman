# REFS-LIBRARY-PLAN — shopman-refs

> Biblioteca genérica de string refs para a suíte Django-Shopman.
> Substitui `orderman/contrib/refs` por um pacote top-level.

Data: 2026-04-20

---

## Visão

Um Ref é um par `(type, value)` que resolve para qualquer entidade do sistema, dentro de um scope.
É o DNS do domínio — liga sem acoplar.

A biblioteca vive em `packages/refs/` como `shopman-refs`, pip-installable, sem dependência
nos outros pacotes. Qualquer app Django pode usá-la.

```
packages/refs/                       shopman-refs
└── shopman/refs/
    ├── __init__.py                  API pública (attach, resolve, rename, ...)
    ├── models.py                    Ref, RefSequence
    ├── types.py                     RefType dataclass
    ├── registry.py                  RefTypeRegistry + RefSourceRegistry
    ├── services.py                  attach, resolve, deactivate, transfer
    ├── bulk.py                      rename, cascade, migrate, deactivate_scope
    ├── generators.py                Sequence, DateSequence, ShortUUID, Checksum
    ├── fields.py                    RefField (CharField inteligente)
    ├── signals.py                   ref_attached, ref_deactivated, ref_renamed, ref_transferred
    ├── exceptions.py                RefConflict, RefNotFound, RefScopeInvalid
    ├── apps.py                      RefsConfig
    ├── admin.py                     Admin inline/standalone (Unfold-ready)
    ├── contrib/
    │   └── admin_unfold/
    │       ├── apps.py              RefsAdminUnfoldConfig
    │       └── admin.py             Unfold-specific admin (badges, search, bulk actions)
    ├── management/commands/
    │   ├── refs_rename.py           manage.py refs_rename --type=SKU --old=X --new=Y
    │   └── refs_audit.py            manage.py refs_audit --orphaned --stale
    ├── migrations/
    └── tests/
```

---

## Fase 1 — Core library (standalone)

### WP-REF-01: Models + Types + Registry

**Ref model:**

```python
class Ref(models.Model):
    id = UUIDField(primary_key=True, default=uuid4)

    # O QUE
    ref_type = CharField(max_length=32, db_index=True)
    value = CharField(max_length=128, db_index=True)

    # A QUEM (generic target)
    target_type = CharField(max_length=64)    # "orderman.Session", "guestman.Customer"
    target_id = CharField(max_length=64)

    # ONDE (scope de unicidade)
    scope = JSONField(default=dict)

    # ESTADO
    is_active = BooleanField(default=True, db_index=True)

    # AUDITORIA
    created_at = DateTimeField(auto_now_add=True)
    actor = CharField(max_length=128, blank=True)           # "system", "user:42", "lifecycle:commit"
    deactivated_at = DateTimeField(null=True, blank=True)
    deactivated_by = CharField(max_length=128, blank=True)

    # EXTENSÍVEL
    metadata = JSONField(default=dict)

    class Meta:
        app_label = "refs"
        indexes = [
            Index(fields=["ref_type", "value", "is_active"]),
            Index(fields=["target_type", "target_id", "is_active"]),
        ]
```

Nota: `target_type` usa `{app_label}.{ModelName}` (padrão Django `ContentType.app_label + model`),
mas NÃO usa GenericForeignKey — é string pura, sem dependência em `contenttypes` framework.

**RefType dataclass:**

```python
@dataclass(frozen=True)
class RefType:
    slug: str
    label: str

    # Targeting
    allowed_targets: tuple[str, ...] = ("*",)     # ("orderman.Session",) ou ("*",)

    # Scope & Uniqueness
    scope_keys: tuple[str, ...] = ()
    unique_scope: str = "active"                   # "active" | "all" | "none"

    # Value handling
    normalizer: str = "upper_strip"                # "upper_strip" | "lower_strip" | "none"
    validator: str | None = None                   # regex pattern

    # Generation (optional)
    generator: str | None = None                   # "sequence" | "date_sequence" | "short_uuid"
    generator_format: str = "{value}"              # "PED-{value:04d}", "T-{value:03d}"

    # Lifecycle (declarativo)
    on_deactivate: str = "nothing"                 # "nothing" | "cascade_deactivate"
```

**Registry:**

Dois registries:
- `RefTypeRegistry` — tipos de ref (POS_TABLE, SKU, etc.)
- `RefSourceRegistry` — campos RefField em models (para cascade/bulk)

**Entregáveis:**
- `models.py`, `types.py`, `registry.py`, `exceptions.py` (RefConflict, RefNotFound, RefScopeInvalid, AmbiguousRef)
- `apps.py` (RefsConfig, label="refs")
- `pyproject.toml` para shopman-refs
- Migrações
- Testes unitários do modelo e registry

---

### WP-REF-02: Services (attach, resolve, deactivate, transfer)

API pública:

```python
# Ligar ref a target
ref = attach(
    ref_type="POS_TABLE",
    value="12",
    target="orderman.Session:47",     # ou (Session, 47)
    scope={"store_id": 1, "business_date": "2026-04-20"},
    actor="pos:caixa",
)

# Resolver ref → target
result = resolve("POS_TABLE", "12", scope={...})
# → ("orderman.Session", "47") ou None

# Resolver com fetch do objeto
session = resolve_object("POS_TABLE", "12", scope={...})
# → Session instance ou None (import dinâmico via app registry)

# Desativar
deactivate(target="orderman.Session:47", ref_types=["POS_TABLE"], actor="lifecycle:close")

# Transferir (Session→Order no commit)
transfer(
    source="orderman.Session:47",
    dest="orderman.Order:103",
    ref_types=None,  # todas
    actor="lifecycle:commit",
)

# Listar refs de um target
refs = refs_for("orderman.Session:47", active_only=True)

# Resolver por sufixo (operador diz "AZ19" → encontra "POS-260420-AZ19")
result = resolve_partial("ORDER_REF", "AZ19", scope={...})
# → ("orderman.Order", "103") ou None
# Busca refs ACTIVE cujo value TERMINA com o sufixo dado, dentro do scope.
# Se encontrar exatamente 1: retorna. Se 0: None. Se >1: raise AmbiguousRef.
```

**Target string format:** `"{app_label}.{ModelName}:{pk}"` — parseable, legível, sem magic.
Helper: `target_str(instance)` → `"orderman.Session:47"`.

**Entregáveis:**
- `services.py` com as 7 operações (attach, resolve, resolve_partial, resolve_object, deactivate, transfer, refs_for)
- Target string parser/builder helpers
- `resolve_object()` com import dinâmico via `django.apps.apps.get_model()`
- `resolve_partial()` com busca por sufixo + AmbiguousRef exception
- Testes completos (attach, idempotência, conflito, resolve, resolve_partial, deactivate, transfer)

---

### WP-REF-03: Bulk operations

```python
from shopman.refs.bulk import RefBulk

# 1. Renomear valor — "produto mudou de SKU"
count = RefBulk.rename(
    ref_type="SKU",
    old_value="CROISSANT",
    new_value="CROISSANT-FR",
    scope=None,              # todas as scopes
    actor="admin:42",
)

# 2. Cascade rename — propaga para RefFields em models
count = RefBulk.cascade_rename(
    ref_type="SKU",
    old_value="CROISSANT",
    new_value="CROISSANT-FR",
    actor="admin:42",
)
# → atualiza Ref.value E todos os RefField(ref_type="SKU") nos models registrados

# 3. Migrar target — "merge de clientes"
count = RefBulk.migrate_target(
    old_target="guestman.Customer:10",
    new_target="guestman.Customer:42",
    actor="merge:admin",
)

# 4. Desativar por scope — "fim do dia operacional"
count = RefBulk.deactivate_scope(
    ref_type="POS_TABLE",
    scope={"store_id": 1, "business_date": "2026-04-20"},
    actor="lifecycle:day_close",
)

# 5. Audit — encontrar órfãos
orphans = RefBulk.find_orphaned(ref_type="SKU")
# → refs cujo target não existe mais
```

**Entregáveis:**
- `bulk.py` com as 5 operações
- Todas as operações em `transaction.atomic()` com `select_for_update`
- Logging estruturado para cada operação
- Testes (rename, cascade, migrate, deactivate_scope, find_orphaned)

---

### WP-REF-04: Signals + Generators

**Signals:**

```python
from shopman.refs.signals import ref_attached, ref_deactivated, ref_renamed, ref_transferred

# Qualquer app pode escutar
@receiver(ref_attached)
def on_ref_attached(sender, ref, **kwargs):
    logger.info("ref.attached", extra={"type": ref.ref_type, "value": ref.value})
```

Emitidos por: `attach()`, `deactivate()`, `RefBulk.rename()`, `transfer()`.

**Generators:**

```python
from shopman.refs.generators import generate_value

# Usado internamente por attach() quando RefType tem generator
value = generate_value("PICKUP_TICKET", scope={"store_id": 1, "business_date": "2026-04-20"})
# → "T-001" (primeiro do dia), "T-002", ...

# Auto-attach com geração
ref = attach(
    ref_type="PICKUP_TICKET",
    value=None,  # gera automaticamente
    target="orderman.Order:103",
    scope={...},
)
# ref.value == "T-042"
```

Generators disponíveis:
- `SequenceGenerator` — incremental scoped (usa RefSequence model, já existe)
- `DateSequenceGenerator` — reset diário (scope inclui date)
- `AlphaNumericGenerator` — 2 letras + 2 dígitos (ex: "AZ19"), 57.600 combos/scope
- `ShortUUIDGenerator` — 6-8 chars alfanuméricos
- `ChecksumGenerator` — valor + dígito verificador (para senhas de balcão)

**AlphaNumericGenerator (destaque):**

Padrão para refs de pedidos: `{prefix}-{date:%y%m%d}-{code}`
Exemplo: `POS-260420-AZ19`

```python
class AlphaNumericGenerator:
    """
    Gera códigos curtos tipo "AZ19" — 2 letras + 2 dígitos.
    
    Alfabeto sem I/O (confusão visual): 24 letras × 24 × 10 × 10 = 57.600/scope.
    Sequencial internamente, mapeado para código memorável.
    """
    LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # sem I, O
    DIGITS = "0123456789"
    
    def next(self, ref_type, scope):
        seq = self._increment_sequence(ref_type.slug, scope)
        n = seq - 1
        L, D = len(self.LETTERS), len(self.DIGITS)
        d2 = n % D; n //= D
        d1 = n % D; n //= D
        l2 = n % L; n //= L
        l1 = n % L
        return self.LETTERS[l1] + self.LETTERS[l2] + self.DIGITS[d1] + self.DIGITS[d2]
```

Anatomia do ref gerado:
```
POS - 260420 - AZ19
 │      │       │
 │      │       └── 4 chars memoráveis (2L+2D), 57.600 combos/canal/dia
 │      │           Operador/cliente usa só isso no dia a dia
 │      │
 │      └────────── YYMMDD — namespace temporal
 │
 └───────────────── Prefixo do canal (vem do Channel.ref)
                    Namespace operacional
```

RefType correspondente:
```python
ORDER_REF = RefType(
    slug="ORDER_REF",
    label="Referencia do Pedido",
    allowed_targets=("orderman.Order",),
    scope_keys=("channel_ref", "business_date"),
    unique_scope="all",
    normalizer="upper_strip",
    validator=r"^[A-Z]{2,5}-\d{6}-[A-Z]{2}\d{2}$",
    generator="alpha_numeric",
    generator_format="{channel_prefix}-{date:%y%m%d}-{code}",
    on_deactivate="nothing",
)
```

**Entregáveis:**
- `signals.py` com 4 signals
- `generators.py` com 4 generators
- Integração: `attach()` chama generator quando `value=None` e RefType tem generator
- Testes

---

### WP-REF-05: RefField (CharField inteligente)

```python
from shopman.refs.fields import RefField

class Product(models.Model):
    ref = RefField()                           # identidade pura, sem ref_type
    sku = RefField(ref_type="SKU")             # registra como fonte de SKU

class RecipeIngredient(models.Model):
    sku = RefField(ref_type="SKU")             # referencia Product por SKU

class Session(models.Model):
    channel_ref = RefField(ref_type="CHANNEL") # referencia Channel.ref
```

**Implementação:**

```python
class RefField(CharField):
    def __init__(self, ref_type=None, **kwargs):
        kwargs.setdefault("max_length", 64)
        kwargs.setdefault("db_index", True)
        self.ref_type = ref_type
        super().__init__(**kwargs)

    def contribute_to_class(self, cls, name):
        super().contribute_to_class(cls, name)
        # Registra no RefSourceRegistry para cascade/bulk
        # (lazy, no first access — evita import-time issues)
        from shopman.refs.registry import _ref_source_registry
        _ref_source_registry.register_lazy(
            app_label_model=f"{cls._meta.app_label}.{cls.__name__}",
            field_name=name,
            ref_type=self.ref_type,
        )

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.ref_type:
            kwargs["ref_type"] = self.ref_type
        return name, path, args, kwargs
```

**Impacto zero em migrações:** RefField é CharField com max_length/db_index defaults.
Se o campo já existe como CharField com os mesmos params, Django não gera migração ao trocar
por RefField (o deconstruct produz o mesmo output).

**Bulk cascade via RefSourceRegistry:**

```python
# Dentro de RefBulk.cascade_rename()
sources = ref_source_registry.get_sources_for_type("SKU")
# → [("offerman.Product", "sku"), ("craftsman.RecipeIngredient", "sku"), ...]
for model_label, field_name in sources:
    Model = apps.get_model(model_label)
    Model.objects.filter(**{field_name: old_value}).update(**{field_name: new_value})
```

**Entregáveis:**
- `fields.py` com RefField
- RefSourceRegistry em `registry.py`
- Integração com `RefBulk.cascade_rename()`
- Testes: contribute_to_class, deconstruct, cascade

---

## Fase 2 — Admin interface

### WP-REF-06: Admin Unfold

**Standalone admin (Ref browser):**

```
┌─────────────────────────────────────────────────────────┐
│  Referências                                    [+ Add] │
├─────────────────────────────────────────────────────────┤
│ Type        │ Value       │ Target            │ Status  │
│─────────────┼─────────────┼───────────────────┼─────────│
│ POS_TABLE   │ MESA 12     │ Session #47       │ 🟢 ativo│
│ POS_TABLE   │ MESA 08     │ Session #32       │ 🔴 inativo│
│ POS_TAB     │ CMD 005     │ Session #47       │ 🟢 ativo│
│ PICKUP      │ T-042       │ Order #103        │ 🟢 ativo│
│ EXTERNAL    │ iF-8a2bc    │ Order #89         │ 🟢 ativo│
│ SKU         │ CROISSANT   │ Product #12       │ 🟢 ativo│
└─────────────┴─────────────┴───────────────────┴─────────┘

Filters: [Type ▼] [Status ▼] [Target Type ▼] [Scope: store ▼]
Search: [ref_type, value, target_id________________]
```

**Bulk actions no admin:**
- "Desativar selecionados"
- "Renomear valor..." → modal pede novo valor, aplica RefBulk.rename()
- "Transferir para..." → modal pede novo target, aplica RefBulk.migrate_target()

**Inline para qualquer model:**

```python
# Em qualquer admin de qualquer pacote
from shopman.refs.contrib.admin_unfold.admin import RefInline

class SessionAdmin(ModelAdmin):
    inlines = [RefInline]
    # Mostra todas as Refs ligadas a esta Session
    # Botão [+ Attach Ref] abre formulário inline
```

O RefInline detecta o target automaticamente: `target_type = f"{model._meta.app_label}.{model.__name__}"`,
`target_id = str(instance.pk)`.

**Dashboard widget:**

```python
# Widget para o dashboard Unfold
from shopman.refs.contrib.admin_unfold.admin import refs_summary_widget

# Mostra: Total refs ativos, por tipo, refs órfãos, refs expirados hoje
```

**Entregáveis:**
- `admin.py` com RefAdmin (standalone, filtros, search)
- `contrib/admin_unfold/admin.py` com Unfold badges, RefInline, bulk actions, dashboard widget
- Integração com DashboardTable (já existe em utils)

---

### WP-REF-07: Management commands

```bash
# Renomear ref
python manage.py refs_rename --type=SKU --old=CROISSANT --new=CROISSANT-FR --cascade --actor=admin

# Audit
python manage.py refs_audit --orphaned    # refs cujo target não existe
python manage.py refs_audit --stale       # refs ativos sem atividade há N dias
python manage.py refs_audit --duplicates  # refs com mesmo (type, value, scope) ambos ativos

# Deactivate scope
python manage.py refs_deactivate_scope --type=POS_TABLE --scope='{"store_id":1,"business_date":"2026-04-20"}'

# Stats
python manage.py refs_stats
# → POS_TABLE: 12 active, 340 inactive
# → SKU: 89 active, 0 inactive
# → PICKUP_TICKET: 42 active today, 1203 total
```

**Entregáveis:**
- 4 management commands
- Output colorido com summary
- `--dry-run` em todas as operações destrutivas

---

## Fase 3 — Migração do contrib/refs

### WP-REF-08: Migrar orderman/contrib/refs → packages/refs

1. Copiar e adaptar models, services, types, tests do contrib para o novo pacote
2. `target_kind` ("SESSION"/"ORDER") → `target_type` ("orderman.Session"/"orderman.Order")
3. Manter backward-compat temporário em orderman: thin wrapper que importa de `shopman.refs`
4. Atualizar CommitService hook para usar nova API
5. Atualizar Nelson para registrar RefTypes no novo registry
6. Remover contrib/refs do orderman
7. Atualizar INSTALLED_APPS: adicionar `shopman.refs`, remover `shopman.orderman.contrib.refs`

**Migration de dados:** Script para converter Refs existentes:
```python
# Ref antigo: target_kind="SESSION", target_id="47"
# Ref novo:   target_type="orderman.Session", target_id="47"
```

**Entregáveis:**
- Novo pacote funcional com todos os testes passando
- Orderman sem contrib/refs
- Migration script
- Zero residuals

---

## Fase 4 — Adoção incremental do RefField

### WP-REF-09: RefField nos pontos de alta conectividade

Campos candidatos (por impacto de cascade):

| Model | Campo | ref_type | Referenciado por |
|-------|-------|----------|-----------------|
| Product | `sku` | `"SKU"` | RecipeIngredient.sku, SessionItem.sku, Quant.sku, Hold.sku, ListingItem.sku |
| Product | `ref` | `None` | (identidade, sem cascade) |
| Channel | `ref` | `"CHANNEL"` | Session.channel_ref, ChannelConfig |
| Recipe | `ref` | `None` | (identidade) |
| Customer | `ref` | `"CUSTOMER"` | (para futuro cross-ref) |

**Migração:** CharField → RefField. Zero migration se params idênticos.
O cascade de SKU é o mais valioso — um rename de SKU hoje exige tocar 6+ tabelas manualmente.

**Entregáveis:**
- RefField aplicado nos 5 campos acima
- Testes de cascade: rename SKU propaga para todos os models
- Documentação

---

## Interface de uso (resumo)

### Para quem consome (qualquer pacote):

```python
from shopman.refs import attach, resolve, deactivate, transfer
from shopman.refs import RefBulk
from shopman.refs.fields import RefField
from shopman.refs.types import RefType
from shopman.refs.registry import register_ref_type
```

### Para quem registra tipos (instances/nelson, apps.py):

```python
# instances/nelson/apps.py
class NelsonConfig(AppConfig):
    def ready(self):
        from shopman.refs import register_ref_type
        from .ref_types import MESA, COMANDA, SENHA, IFOOD_ORDER
        for rt in [MESA, COMANDA, SENHA, IFOOD_ORDER]:
            register_ref_type(rt)
```

### Para o admin:

```python
# Qualquer admin que queira mostrar refs
from shopman.refs.contrib.admin_unfold.admin import RefInline

class OrderAdmin(ModelAdmin):
    inlines = [RefInline]
```

---

## Ordem de execução

| WP | Conteúdo | Depende de | Esforço |
|----|----------|------------|---------|
| REF-01 | Models + Types + Registry | — | médio |
| REF-02 | Services (attach, resolve, etc.) | 01 | médio |
| REF-03 | Bulk operations | 02 | médio |
| REF-04 | Signals + Generators | 02 | pequeno |
| REF-05 | RefField + RefSourceRegistry | 01, 03 | médio |
| REF-06 | Admin Unfold | 02 | médio |
| REF-07 | Management commands | 03 | pequeno |
| REF-08 | Migração contrib/refs → pacote | 01-04 | médio |
| REF-09 | RefField nos models existentes | 05, 08 | pequeno |

Paralelizáveis: REF-01 sozinho → {REF-02, REF-04} paralelos → {REF-03, REF-05} paralelos → {REF-06, REF-07, REF-08} paralelos → REF-09

---

## Decisões de design

1. **Sem GenericForeignKey** — `target_type` + `target_id` são strings puras. Sem dependência em `contenttypes`.
2. **Sem ...man** — é `shopman.refs`, uma biblioteca genérica como `shopman.utils`.
3. **RefField = CharField** — zero migration, zero schema change. A inteligência é no registry, não no banco.
4. **RefTypes em código, não no banco** — frozen dataclasses, versionáveis, imutáveis. Instâncias registram no `ready()`.
5. **Audit via campos no model** — `actor`, `deactivated_at`, `deactivated_by`. Sem tabela de eventos separada (simplicidade).
6. **Signals opcionais** — emitidos mas ninguém é obrigado a escutar.

---

## Referências

- Implementação atual: `packages/orderman/shopman/orderman/contrib/refs/`
- Memory: `.auto-memory/project_refs_evolution.md`
- Convenção `ref not code`: CLAUDE.md
