# PDP-DATA-FIELDS-PLAN — Ingredientes + Informações Nutricionais

> **Objetivo:** trazer "Ingredientes" e "Informações Nutricionais" para o
> accordion "Alérgenos & info" no PDP. Decidir **onde** esses dados moram
> antes de escrever qualquer template ou projeção.

## Estado atual (verificado)

### Já existem no DB
- `Offerman.Product.unit_weight_g` (PositiveIntegerField) — peso por unidade.
  **Já é projetado** como `product.conservation.unit_weight_label` (`"~250g a unidade"`)
  em `projections/product_detail.py`. Hoje está **enterrado no accordion de
  conservação** — precisa ir para junto do preço.
- `Offerman.Product.shelf_life_days`, `storage_tip` — validade + dica.
- `Offerman.Product.metadata` (JSONField) — extensível.
- Alérgenos vêm de `Offerman.Product.keywords` / `_allergen_info()` no
  helper. Já visíveis como badge inline e no accordion.

### Ausentes
- **Ingredientes** — lista ordenada de ingredientes em pt-BR, texto humano.
  Ex: "Farinha de trigo, água, fermento natural, sal marinho".
- **Informações nutricionais** — tabela padrão ANVISA por porção.

## Discussão: onde esses dados moram?

Duas opções legítimas. Precisa de decisão do Pablo antes de implementar.

### Opção A — `Offerman.Product` direto

Campos novos em Product (ou via `metadata` JSONField com dataclass).

**Prós:**
- Simples: o PDP já consulta Product.
- Funciona para produtos que **não são produzidos internamente** (revendidos).

**Contras:**
- Duplica informação quando o produto vem de uma receita que já tem a BOM.
  Mudança na receita não propaga.

### Opção B — Derivado de `Craftsman.Recipe`

Receita produz produto; BOM da receita tem os insumos; ficha técnica do
insumo tem nutricional. Produto mostra info derivada.

**Prós:**
- Fonte única de verdade. Mudança na receita atualiza PDP.
- Respeita domínio: craftsman manda em produção, oferta mostra.

**Contras:**
- Nem todo produto tem receita (itens revendidos).
- Computação mais cara — precisa cache ou view materializada.

### Decisão aprovada (2026-04-17): Opção Híbrida

**Pablo aprovou a recomendação híbrida** — execução liberada para os WPs
abaixo.

**Híbrido, com Product como superfície:**
- Product ganha `ingredients_text` e `nutrition_facts` (JSON dataclass).
- Produtos com receita: *trigger/serviço* preenche esses campos ao salvar
  a Recipe (derivação materializada, não computação on-read).
- Produtos sem receita: editáveis direto no admin do Product.
- **Resultado:** uma única leitura (`Product.ingredients_text`), fonte
  configurável.

Padrão `feedback_dataclass_driven_admin` já aprovado — dataclass + admin
form + `clean()` de validação.

## Schema proposto (para aprovação)

### `ingredients_text` — TextField

Lista humana, pt-BR, ordenada por peso decrescente (ANVISA requer isso).
Sem estrutura rígida — texto simples que o operador digita.

```
Farinha de trigo, água, fermento natural, sal marinho, açúcar mascavo.
CONTÉM: glúten. PODE CONTER: leite, ovo, soja (contaminação cruzada).
```

### `nutrition_facts` — JSONField (dataclass-driven)

```python
@dataclass(frozen=True)
class NutritionFacts:
    serving_size_g: int              # "Porção: 50g (1 unidade)"
    servings_per_container: int = 1

    energy_kcal: float | None = None
    carbohydrates_g: float | None = None
    sugars_g: float | None = None
    proteins_g: float | None = None
    total_fat_g: float | None = None
    saturated_fat_g: float | None = None
    trans_fat_g: float | None = None
    fiber_g: float | None = None
    sodium_mg: float | None = None
    # %VD calculado pela view com base em DRV padrão (2000 kcal)
```

Validação em `Product.clean()`:
- Se houver qualquer campo nutricional, `serving_size_g` é obrigatório.
- Valores ≥ 0, trans_fat_g ≤ total_fat_g, etc.

Admin renderiza com form dedicado (um campo por linha, agrupado por
categoria), não JSON raw.

## Peso por unidade — exibir próximo ao preço — **FEITO**

Mudança aplicada 2026-04-17:
- `ProductDetailProjection.unit_weight_label` agora é top-level (antes
  estava mal-localizado em `ConservationInfoProjection.unit_weight_label`).
- Template PDP mostra `~250g a unidade` logo abaixo do preço.

## Conservação — incorporada no PDP (sem link externo) — **FEITO**

Mudança aplicada 2026-04-17:
- Seção "Conservação" agora mora **dentro** do accordion "Alérgenos & info"
  no PDP (não como card separado com link para `/dicas`).
- `Shop.conservation_tips_default` (TextField) exposto no admin Unfold —
  copy padrão da loja.
- `Product.storage_tip` é **override por SKU**. Projeção resolve cascata:
  `storage_tip` do produto → `conservation_tips_default` da loja → vazio.
- Migração `0003_shop_conservation_tips_default.py` criada.

## Plano de execução

### WP-PDP-DATA-1 — decidir onde moram

- Pablo decide: Opção A, B ou híbrido.
- Documentar ADR em `docs/decisions/adr-XXX-pdp-nutrition.md`.

### WP-PDP-DATA-2 — schema + migração

- Adicionar `ingredients_text` e `nutrition_facts` (ou campos equivalentes)
  em Product.
- Criar dataclass `NutritionFacts` com validação.
- Admin form dedicado.
- Migration.

### WP-PDP-DATA-3 — projeção + UI

- `projections/product_detail.py` — expor `ingredients`, `nutrition` como
  objetos tipados.
- Template `product_detail.html` — adicionar `<details>` para Ingredientes
  e `<details>` para Informações Nutricionais no accordion existente.
- Exibir `unit_weight_label` próximo ao preço (mudança imediata).

### WP-PDP-DATA-4 — seed/backfill

- Comando `fill_nutrition_from_recipe` para produtos com receita ativa.
- Atualizar seed Nelson (`make seed`) com dados reais.

## Referências

- ANVISA RDC 360/2003 — rotulagem nutricional obrigatória no Brasil.
- [`project_pdp_data_fields_pending.md`](../../_/memory) — memória durável.
