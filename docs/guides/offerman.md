# Offerman — Catálogo, Oferta e Projeção

## Visão Geral

O app `shopman.offerman` é o domínio de oferta comercial da suite. Ele gerencia produtos, coleções, listings e preços por canal. A API pública é o `CatalogService`.

`offerman` trata **somente** da oferta comercial. Exposição e vigência vivem aqui; disponibilidade prometível vem de `stockman`.

## Conceitos

### Produto (`Product`)
Unidade vendável com SKU único, preço base em centavos (`base_price_q`), unidade de medida e política de disponibilidade.

### Política de Disponibilidade (`AvailabilityPolicy`)
Diretriz para apps downstream (Stocking, Crafting):
- `stock_only` — só vende se tem estoque físico
- `planned_ok` — aceita produção planejada (default)
- `demand_ok` — aceita pré-encomenda/sob demanda

### Bundle
Produto composto por outros produtos. Não há modelo separado — um Product com `components` é um bundle. Validação de profundidade máxima e referências circulares.

### Coleção (`Collection`)
Agrupamento hierárquico de produtos (como categorias). Suporta validade temporal e ordenação.

### Listing
Tabela de preços por canal (WhatsApp, iFood, balcão). Suporta preços por faixa de quantidade (`min_qty`), validade temporal e prioridade.

## Modelos

### Product

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `uuid` | UUIDField | Identificador único |
| `sku` | CharField(100, unique) | Código do produto |
| `name` | CharField(200) | Nome |
| `short_description` | CharField(255) | Descrição curta |
| `long_description` | TextField | Descrição completa |
| `keywords` | TaggableManager | Tags de busca (django-taggit) |
| `unit` | CharField(20, default="un") | Unidade de medida |
| `base_price_q` | BigIntegerField | Preço base em centavos |
| `availability_policy` | CharField(choices) | `stock_only`, `planned_ok`, `demand_ok` |
| `shelf_life_days` | IntegerField(null) | Validade em dias (None=não perecível, 0=consumo no dia) |
| `production_cycle_hours` | IntegerField(null) | Tempo de produção em horas |
| `is_published` | BooleanField | Visível no catálogo |
| `is_sellable` | BooleanField | Elegível comercialmente para venda |
| `image_url` | URLField | URL da imagem |
| `is_batch_produced` | BooleanField | Produção em lote |
| `metadata` | JSONField | Dados customizados |
| `created_at` / `updated_at` | DateTimeField | Timestamps |
| `history` | HistoricalRecords | Auditoria (simple-history) |

**Propriedades:**
- `base_price` — Decimal (converte de centavos)
- `is_perishable` — True se `shelf_life_days is not None`
- `is_bundle` — True se tem componentes
- `reference_cost_q` — Custo de produção via CostBackend (read-only)
- `margin_percent` — Margem percentual

**QuerySet:**
- `Product.objects.published()` — publicados
- `Product.objects.sellable()` — elegíveis comercialmente

### ProductComponent

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `parent` | FK(Product, CASCADE) | Produto pai (o bundle) |
| `component` | FK(Product, PROTECT) | Produto componente |
| `qty` | DecimalField(10,3) | Quantidade por unidade do bundle |

Validações: sem auto-referência, sem ciclos, profundidade ≤ `BUNDLE_MAX_DEPTH` (default 5).

### Collection

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `uuid` | UUIDField | Identificador único |
| `ref` | SlugField(50, unique) | Identificador canônico |
| `name` | CharField(100) | Nome |
| `parent` | FK(self, null, CASCADE) | Coleção pai (hierarquia) |
| `valid_from` / `valid_until` | DateField(null) | Validade temporal |
| `sort_order` | IntegerField | Ordenação dentro do pai |
| `is_active` | BooleanField | Ativa |

**Métodos:**
- `is_valid(date=None)` — Verifica se ativa e dentro do período
- `full_path` — Breadcrumb ("Categoria > Subcategoria > Coleção")
- `depth` — Profundidade na hierarquia (0 = raiz)
- `get_ancestors()` / `get_descendants()` — Navegação hierárquica

### CollectionItem

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `collection` | FK(Collection, CASCADE) | Coleção |
| `product` | FK(Product, CASCADE) | Produto |
| `is_primary` | BooleanField | Coleção principal (máximo 1 por produto) |
| `sort_order` | IntegerField | Ordenação |

### Listing

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `uuid` | UUIDField | Identificador único |
| `ref` | SlugField(50, unique) | Código do canal (ex: `whatsapp`, `ifood`) |
| `name` | CharField(100) | Nome |
| `valid_from` / `valid_until` | DateField(null) | Validade temporal |
| `priority` | IntegerField | Prioridade (maior = mais específico) |
| `is_active` | BooleanField | Ativa |

