# DECOUPLING-PLAN — Desacoplamento Framework ↔ Kernel

> Plano de execução para desacoplar services/handlers do framework dos packages do kernel,
> mover Channel para o framework, e preparar a base para UI separation futura.

---

## Contexto

O framework (`framework/shopman/`) importa diretamente de 5 packages do kernel:
- **Omniman** (28 imports) — obrigatório, é o motor de pedidos
- **Offerman** (14 imports) — catálogo, deveria ser substituível
- **Guestman** (8 imports) — clientes, deveria ser opcional
- **Craftsman** (5 imports) — produção, deveria ser opcional
- **Stockman** (6 imports) — **já desacoplado via adapter**

Além disso, o `Channel` model vive no Omniman mas é conceito operacional,
não de pedidos. Deve morar ao lado de Shop e ChannelConfig no framework.

### Decisões arquiteturais (2026-04-10)

1. Channel sai do Omniman → framework (ao lado de Shop)
2. ChannelConfigRecord eliminado — config vira JSONField no Channel
3. Channel.get_config() retorna ChannelConfig dataclass (value object passivo)
4. Omniman → Orderman (rename, pode ser fase posterior)
5. Services/handlers usam adapters, nunca importam kernel direto
6. Web views/API mantêm imports diretos (serão movidos para channel apps em plano futuro)

---

## Fase 1 — Adapter Decoupling (services + handlers)

### WP-D1: CatalogAdapter (Offerman)

**Criar** `framework/shopman/adapters/catalog.py`

Interface necessária (baseada no uso real em services/handlers):

```python
# Pricing
def get_price(sku, qty=1, channel=None) -> int:
    """Preço em centavos. Delega para CatalogService.price()."""

# Bundle expansion
def expand_bundle(sku, qty) -> list[dict]:
    """Expande bundle em componentes. Retorna [{"sku": str, "qty": Decimal}]."""

# Product lookup
def get_product_base_price(sku) -> int:
    """Preço base do produto (sem tiers). Retorna centavos."""

# Listing lookup
def get_listing_item(sku, listing_ref) -> dict | None:
    """Retorna {"price_q": int, "min_qty": int, "is_sellable": bool} ou None."""

def find_listing_tiers(sku, listing_ref) -> list[dict]:
    """Tiers de preço por quantidade. Retorna [{"min_qty": int, "price_q": int}] desc."""
```

**Atualizar:**
- `services/pricing.py` — usar `get_adapter("catalog")`
- `services/availability.py` — usar `get_adapter("catalog")`
- `services/stock.py` — usar `get_adapter("catalog")`
- `handlers/pricing.py` — usar `get_adapter("catalog")`

**Registrar** em `adapters/__init__.py`:
```python
_SETTINGS_MAP["catalog"] = "SHOPMAN_CATALOG_ADAPTER"
_DEFAULTS["catalog"] = "shopman.adapters.catalog"
```

---

### WP-D2: ProductionAdapter (Craftsman)

**Criar** `framework/shopman/adapters/production.py`

Interface necessária:

```python
# Work order lookup
def get_work_order(code) -> dict | None:
    """Retorna {"code", "quantity", "output_ref", "produced", "recipe_name"} ou None."""

# Work order event query
def count_adjusted_events(work_order_code) -> int:
    """Conta eventos ADJUSTED de uma work order."""
```

**Atualizar:**
- `services/production.py` — usar `get_adapter("production")`
- `production_flows.py` — usar `get_adapter("production")`

**Registrar** em `adapters/__init__.py`:
```python
_SETTINGS_MAP["production"] = "SHOPMAN_PRODUCTION_ADAPTER"
_DEFAULTS["production"] = "shopman.adapters.production"
```

---

### WP-D3: CustomerAdapter (Guestman)

**Criar** `framework/shopman/adapters/customer.py`

Interface necessária:

```python
# Customer CRUD
def get_customer_by_phone(phone) -> dict | None:
    """Retorna {"ref", "first_name", "last_name", "phone"} ou None."""

def create_customer(ref, first_name, last_name, phone, customer_type, source_system) -> dict:
    """Cria cliente. Retorna {"ref", "first_name", "last_name", "phone"}."""

def update_customer(ref, first_name=None, last_name=None) -> None:
    """Atualiza dados do cliente."""

# Identifiers (external providers: manychat, ifood)
def get_customer_by_identifier(identifier_type, identifier_value) -> dict | None:
    """Busca cliente por identificador externo. Retorna {"ref", ...} ou None."""

def create_identifier(customer_ref, identifier_type, identifier_value, is_primary=True, source_system=None) -> None:
    """Cria identificador externo para cliente."""

# Timeline
def log_timeline_event(customer_ref, event_type, title, description="", channel="", reference="", metadata=None, created_by="system") -> None:
    """Registra evento na timeline do cliente."""

def has_timeline_event(customer_ref, event_type, reference) -> bool:
    """Verifica se evento já existe (idempotência)."""

# Insights
def recalculate_insights(customer_ref) -> None:
    """Recalcula insights do cliente (RFM, etc.)."""

# Addresses
def has_address(customer_ref, formatted_address) -> bool:
    """Verifica se endereço já existe."""

def create_address(customer_ref, label, formatted_address, is_default=False) -> None:
    """Salva endereço do cliente."""

# Preferences
def get_preferences(customer_ref, category) -> list[dict]:
    """Retorna [{"key": str, "value": str}]."""

def set_preference(customer_ref, category, key, value, preference_type="explicit", confidence=1.0, source="checkout") -> None:
    """Salva preferência."""

# Loyalty
def enroll_loyalty(customer_ref) -> None:
    """Inscreve cliente no programa de fidelidade."""

def earn_points(customer_ref, points, description, reference, created_by="system") -> None:
    """Credita pontos."""

def redeem_points(customer_ref, points, description, reference, created_by="system") -> None:
    """Debita pontos."""
```

