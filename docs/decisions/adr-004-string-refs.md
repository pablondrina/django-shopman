# ADR-004: String refs vs GenericForeignKey

**Status:** Aceito (crafting); Em revisao (stocking)
**Data:** 2025-01-20 (crafting), 2026-03-18 (revisao stocking)
**Contexto:** Como referenciar produtos/materiais sem acoplar ao catalogo

---

## Contexto

Tanto crafting quanto stocking precisam referenciar "coisas" (produtos, insumos, materiais) sem depender do offering (catalogo). Duas abordagens foram usadas:

1. **crafting:** `output_ref` / `input_ref` / `item_ref` — CharField(100) com string livre
2. **stocking:** `content_type` + `object_id` — GenericForeignKey do Django

O crafting usa `_ref` (nao `_sku`) deliberadamente: uma receita pode referenciar materias-primas que nao sao SKUs do catalogo (`FARINHA-T55`, `AGUA`, `FERMENTO-NATURAL`). O adapter faz o mapeamento quando necessario.

## Decisao

### crafting: string refs (correto, manter)

```python
class Recipe(models.Model):
    output_ref = CharField(max_length=100)  # "CROISSANT", "PAO-FRANCES"

class RecipeItem(models.Model):
    input_ref = CharField(max_length=100)   # "FARINHA-T55", "MANTEIGA"

class WorkOrderItem(models.Model):
    item_ref = CharField(max_length=100)    # insumo, produto ou perda
```

A resolucao `output_ref -> SKU do offering` e feita pelo `CatalogProtocol.resolve()` em runtime, nao por FK.

### stocking: GenericForeignKey (funciona, mas inconsistente)

```python
class Quant(models.Model):
    content_type = ForeignKey(ContentType)
    object_id = PositiveIntegerField()
    product = GenericForeignKey()
```

A API externa do stocking ja usa `sku` (string) nos serializers e views. O GFK e um detalhe interno que adiciona JOINs desnecessarios.

### Recomendacao para stocking: migrar para SKU string

```python
# Futuro
class Quant(models.Model):
    sku = CharField(max_length=100, db_index=True)
```

A migracao deve ser feita quando houver janela, pois requer:
1. Adicionar campo `sku` (nullable)
2. Data migration: popular `sku` a partir do GFK
3. Remover campos GFK
4. Tornar `sku` NOT NULL

## Consequencias

### String refs (crafting)

**Positivas:**
- **Desacoplamento total:** crafting nao sabe o que e um Product. Pode referenciar qualquer coisa
- **Sem JOINs:** Query direta por string, sem ContentType
- **Portabilidade:** Se trocar offering por outro catalogo, zero impacto no crafting
- **Consistente com a suite:** ordering usa `sku` (string) em OrderItem e SessionItem

**Negativas:**
- **Sem integridade referencial:** `input_ref="FARIHNA-T55"` (typo) nao e detectado pelo banco
- **Resolucao manual:** Precisa chamar `CatalogProtocol.resolve()` para obter nome, unidade etc.

### GenericForeignKey (stocking atual)

**Positivas:**
- **Integridade referencial:** O banco garante que o objeto existe
- **Flexibilidade de tipo:** Pode apontar para Product, Component, ou qualquer model

**Negativas:**
- **Performance:** JOIN em `django_content_type` para cada query
- **Inconsistencia:** API usa `sku` (string), models usam GFK. Conversao em todo serializer
- **Acoplamento ao Django:** GenericForeignKey e especifico do Django ORM
- **Complexidade:** `content_type_id` + `object_id` sao 2 campos para representar 1 conceito

### Mitigacao

- Validacao de SKU via `SkuValidator` protocol (stocking ja tem) compensa a falta de FK
- Migracao GFK -> string e backwards-compatible: API externa nao muda (ja usa `sku`)
