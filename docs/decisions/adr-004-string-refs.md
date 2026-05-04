# ADR-004: String refs para identificadores cross-domain

**Status:** Aceito
**Data:** 2026-04-14 (consolidação)
**Supera:** versões de 2025-01-20 (craftsman) e 2026-03-18 (stockman)

---

## Contexto

Vários cores precisam referenciar "coisas" do domínio de catálogo (produtos,
insumos, materiais) sem importar o offerman. Craftsman referencia o que entra
e sai de uma receita. Stockman referencia o que está em estoque. Orderman
referencia o que o cliente comprou.

A pergunta é: **como nomear esses ponteiros sem criar dependência entre cores?**
Uma FK direta para `offerman.Product` violaria ADR-001 (cores não se importam).
`GenericForeignKey` resolve o acoplamento mas adiciona JOIN em `django_content_type`
por query e cria inconsistência (API usa string, modelo usa par `(ct, id)`).

## Decisão

### 1. Identificadores textuais são strings planas indexadas

Cada core guarda o identificador como `CharField` indexado. O nome do campo
segue a taxonomia canônica (ver `docs/constitution.md` §3.1):

- **`sku`** — identificador estável de produto vendável/estocável. Usado em
  `offerman.Product.sku`, `stockman.Quant.sku`, `stockman.Hold.sku`,
  `orderman.OrderItem.sku`.
- **`ref`** — identificador textual de entidade do próprio core (ex.:
  `Order.ref`, `Session.ref`, `Customer.ref`).
- **`*_ref`** — ponteiro textual para entidade externa ao core, quando o alvo
  **não é necessariamente** um SKU do catálogo (ver craftsman abaixo).

```python
# packages/stockman/shopman/stockman/models/quant.py
class Quant(models.Model):
    sku = models.CharField(max_length=100, db_index=True)

# packages/orderman/shopman/orderman/models.py
class OrderItem(models.Model):
    sku = models.CharField(max_length=100)
```

### 2. Craftsman usa refs textuais para BOM

Uma receita pode referenciar produto vendável, insumo catalogado ou subproduto:
`CROISSANT`, `FARINHA-T55`, `AGUA`, `FERMENTO-NATURAL`. Esses ponteiros não
viram FK para `offerman.Product`; Craftsman armazena refs textuais e resolve
via adapter quando precisa de nome, unidade ou estado comercial.

```python
# packages/craftsman/shopman/craftsman/models.py
class Recipe(models.Model):
    output_sku = RefField(ref_type="SKU", max_length=100)   # "CROISSANT"

class RecipeItem(models.Model):
    input_sku = RefField(ref_type="SKU", max_length=100)    # "FARINHA-T55"

class WorkOrderItem(models.Model):
    item_ref = CharField(max_length=100)     # insumo, produto ou perda
```

A resolução `output_sku → offerman.Product` é feita pelo framework via
adapter (`PricingBackend` / catálogo), em runtime, não por FK.

### 3. Validação é responsabilidade do framework

Sem FK o banco não impede typos (`FARIHNA-T55`). A validação acontece na
borda onde o dado entra: services do framework e adapters validam SKU contra
o catálogo antes de persistir. Testes de invariante garantem que o contrato
`sku` é consistente entre cores.

### 4. `shopman-refs` é oficial, mas não obrigatório para todo kernel

`shopman-refs` fornece registro, geração e resolução de refs para projetos que
querem essa conveniência. Kernels que só precisam armazenar uma string usam
`shopman.utils.refs.RefField`, que decompõe como `django.db.models.CharField`.

Quando `shopman-refs` está instalado, esse wrapper usa o `RefField` real e
participa do registry. Quando não está, ele cai para um `CharField` compatível.
Assim, `refs` é cidadão de primeira classe na suíte composta, mas não vira
dependência invisível para kernels que continuam semanticamente standalone.

## Consequências

### Positivas

- **Desacoplamento real:** stockman, orderman e craftsman não importam offerman.
  Trocar o catálogo não toca nos outros cores.
- **Sem JOINs parasitas:** query por `sku` é direta, sem `django_content_type`.
- **Consistência cross-core:** o mesmo conceito (produto vendável) tem o mesmo
  nome (`sku`) em todos os cores que o manipulam.
- **Serializers diretos:** API externa já fala `sku` — não precisa traduzir
  de/para `(content_type, object_id)`.

### Negativas

- **Sem integridade referencial no banco:** typos só são pegos em runtime.
- **Resolução manual:** para obter nome/unidade de um `sku`, um service precisa
  chamar o adapter de catálogo.

### Mitigações

- Services do framework validam `sku` contra o catálogo na borda de entrada.
- Testes cruzados (`shopman/shop/tests/test_invariants.py`) garantem que
  os SKUs usados em fluxos reais existem no offerman.
- Craftsman tem `CatalogProtocol.resolve()` para mapear `output_sku → Product`
  quando o output **é** um vendável.

## Atualização 2026-04-30: Receita ativa por SKU é determinística

O Craftsman atual usa os nomes `output_sku` e `input_sku`, ainda como
`RefField(ref_type="SKU")`, para deixar explícito que a integração com
Offerman acontece por SKU textual e não por FK.

A regra operacional agora é: um `output_sku` pode ter **no máximo uma**
`Recipe` ativa. Alternativas, sazonalidade ou múltiplas rotas de produção não
devem ser modeladas como várias receitas ativas concorrentes; quando isso for
necessário, a suíte deve ganhar uma entidade explícita de rota/seletor.

Consequências práticas:

- serviços resolvem receita por `get_active_recipe_for_output_sku()`, não por
  `.first()` implícito;
- `Recipe` mantém uma constraint parcial de unicidade para `output_sku` ativo;
- combos/bundles continuam pertencendo à composição comercial de Offerman
  (`ProductComponent`) e não devem ser saída direta de `Recipe`.

## Histórico

- 2025-01-20: Decisão original — craftsman adota `*_ref` como string livre;
  stockman ainda usa `GenericForeignKey`.
- 2026-03-18: Revisão reconhece inconsistência — stockman precisa migrar.
- 2026-04-14: Migração de stockman concluída. Todos os cores usam string
  indexada (`sku` ou `*_ref`). Esta ADR consolida o estado final.
- 2026-04-30: Craftsman endurece o contrato para uma receita ativa por
  `output_sku` e resolução centralizada.

## Referências

- ADR-001: independência dos cores
- `docs/constitution.md` §3.1: taxonomia de identificadores (uuid/ref/sku/handle)
