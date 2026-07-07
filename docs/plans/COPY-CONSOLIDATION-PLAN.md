# COPY-CONSOLIDATION-PLAN — matar o drift registro × template

Status: **CONCLUÍDO** (2026-07-07) para as áreas mapeadas. Insight que guiou a execução:
**chave no registro que não chega a nenhuma tela é uma "mentira" para o operador** (ele
edita no Admin e nada muda) — logo, chrome estrutural com chave órfã confirmada resolve-se
**removendo a chave** (fonte única = template), e copy entregue-mas-ignorada resolve-se
**consumindo a projection** no Vue. Resultado:

- **Home "Como Funciona"** ✅ Vue consome `how_online_heading`/`how_store_heading`.
- **Tracking** ✅ Vue consome `tracking.copy.page_kicker`/`order_ref_label` (com fallback
  no header, que renderiza antes de `tracking` carregar).
- **10 chaves órfãs deletadas** (zero refs, não-dinâmicas): `CART_PAGE_TITLE`,
  `CHECKOUT_PAGE_TITLE`, `CHECKOUT_PAGE_META_DESCRIPTION`, `CHECKOUT_LOYALTY_PROMPT`,
  `CHECKOUT_COUPON_PROMPT`, `CHECKOUT_NOTES_PROMPT`, `MENU_EMPTY`, `MENU_PAGE_META_DESCRIPTION`,
  `PDP_CROSS_SELL_HEADING`, `TRACKING_RATE_PROMPT`. Os hardcodes (iguais ou melhores)
  viram fonte única; o cross-sell adotou o wording bom do registro ("Talvez você também goste").
- Fora de escopo confirmado: `MENU_SUBTITLE` (viva só como fixture de teste do template tag —
  investigar depois) e a limpeza das ~180 chaves órfãs de legado do cutover.

## Problema

A copy de cliente é canônica no **registro omotenashi** (`shopman/shop/omotenashi/copy.py`,
`OMOTENASHI_DEFAULTS`, ~389 chaves), resolvida pela camada de **presentation** via
`build_copy(namespace)` / `resolve_copy(key)` e entregue às superfícies Nuxt como
**projections** (campos `CopyEntryProjection`). O Vue deveria **consumir** a projection.

**Drift:** vários templates Nuxt **hardcodam** strings que também existem no registro —
às vezes com wording **divergente**. Duas fontes de verdade = risco de inconsistência
silenciosa e copy que o operador acha que configura (via Admin/OmotenashiCopy) mas não
tem efeito, porque a tela ignora a projection.

## Descoberta crítica — por que NÃO deletar chaves em massa

Um scan por nome literal marca ~187 chaves como "não referenciadas". **É enganoso.** As
chaves são resolvidas também de forma **não-estática**:

- **f-string por prefixo** (`shopman/storefront/presentation/status.py`):
  `build_copy("ORDER_STATUS").title(f"ORDER_STATUS_{status.upper()}")`,
  idem `PAYMENT_METHOD_*`, `AVAILABILITY_*`.
- **valor carregado no dado**: uma promise de tracking carrega `copy_key`; a presentation
  resolve `.title(promise.copy_key)`. As chaves `TRACKING_PROMISE_*` nunca aparecem
  literalmente no código.
- **namespaces inteiros** (`build_copy("TRACKING"|"CHECKOUT"|"PAYMENT"|"STOREFRONT")`)
  carregam todas as chaves do prefixo para o catálogo.

⇒ **Regra de ouro:** só deletar uma chave após **confirmar positivamente** que é
inalcançável — nenhum literal, nenhuma família f-string, nenhum `copy_key` de dado. Na
dúvida, **não deletar**. Limpeza de órfãs de legado (resíduo do cutover headless, telas
Django removidas) é **fora de escopo** deste plano — vira um passe próprio por família.

## Princípio de resolução (por caso)

Para cada string hardcoded que colide com o registro:

1. **É copy de cliente (deve poder ser reconfigurada pelo operador)?**
   → Fonte única = **REGISTRO**. Entregar via projection (Python) e **consumir no Vue**,
   removendo o hardcode. Alinhar o wording do registro ao melhor texto. *(padrão validado
   na home "Como Funciona").*
