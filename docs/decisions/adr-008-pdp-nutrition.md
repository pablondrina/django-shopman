# ADR-008: Ingredientes e informação nutricional no PDP — Product é superfície, Recipe é fonte opcional

**Status:** Aceito
**Data:** 2026-04-17
**Contexto:** O storefront precisa exibir "Ingredientes" e "Informações Nutricionais" no PDP. Havia dúvida entre armazenar em `Offerman.Product` (simples, duplica) ou derivar em tempo real de `Craftsman.Recipe` (fonte única, caro). Referência: [`docs/plans/PDP-DATA-FIELDS-PLAN.md`](../plans/PDP-DATA-FIELDS-PLAN.md).

---

## Contexto

Dois domínios são legítimos candidatos a segurar esses dados:

- **Offerman.Product** — a superfície vendável, o que o storefront já consulta.
- **Craftsman.Recipe / RecipeItem** — a ficha técnica de produção; ingredientes moram aqui naturalmente como `RecipeItem.input_ref`.

Cada alternativa pura é frágil:

- **Só em Product:** duplica informação e abre caminho para divergência quando a receita muda. Obriga operador a manter dois pontos de verdade.
- **Só derivado de Recipe on-read:** computação cara no hot path do PDP, não cobre produtos **revendidos** (sem receita) e exige que a projeção conheça o domínio de produção.

Há também um terceiro sujeito silencioso: **bundles**. Um combo não tem receita própria — sua composição é a soma das partes. Derivar nutricional de bundle é cirurgicamente difícil de acertar (porções diferentes, unidades diferentes, contaminação cruzada) e errar rotulagem alimentar é risco regulatório.

## Decisão

**Híbrido, com Product como superfície e derivação materializada opcional.**

1. `Offerman.Product` ganha dois campos de **dado final, já pronto para exibir**:
   - `ingredients_text` (`TextField`, blank=True) — lista humana pt-BR, ordem decrescente de peso (exigência ANVISA RDC 360/2003).
   - `nutrition_facts` (`JSONField`, blank=True, default=dict) — dict serializado de um `dataclass NutritionFacts` frozen.

2. A projeção `ProductDetailProjection` consome **só esses dois campos**. Ingrediente e nutricional nunca são computados em tempo de request. O PDP é uma leitura fria.

3. Produtos **com** Recipe ativa têm derivação opt-in, materializada em escrita:
   - Service `shopman.shop.services.nutrition_from_recipe.fill_nutrition_from_recipe(product)` lê a receita ativa (`Recipe.output_ref == product.sku`, `is_active=True`), soma o perfil nutricional de cada `RecipeItem` (armazenado em `RecipeItem.meta["nutrition"]`), gera `ingredients_text` a partir de `RecipeItem.meta["label"]` em ordem decrescente de peso, e escreve de volta em `Product`.
   - Signal `post_save` em `Recipe` dispara o service após o save da receita.
   - Um flag `nutrition_facts["auto_filled"]` distingue valores derivados de override manual — o service só sobrescreve se o valor atual **não** for `auto_filled=False`.
   - Management command `fill_nutrition_from_recipe` faz backfill em lote.

4. Produtos **sem** Recipe (revendidos, combos, bebidas) são editáveis direto no admin com um form Unfold dedicado, um campo por nutriente, agrupado em fieldsets ("Porção", "Macronutrientes", "Micronutrientes"). JSON raw nunca aparece no admin.

5. **Bundles ficam de fora da derivação.** Produtos `is_bundle=True` não têm receita associada e a soma aritmética de nutricional de componentes é frágil demais para rotulagem alimentar — preferimos **nada** a **errado**. Se o operador quiser rotular nutricionalmente um combo, preenche manualmente no admin.