**Atualizar:**
- `services/customer.py` — usar `get_adapter("customer")`
- `services/checkout_defaults.py` — usar `get_adapter("customer")`
- `handlers/loyalty.py` — usar `get_adapter("customer")`

**Registrar** em `adapters/__init__.py`:
```python
_SETTINGS_MAP["customer"] = "SHOPMAN_CUSTOMER_ADAPTER"
_DEFAULTS["customer"] = "shopman.adapters.customer"
```

---

### WP-D4: Testes + Lint

- Rodar `make test` — todos os 2.265+ testes devem passar
- Rodar `make lint` — zero warnings
- Verificar que nenhum service/handler importa diretamente de offerman/craftsman/guestman
- Commit: `feat(DECOUPLING): adapter pattern for catalog, production, customer`

---

## Fase 2 — Channel Move + Shop+Channel+ChannelConfig coesão

### WP-D5: Channel model → framework

- Criar `framework/shopman/models/channel.py` com os campos do Channel atual do Omniman
  **mais** `config = JSONField(default=dict)` e `shop = FK(Shop)`
- Adicionar `get_config() -> ChannelConfig` no Channel model (cascata: defaults → shop → config)
- Migration framework: criar tabela `shopman_channel`
- **Data migration**: copiar dados de `omniman_channel` → `shopman_channel`

### WP-D6: Omniman desacopla de Channel

- `Session.channel` FK → `Session.channel_ref` CharField
- Migration Omniman: remover FK, adicionar CharField, data migration para copiar refs
- Remover `Channel` model do Omniman
- Atualizar todos os imports no Omniman que usam Channel

### WP-D7: Eliminar ChannelConfigRecord

- Migrar dados: `ChannelConfigRecord.data` → `Channel.config` para cada canal
- Remover model `ChannelConfigRecord`
- Remover migration
- `config.py`: ChannelConfig dataclass fica como value object passivo
  - Remover `for_channel()` classmethod
  - Manter `from_dict()`, `to_dict()`, `defaults()`, `validate()`

### WP-D8: Admin — Channel com fieldsets tipados

- Channel inline no Shop admin (ou listagem própria)
- Form gerado a partir do ChannelConfig dataclass (padrão dataclass-driven)
- Fieldsets por aspecto: Confirmação, Pagamento, Fulfillment, Stock, etc.
- `Literal` → Select, `int` → NumberInput, `bool` → Toggle

### WP-D9: Testes + Lint Fase 2

- Rodar `make test` — garantir que tudo passa
- Verificar cascata: Channel.get_config() resolve corretamente
- Verificar admin: editar config de canal funciona
- Commit: `feat(DECOUPLING-F2): Channel in framework, ChannelConfigRecord eliminated`

---

## Fase 3 — Omniman → Orderman rename (opcional, pode ser separada)

### WP-D10: Rename package

- `packages/omniman/` → `packages/orderman/`
- Namespace: `shopman.omniman` → `shopman.orderman`
- App label: `omniman` → `orderman` (com migration rename)
- Settings key: `OMNIMAN` → `ORDERMAN`
- Atualizar todos os imports, docs, testes, settings

### WP-D11: Testes + Lint Fase 3

- Rodar full suite
- Commit: `feat(RENAME): Omniman → Orderman`

---

## Checklist de validação por WP

Cada WP deve:
- [ ] Não quebrar nenhum teste existente
- [ ] Não introduzir imports diretos de kernel em services/handlers
- [ ] Passar `make lint` limpo
- [ ] Ser commitável independentemente

---

## Fora de escopo (planos futuros)

- **UI Separation** (storefront, POS → `channels/` apps) — plano próprio, pós-decoupling
- **KDS/Dashboard** migração para Unfold — plano próprio
- **Payman conf.py** — feature work, não cleanup
- **Diretório rename** (`framework/` → `application/`) — cosmético, decidir depois