### ListingItem

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `listing` | FK(Listing, CASCADE) | Listing/canal |
| `product` | FK(Product, CASCADE) | Produto |
| `price_q` | BigIntegerField | Preço em centavos |
| `min_qty` | DecimalField(10,3, default=1) | Quantidade mínima para este tier |
| `is_published` | BooleanField | Visível neste canal |
| `is_sellable` | BooleanField | Elegível comercialmente neste canal |
| `history` | HistoricalRecords | Auditoria de preços |

## Serviços

### CatalogService

API pública do catálogo. Todos os métodos são classmethods.

```python
from shopman.offerman import CatalogService, CatalogError
```

#### Consultas

**`CatalogService.get(sku)`** — Busca produto por SKU (ou lista de SKUs).
```python
produto = CatalogService.get("CROISSANT")
produtos = CatalogService.get(["CROISSANT", "BAGUETE"])  # dict {sku: Product}
```

**`CatalogService.price(sku, qty=1, channel=None, listing=None)`** — Preço total em centavos.
```python
total = CatalogService.price("CROISSANT", qty=Decimal("3"), listing="whatsapp")
# Algoritmo: listing price > base_price (fallback)
```

**`CatalogService.get_price(sku, qty=1, channel=None, listing=None, context=None)`** — Preço contextual completo.
```python
price = CatalogService.get_price(
    "CROISSANT",
    qty=Decimal("3"),
    listing="whatsapp",
    context={"customer_segment": "vip"},
)
# ContextualPrice com preço de lista, preço final e ajustes explícitos
```

**`CatalogService.expand(sku, qty=1)`** — Explode bundle em componentes.
```python
componentes = CatalogService.expand("KIT-CAFE", qty=Decimal("2"))
# [{"sku": "CROISSANT", "name": "Croissant", "qty": Decimal("4")}, ...]
```

**`CatalogService.validate(sku)`** — Valida SKU e retorna status.
```python
result = CatalogService.validate("CROISSANT")
# SkuValidation(valid=True, sku="CROISSANT", name="Croissant Tradicional", ...)
```

**`CatalogService.search(query=None, collection=None, keywords=None, limit=20)`** — Busca produtos.
```python
paes = CatalogService.search(collection="paes-salgados")
doces = CatalogService.search(keywords=["doce", "sobremesa"])
```

#### Canal

**`CatalogService.get_sellable_products(listing_ref)`** — Produtos comercialmente elegíveis num canal.
```python
menu_whatsapp = CatalogService.get_sellable_products("whatsapp")
```

**`CatalogService.is_product_sellable(product, listing_ref)`** — Verifica elegibilidade comercial num canal.

#### Projeção

**`CatalogService.get_projection_items(listing_ref)`** — Snapshot canônico da oferta de um canal.
```python
snapshot = CatalogService.get_projection_items("ifood")
# [ProjectedItem(sku="CROISSANT", price_q=790, is_published=True, is_sellable=True, ...), ...]
```

**`CatalogService.project_listing(listing_ref, full_sync=False)`** — Sincroniza a oferta do canal via projection backend.
```python
result = CatalogService.project_listing("ifood")
# ProjectionResult(success=True, projected=42, channel="ifood")
```

**`CatalogService.project_catalogs(listing_refs=None, full_sync=False)`** — Sincroniza múltiplos catálogos externos configurados.
```python
results = CatalogService.project_catalogs()
# {"google": ProjectionResult(...), "meta_ig": ProjectionResult(...), "whatsapp": ProjectionResult(...)}
```

Offerman deve ser a fonte da verdade da oferta comercial também para catálogos externos. Cada destino externo é uma `Listing` canônica (`whatsapp`, `google`, `meta_ig`, `ifood`, etc.) com um `CatalogProjectionBackend` configurado em `OFFERMAN["PROJECTION_BACKENDS"]`. O kernel não conhece APIs específicas de plataforma; adapters no orquestrador ou na instância traduzem `ProjectedItem` para o contrato de Google, WhatsApp, Meta/IG ou marketplace.

## Protocols

### CatalogBackend

Interface para implementações alternativas do catálogo.

```python
class CatalogBackend(Protocol):
    def get_product(self, sku: str) -> ProductInfo | None: ...
    def get_price(self, sku: str, qty: Decimal = Decimal("1"), channel: str | None = None) -> PriceInfo: ...
    def validate_sku(self, sku: str) -> SkuValidation: ...
    def expand_bundle(self, sku: str, qty: Decimal = Decimal("1")) -> list[BundleComponent]: ...
```