6. `Product.clean()` valida invariantes ANVISA estruturais:
   - Se **qualquer** campo nutricional está presente, `serving_size_g` é obrigatório.
   - Todos os campos numéricos são ≥ 0.
   - `trans_fat_g ≤ total_fat_g`, `saturated_fat_g ≤ total_fat_g`, `sugars_g ≤ carbohydrates_g`.

## O teste diagnóstico

Quando um campo novo de exibição precisa morar em Product vs derivar de Recipe:

| Sinal | Resposta |
|---|---|
| Precisa renderizar sem tocar outro domínio | Product carrega o dado final |
| Dados estruturais (BOM, quantidades, receita) que já moram em Recipe | Recipe continua dona |
| Derivação tem custo e é escrita rara | Materialize no Product via signal em Recipe |
| Produtos sem receita também precisam do campo | Product ganha o campo, com derivação opt-in |

`ingredients_text` + `nutrition_facts` satisfazem todos os sinais.

## Consequências

### Positivas

- **Leitura fria no PDP.** Projeção nunca importa `craftsman`.
- **Uma fonte de verdade por produto:** ou o operador edita (manual) ou a Recipe edita via signal. Flag `auto_filled` evita stomp.
- **Compatível com revendidos/bebidas/combos.** Não exige receita para ter rotulagem.
- **Compatível com operador que não usa Recipe.** Basta preencher no admin.
- **Rotulagem alimentar correta por padrão.** Bundle não alucina nutricional.

### Negativas

- **Dois pontos de verdade potenciais** para produtos com receita: se o operador edita a Recipe e também manualmente o Product, o flag `auto_filled=False` bloqueia sobrescrita — o operador precisa **saber** disso. Mitigação: admin expõe um toggle "derivado da receita" (próximo WP, não agora) e a história é visível em `HistoricalRecords`.
- **Soma nutricional correta depende da qualidade de `RecipeItem.meta["nutrition"]`.** Se o operador não preenche o perfil do insumo, o service gera `{}`. Isso é OK — vazio é melhor que chute.

### Mitigações

- Esta ADR existe.
- `Product.clean()` bloqueia estados incoerentes (campos sem `serving_size_g`, trans > total).
- Signal é idempotente (`auto_filled=True` é o único sinal verde para sobrescrita).
- Management command `fill_nutrition_from_recipe` permite backfill controlado.

## Alternativas consideradas

### A. Campo direto em Product, sem derivação automática

Rejeitada. Força o operador a manter rotulagem nutricional em dois pontos (Recipe para BOM, Product para PDP). Divergência inevitável em produção.

### B. Derivação on-read na projeção

Rejeitada. Custo de I/O no hot path do PDP, não cobre revendidos, e obriga a projeção a importar Craftsman — quebra a fronteira de domínio.

### C. Insumo como entidade (novo modelo Stockman.Ingredient)

Rejeitada **por ora**. `RecipeItem.input_ref` é string ref hoje; `RecipeItem.meta` é JSON extensível. Guardar o perfil nutricional do insumo em `meta["nutrition"]` resolve o problema sem migração de modelo novo. Se o domínio pedir um Ingredient first-class depois (fornecedor, lote, rotulagem regulatória própria), abre-se outro ADR.

### D. Cálculo nutricional para bundles

Rejeitada. Rotulagem alimentar errada é risco regulatório; preferimos deixar vazio.

## Referências

- [`docs/plans/PDP-DATA-FIELDS-PLAN.md`](../plans/PDP-DATA-FIELDS-PLAN.md)
- [`packages/offerman/shopman/offerman/nutrition.py`](../../packages/offerman/shopman/offerman/nutrition.py) — dataclass `NutritionFacts`
- [`shopman/shop/services/nutrition_from_recipe.py`](../../shopman/shop/services/nutrition_from_recipe.py) — derivação
- [`shopman/shop/projections/product_detail.py`](../../shopman/shop/projections/product_detail.py) — leitura
- ANVISA RDC 360/2003 — rotulagem nutricional obrigatória no Brasil
