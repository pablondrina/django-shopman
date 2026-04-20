# WP-GAP-10 — Investigação: Exteriorizar Regras de Desconto

> Fase 1 obrigatória. Análise completa das três políticas de stacking de desconto.
> Data: 2026-04-18

---

## 1. Inventário de Modifiers Auditados

Após leitura completa de `shopman/shop/modifiers.py` e `instances/nelson/modifiers.py`, o mapa
real de modifiers de desconto é:

| Order | Código | Arquivo | Política |
|-------|--------|---------|----------|
| 15 | `shop.d1_discount` | `instances/nelson/modifiers.py` | D-1 prioridade absoluta |
| 20 | `shop.discount` | `shopman/shop/modifiers.py` | Maior desconto ganha (promos + cupom) |
| 60 | `shop.employee_discount` | `shopman/shop/modifiers.py` | Desconto funcionário (staff) |
| 65 | `shop.happy_hour` | `instances/nelson/modifiers.py` | Happy Hour, bloqueado por employee |

**Achado crítico**: D-1 e Happy Hour são modifiers **de instância** (`instances/nelson/`), não do
orquestrador (`shopman/shop/`). Isso afeta diretamente o escopo de exteriorização — ver §5.

---

## 2. Política 1 — "Maior Desconto Ganha" (`DiscountModifier`, `shop.discount`)

### 2.1 O que a lógica faz

`DiscountModifier.apply()` coleta candidatos de desconto para cada item do carrinho: promoções
automáticas ativas (excluindo cupom-only) mais, se houver, a promoção do cupom aplicado na sessão.
Para cada item, percorre todos os candidatos calculando o desconto absoluto em centavos
(`_calc_discount(promo, price_q)`), e aplica **apenas o de maior valor**. Itens que já possuem
`modifiers_applied[].type == "d1_discount"` são **pulados integralmente** (D-1 tem precedência
absoluta). Ao final, persiste um resumo em `session.pricing["discount"]` e, se cupom, em
`session.pricing["coupon"]`.

Nota técnica: sem fulfillment_type na sessão (pré-checkout), a promoção é avaliada pela regra da
vitrine (aceita se *algum* tipo permitido fizer match), evitando divergência entre cardápio e
carrinho.

### 2.2 Parâmetros que poderiam variar por instância

Nenhum. Esta política **não tem parâmetros próprios** — os parâmetros (`type`, `value`,
`min_order_q`, `fulfillment_types`, `skus`, `collections`, `customer_segments`, `valid_from`,
`valid_until`) **já vivem nos modelos `Promotion` e `Coupon`** no banco de dados, editáveis via
admin. O comportamento do algoritmo ("maior desconto ganha", "skip D-1") é uma **invariante
matemática do flow**, não um parâmetro de instância.

### 2.3 Risco de exteriorizar