2. **É label puramente estrutural, que ninguém configura, e a chave do registro está
   comprovadamente órfã?**
   → Manter no template e **deletar a chave órfã**.
3. **Nunca** deixar duas fontes. Se ligar dá trabalho desproporcional para um label trivial,
   documentar a decisão de manter hardcode + remover a chave.

Toda mudança: `build` + testes verdes + **verificação de tela**.

## Áreas e drifts concretos

| # | Área | Hardcode (Vue) | Chave/campo do registro | Ação |
|---|------|----------------|-------------------------|------|
| 1 | Home "Como Funciona" | "Peça online" / "Visite a loja" | `how_online_heading` / `how_store_heading` (já entregues) | **✅ FEITO** — Vue consome projection; registro adotou o wording bom |
| 2 | Produto | `<h2>Você também pode gostar</h2>` | `PDP_CROSS_SELL_HEADING` (title+message, **não entregue**) | Entregar `cross_sell_heading` na product projection; consumir; alinhar wording |
| 3 | Checkout | h1 "Finalize seu pedido"; "Usar pontos de fidelidade"; "Cupom de desconto?" | `CHECKOUT_PAGE_TITLE` / `CHECKOUT_LOYALTY_PROMPT` / `CHECKOUT_COUPON_PROMPT` (**não entregues**) | Entregar copy bag na checkout projection; consumir; alinhar |
| 4 | Sacola | h1 "Sua sacola" | `CART_PAGE_TITLE` ("Sua sacola") | Confirmar órfã; entregar via cart projection **ou** deletar chave (label estrutural idêntico) |
| 5 | Tracking | kicker "Acompanhamento" / "Pedido {ref}" | `TRACKING_PAGE_KICKER` / `TRACKING_ORDER_REF_LABEL` | Verificar entrega; consumir se entregue |
| 6 | Menu | vazio "Cardápio em preparo…" | `MENU_EMPTY` / `MENU_SUBTITLE` | Confirmar órfã; resolver (entregar ou deletar) |

> Campos de projection **entregues mas não consumidos** (ex.: `how_step_choose/pay/fulfill`,
> `how_self_service_label` — de um layout antigo da home) são um sub-caso: ou o layout volta
> a usá-los, ou se podam do projection + registro. Tratar ao passar por cada área.

## Guardrails / testes

- Manter `test_used_copy_keys_are_defined` (chave usada via `.title/.text` deve existir).
- Manter `test_no_em_dash_in_copy` (voz da marca).
- Adicionar **radar de órfã ciente de dinâmicas**: reportar (não travar) chaves cujo
  namespace nunca é carregado por `build_copy` **e** que não são referenciadas por literal —
  candidatas a investigação, nunca deleção automática.

## Sequência

Uma área por vez, **commit por área**, com verificação de tela. Ordem por
valor/risco: Home ✅ → Produto → Checkout → Sacola → Tracking → Menu.

## Limpeza de legado ✅ FEITA (2026-07-07)

Executada com segurança após validar o **radar de alcançabilidade**:

- Confirmado que os **únicos** caminhos não-literais são 3 f-strings
  (`ORDER_STATUS_`/`PAYMENT_METHOD_`/`AVAILABILITY_`) — **não** há `copy_key` de dado
  (grep vazio), nem concatenação/`.format()`/`getattr` construindo chave. Logo o radar
  (definida − literal-ref − famílias dinâmicas) é **sólido**.
- **157 chaves órfãs removidas** via AST (robusto, não regex): `copy.py` 379 → 222
  chaves. Preservadas `MENU_SUBTITLE`/`WELCOME_WHATSAPP` (referenciadas só em testes).
- **Zero falhas novas**: as 18 falhas do suite completo são **pré-existentes** (idênticas
  com o `copy.py` original — permissions/order_confirm/exception-hygiene, sem relação).
  Home/tracking/product resolvem copy normalmente; sem erros no runtime.
- **Guardrail instalado**: `test_no_orphan_copy_keys` recomputa o radar e falha se uma
  chave definida ficar inalcançável (impede as órfãs de voltarem a crescer).