### CostBackend

Interface para provedores de custo de produção (ex: Crafting).

```python
class CostBackend(Protocol):
    def get_cost(self, sku: str) -> int | None: ...  # centavos
```

### CatalogProjectionBackend

Interface para projeção da oferta para canais terceiros.

```python
class CatalogProjectionBackend(Protocol):
    def project(self, items: list[ProjectedItem], *, channel: str, full_sync: bool = False) -> ProjectionResult: ...
    def retract(self, skus: list[str], *, channel: str) -> ProjectionResult: ...
```

### Dataclasses

- `ProductInfo(sku, name, description, category, unit, is_bundle, base_price_q, is_published, is_sellable, keywords)`
- `PriceInfo(sku, unit_price_q, total_price_q, qty, listing)`
- `PriceAdjustment(code, label, amount_q, metadata)`
- `ContextualPrice(sku, qty, listing, list_unit_price_q, list_total_price_q, final_unit_price_q, final_total_price_q, adjustments, metadata)`
- `SkuValidation(valid, sku, name, is_published, is_sellable, error_code, message)`
- `BundleComponent(sku, name, qty)`
- `ProjectedItem(sku, name, description, unit, price_q, is_published, is_sellable, category, image_url, keywords, metadata)`
- `ProjectionResult(success, projected, errors, channel)`

## Sinais

| Sinal | Quando | Payload |
|-------|--------|---------|
| `product_created` | Primeiro save de Product | `sender`, `instance`, `sku` |
| `price_changed` | Alteração em ListingItem.price_q | `sender`, `instance`, `listing_ref`, `sku`, `old_price_q`, `new_price_q` |

## Configuração

Chave Django settings: `OFFERMAN`

| Setting | Default | Descrição |
|---------|---------|-----------|
| `MAX_COLLECTION_DEPTH` | 10 | Profundidade máxima de coleções |
| `BUNDLE_MAX_DEPTH` | 5 | Profundidade máxima de bundles |
| `COST_BACKEND` | None | Dotted path para CostBackend |
| `PRICING_BACKEND` | None | Dotted path para `PricingBackend` |
| `PROJECTION_BACKENDS` | `{}` | Mapa `{listing_ref: dotted_path}` para `CatalogProjectionBackend` |

## Exemplos

### Criar produto com preço por canal

```python
from shopman.offerman.models import Product, Listing, ListingItem
from decimal import Decimal

# Criar produto
croissant = Product.objects.create(
    sku="CROISSANT",
    name="Croissant Tradicional",
    base_price_q=850,  # R$ 8,50
    unit="un",
    availability_policy="planned_ok",
    shelf_life_days=1,
)

# Criar listing para WhatsApp
listing_wpp = Listing.objects.create(
    ref="whatsapp",
    name="Menu WhatsApp",
)

# Preço diferenciado no canal
ListingItem.objects.create(
    listing=listing_wpp,
    product=croissant,
    price_q=790,  # R$ 7,90 no WhatsApp
)
```

### Consultar preço com fallback

```python
from shopman.offerman import CatalogService

# Preço no canal (R$ 7,90)
preco_wpp = CatalogService.price("CROISSANT", listing="whatsapp")

# Preço sem canal (fallback para base_price: R$ 8,50)
preco_base = CatalogService.price("CROISSANT")
```

### Cotação contextual

```python
from decimal import Decimal
from shopman.offerman import CatalogService

price = CatalogService.get_price(
    "CROISSANT",
    qty=Decimal("2"),
    listing="whatsapp",
    context={"customer_segment": "vip"},
)

assert price.list_total_price_q >= price.final_total_price_q
```

### Projetar catálogo por canal

```python
from shopman.offerman import CatalogService

result = CatalogService.project_listing("ifood", full_sync=False)
assert result.success is True
```

### Bundle

```python
from shopman.offerman.models import Product, ProductComponent
from decimal import Decimal

kit = Product.objects.create(sku="KIT-CAFE", name="Kit Café da Manhã", base_price_q=2500)
croissant = Product.objects.get(sku="CROISSANT")
cafe = Product.objects.get(sku="CAFE-ESPRESSO")

ProductComponent.objects.create(parent=kit, component=croissant, qty=Decimal("2"))
ProductComponent.objects.create(parent=kit, component=cafe, qty=Decimal("1"))

# Expandir bundle
componentes = CatalogService.expand("KIT-CAFE")
# [{"sku": "CROISSANT", "name": "...", "qty": Decimal("2")},
#  {"sku": "CAFE-ESPRESSO", "name": "...", "qty": Decimal("1")}]
```