**Risco alto se** a semântica "maior desconto ganha" se tornasse configurável (ex.: "acumula
todos os descontos"). Isso quebraria a invariante de nunca aplicar dois descontos por item,
podendo levar a `unit_price_q < 0`. A regra de skip de D-1 é segurança estrutural.

**Risco irrelevante** para os dados das promoções em si — esses já são externos (Promotion DB).

### 2.4 Proposta

**Manter em código** (Alternativa B parcial para a semântica de stacking) + nenhuma mudança
necessária para os parâmetros de promoção (já estão no DB).

O único "hardcoded" aqui é o **algoritmo de stacking**, que é um invariante matemático correto:
exteriorizar criaria uma armadilha de configuração (stacking acumulativo → crédito negativo).

---

## 3. Política 2 — "D-1 Prioridade Absoluta" (`D1DiscountModifier`, `shop.d1_discount`)

### 3.1 O que a lógica faz

`D1DiscountModifier.apply()` (order=15, Nelson) percorre todos os itens do carrinho. Para cada
item com `is_d1 == True` (via `item["is_d1"]` ou `session.data["availability"][sku]["is_d1"]`),
aplica um desconto percentual fixo sobre `unit_price_q`, registra `modifiers_applied[]` com
`type="d1_discount"`, e persiste totais em `session.pricing["d1_discount"]`.

O efeito de "prioridade absoluta" é indireto: `DiscountModifier` (order=20) pula itens que já
possuem `type == "d1_discount"` em `modifiers_applied`. A ordem de execução (15 antes de 20)
garante que D-1 marca os itens primeiro.

O percentual lê `channel.config.rules.d1_discount_percent` com fallback para o construtor
(default `D1_DISCOUNT_PERCENT = 50`).

### 3.2 Parâmetros que poderiam variar por instância

| Parâmetro | Valor atual | Onde lê hoje | Observação |
|-----------|-------------|--------------|------------|
| `discount_percent` | 50% | `channel.config.rules.d1_discount_percent` → construtor (50) | Já parcialmente exteriorizado via Channel.config |

**Já existe um mecanismo de override por canal** via `Channel.config["rules"]["d1_discount_percent"]`.
O que falta é:
1. Seed com RuleConfig entry para visibilidade no admin.
2. Fallback direto de RuleConfig.params em vez de só via Channel.config.

### 3.3 Risco de exteriorizar

**Baixo**: o percentual é um parâmetro de negócio limpo. O risco real é que alguém configure 0%
ou 100%+ — mitigável com validação no RuleConfig (min=1, max=99).

A semântica de "prioridade" (a marcação `d1_discount` que bloqueia outros) deve permanecer em
código — não é um parâmetro, é a garantia estrutural de que D-1 não acumula com promoções.

### 3.4 Proposta

**Default** (exteriorizar parâmetro, manter semântica em código):
- `RuleConfig(code="discount.d1_percent", params={"discount_percent": 50})` no seed.
- `D1DiscountModifier.__init__` lê `RuleConfig.params` em vez de constante de módulo.
- `Channel.config.rules.d1_discount_percent` pode continuar como override por canal (maior granularidade).
- Semântica de bloqueio (a checagem de `d1_discount` em DiscountModifier) permanece em código.

---

## 4. Política 3 — "Employee Bloqueia Happy Hour" (`HappyHourModifier`, `shop.happy_hour`)

### 4.1 O que a lógica faz

`HappyHourModifier.apply()` (order=65, Nelson) tem duas guards de saída antecipada:
1. Se `session.data["origin_channel"] == "web"` → retorna (evita divergência vitrine/carrinho).
2. Se horário atual NÃO está em `[self.start, self.end)` → retorna.

Para os itens restantes, aplica desconto percentual sobre `unit_price_q` de cada item que **não
possua** `type == "employee_discount"` em `modifiers_applied`. Persiste em
`session.pricing["happy_hour"]`.

O bloqueio de employee é implementado via **verificação passiva no Happy Hour** (ele pula itens
com employee discount), não via lógica ativa no EmployeeDiscountModifier. Como Employee (order=60)
executa antes de Happy Hour (order=65), o efeito é garantido pela ordenação.

**Parâmetros configuráveis hoje:**
- `SHOPMAN_HAPPY_HOUR_START` (settings, default "17:30")
- `SHOPMAN_HAPPY_HOUR_END` (settings, default "18:00")
- Construtor `discount_percent` (default `HAPPY_HOUR_DISCOUNT_PERCENT = 25`)

**Discrepância com docs**: `business-rules.md §6.7` documenta janela "16:00–18:00" e percent 10%,
mas o código Nelson usa 17:30–18:00 e 25%. Isso é uma divergência docs ↔ código que deve ser
corrigida independente da decisão de exteriorização.

### 4.2 Parâmetros que poderiam variar por instância

| Parâmetro | Valor código | Valor docs | Onde lê hoje | Observação |
|-----------|-------------|-----------|--------------|------------|
| `discount_percent` | 25% | 10% | construtor (settings) | Docs e código divergem |
| `start` | 17:30 | 16:00 | `SHOPMAN_HAPPY_HOUR_START` | Docs e código divergem |
| `end` | 18:00 | 18:00 | `SHOPMAN_HAPPY_HOUR_END` | Alinhados |

### 4.3 Risco de exteriorizar

**Baixo** para os parâmetros numéricos. Um operador configurando janela errada (ex.: 00:00–23:59)
causaria happy hour permanente, mas a carga é sobre o próprio operador.

**Médio** para expor a semântica "bloqueia employee". Se isso virasse um booleano configurável,
um operador poderia ativar stacking employee+happy_hour (desconto duplo pós-pricing), resultando
em preços absurdamente baixos para staff fora do expediente.

### 4.4 Proposta

**Default** (exteriorizar parâmetros, manter bloqueio em código):
- `RuleConfig(code="discount.happy_hour_percent", params={"discount_percent": 25})` no seed.
- `RuleConfig(code="discount.happy_hour_window", params={"start": "17:30", "end": "18:00"})` no seed.
- Ou um único: `RuleConfig(code="discount.happy_hour", params={"discount_percent": 25, "start": "17:30", "end": "18:00"})`.
- Remover dependência de `SHOPMAN_HAPPY_HOUR_*` settings (anti-padrão: config deve estar no DB,
  não em env vars).
- Semântica "skip employee items" permanece em código — invariante de negócio.
- Corrigir divergência docs ↔ código (ver §6).

---

## 5. Achados Transversais

### 5.1 Arquitetura de dois repositórios de modifiers

O WP assume que as três políticas vivem em `shopman/shop/modifiers.py`, mas a investigação revela:

- `shopman/shop/modifiers.py` → `shop.discount` + `shop.employee_discount` (orquestrador)
- `instances/nelson/modifiers.py` → `shop.d1_discount` + `shop.happy_hour` (instância Nelson)

Isso tem implicação relevante: **RuleConfig entries para D-1 e Happy Hour só fazem sentido no
contexto Nelson**. Se amanhã surgir outra instância sem D-1 (ex.: uma loja sem estoque físico
antigo), ela simplesmente não registra esses modifiers. O seed de Nelson deve criar os RuleConfigs;
o seed de outra instância não precisa.

### 5.2 Mecanismo de leitura já parcialmente presente

`D1DiscountModifier` e `EmployeeDiscountModifier` já leem `channel.config.rules.*` como override.
A extensão para RuleConfig é menor do que parece: basta adicionar uma consulta a `RuleConfig`
como fonte de fallback entre `channel.config` e a constante de módulo.

### 5.3 Discrepância docs ↔ código (Happy Hour)

`business-rules.md §6.7` documenta percent=10%, janela=16:00–18:00. O código Nelson tem
percent=25%, janela=17:30–18:00. Esta divergência deve ser resolvida na Fase 2 (alinhar docs ao
código real, ou vice-versa com decisão explícita do dono).

### 5.4 Settings como fonte de config para Happy Hour

`HappyHourModifier` lê `SHOPMAN_HAPPY_HOUR_*` de settings, que é anti-padrão para este projeto
(config deve estar no DB via RuleConfig, não em env vars). A Fase 2 deve migrar esses para
RuleConfig params e deprecar os settings.

---

## 6. Matriz de Decisão

| Política | Params variáveis? | Risco exteriorizar params | Risco exteriorizar semântica | Proposta |
|----------|--------------------|--------------------------|------------------------------|----------|
| Maior desconto ganha (`shop.discount`) | Nenhum — promos já estão no DB | N/A | Alto (stacking acumulativo) | Manter semântica em código; nenhuma mudança |
| D-1 prioridade (`shop.d1_discount`) | `discount_percent=50` | Baixo | Médio (desativar bloqueio cria acúmulo) | **Default**: exteriorizar percent via RuleConfig; semântica em código |
| Employee bloqueia HH (`shop.happy_hour`) | `discount_percent=25`, `start=17:30`, `end=18:00` | Baixo | Médio (stacking pós-pricing) | **Default**: exteriorizar 3 params via RuleConfig; semântica em código |

---

## 7. Recomendação Final

### Decisão: **Default** — exteriorizar parâmetros, manter semântica de stacking em código

**Justificativa**:

1. **Invariantes matemáticos permanecem seguros**: D-1 bloqueando outros descontos e Employee
   bloqueando Happy Hour são garantias que evitam configurações que levem a preços negativos ou
   descontos duplos injustificados. Essas semânticas de ordering e blocking ficam em código Python,
   imutáveis sem deploy.

2. **Dono da padaria ganha controle real sobre os parâmetros que importam**: quanto desconto dar
   nos produtos D-1 (hoje 50%), qual a janela de happy hour, qual o percentual. Esses são
   decisões de negócio genuínas que mudam com a realidade operacional (ex.: "50% não está
   vendendo, vou subir para 60%" ou "happy hour agora é 17:00–18:30").

3. **Custo de implementação é baixo**: os modifiers já leem `channel.config.rules.*` como override.
   A extensão para `RuleConfig` é incremental (fallback adicional na cadeia).

4. **Alternativa A (exteriorizar tudo)** adiciona risco sem benefício proporcional: nenhum dono
   de padaria precisa configurar "quem bloqueia quem" — essa é uma decisão arquitetural estável.

5. **Alternativa B (ADR, manter tudo em código)** desperdiça a oportunidade: os parâmetros
   numéricos (50%, 25%, 17:30–18:00) **são** parâmetros de negócio legítimos, e o sistema já tem
   a infraestrutura (RuleConfig + admin) para expô-los corretamente.

### Escopo preciso para Fase 2 (se aprovado)

**Fase 2 deve implementar:**

```
RuleConfig entries (seed Nelson):
  discount.d1_percent       → params: {discount_percent: 50}
  discount.happy_hour       → params: {discount_percent: 25, start: "17:30", end: "18:00"}
  discount.employee_percent → params: {discount_percent: 20}

Modifiers (leitura de RuleConfig):
  D1DiscountModifier       → lê discount.d1_percent antes de channel.config e constante
  HappyHourModifier        → lê discount.happy_hour em vez de SHOPMAN_HAPPY_HOUR_* settings
  EmployeeDiscountModifier → lê discount.employee_percent (já lê channel.config; adicionar RuleConfig)

Cleanup:
  Deprecar SHOPMAN_HAPPY_HOUR_* settings (ou manter como fallback de última instância)
  Corrigir divergência business-rules.md §6.7 (docs documentam percent=10%, código usa 25%)
```

**Fase 2 NÃO deve implementar:**
- Exposição de `priority`, `blocks`, ou `order` em RuleConfig.
- Validação de ciclos de blocking.
- Novas políticas de desconto.

---

## 8. Referências

- `shopman/shop/modifiers.py` — DiscountModifier (order=20), EmployeeDiscountModifier (order=60)
- `instances/nelson/modifiers.py` — D1DiscountModifier (order=15), HappyHourModifier (order=65)
- `shopman/shop/rules/engine.py` — mecanismo RuleConfig (cache 1h, invalidação em save)
- `docs/business-rules.md §6` — Pricing & Discounts (possui divergência docs↔código em §6.7)
- `docs/reference/system-spec.md §2.5, §2.7` — Rules engine e modifier ordering
- `WP-GAP-10-discount-rules-externalization.md` — escopo original deste WP
