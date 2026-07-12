# ADR-014 - Corte dado/apresentação nas superfícies: Projection de dado vs Presentation

**Status:** Accepted
**Data:** 2026-06-05
**Escopo:** Orquestrador (`shopman/shop/`) e superfícies (storefront, PDV/Nuxt, backstage/admin, agentic).
**Refina:** [ADR-005](adr-005-orchestrator-as-coordination-center.md) (orquestrador = centro de
coordenação) e [ADR-012](adr-012-headless-surface-contract.md) (contrato headless: Projection com Actions).
**Blueprint:** [docs/_archive/redesign/04-architecture.md](../_archive/redesign/04-architecture.md) (WP1).

---

## Contexto

A iniciativa de redesign de excelência ([[project_excellence_refactor_initiative]]) auditou as
superfícies atuais ([01-surface-audit](../redesign/01-surface-audit.md)) e achou a causa-raiz do
"frankenstein": a regra **"superfície nunca importa o Core"** (testada em `test_import_boundaries`)
estava certa, mas **incompleta** — não havia uma camada de apresentação **dentro** da superfície. Sem
ela, a apresentação (copy, formatação, layout, ETA, labels) não tinha pra onde ir e **vazou para o
orquestrador**, inflando `shop/services/` num BFF de ~7.000 linhas (`order_tracking.py` 1.652 ln de
projeção de tela; `*_context` com merchandising; `pos.py` 2.179 ln misturando comando e payload de UI).

Sintomas: dois shapes de card e dois templates para o mesmo conceito; `product_cards.py` recalculando
promoção via **métodos privados do Core** (divergência preço-vitrine vs preço-carrinho); lifecycle
duplicado (`order_queue` vs `operator_orders.next_status_for`); vertical food/BR hardcoded.

## Decisão

Adotar um **corte semântico explícito** entre **dado** e **apresentação**, ortogonal ao corte mecânico
existente (que **fica intocado**: superfície nunca importa o Core).

1. **`Projection` (de dado)** — dono: **orquestrador**. É a "Projection" da
   [ADR-012](adr-012-headless-surface-contract.md), e **fica onde sempre esteve**: `shop/projections/`
   (read-side). É frozen, surface-agnostic, **policy-laden** (toda decisão já tomada) e **semântica**
   (centavos `_q`, enums, timestamps ISO, booleanos, refs, `reason_code`, `payload_schema`). **Não**
   carrega string de UX renderizada, formatação de dinheiro, frase de ETA, label ou HTML. Carrega
   `actions: list[Action]` como contrato de comando (a `Action` é o item acionável — ver decisão 7). O
   read-side `shop/projections/` (hoje só `types.py`) **cresce** para abrigar o dado drenado dos
   `*_context`/`order_tracking`.

2. **`Presentation`** — dona: **cada superfície**. Vive em `<surface>/presentation/`. Consome **só**
   `shop.projections` (Projection + `Action`); **nunca** o Core, **nunca**
   `shop.services` (write-side). Produz o shape de tela: resolve copy (via Projection de copy do
   `OmotenashiCopy`), formata `_q`→`R$`, frase de ETA, label de status, agrupa, ordena, mapeia ícone. É
   específica da tecnologia de render (Django/HTMX, Nuxt/TS, Unfold, mensagem).

3. **`shop/` parte em dois eixos:** `shop/services/` = **write-side** (comandos + saga + política — a
   espinha, **sagrada**); `shop/projections/` = **read-side** (as `Projection`). Os read-models de tela
   hoje em `services/` migram para `projections/`, **purgados de apresentação**; a apresentação migra
   para as superfícies (`<surface>/presentation/`).

4. **Vocabulário** (resolve a sobrecarga de "projection"): no orquestrador, **`Projection`** = dado
   (como na ADR-012); na superfície, **`Presentation`** = aparência. "Presentation" **não** é sinônimo de
   "projection", então não há colisão. O bug de naming antigo não era a palavra "projection"; era **não
   existir uma camada de Presentation na superfície**. Por isso `shop/projections/types.py` **não é
   renomeado** — o contrato compartilhado fica; só sai o label PT do `Availability` (que é Presentation).

5. **O contrato é consumido idêntico** por storefront, PDV, backstage/admin e agentic:
   `Projection de dado → Presentation → render`; mutação via `shop.services` ou REST + `Action`.
   Só a tecnologia de render varia. O **agentic (headless) é o canário**: só funciona se a Projection for
   100% agnóstica de superfície.

6. **A fronteira vira testável.** `test_import_boundaries` ganha quatro regras (mantendo todas as
   atuais): **R-A** Presentation não importa `shop.services`; **R-B** `shop/projections/` não importa
   formatação/locale/HTML nem contém copy PT-BR; **R-C** `shop/projections/` é frozen e ignora HTTP;
   **R-D** uma forma de card (sem 2º shape/template). As regras atuais escritas contra
   `<surface>/projections/` reapontam para `<surface>/presentation/` (renomeação de alvo).

7. **`SurfaceActionProjection` → `Action`.** O prefixo "Surface" mentia (o tipo é **surface-agnostic**,
   dono = orquestrador; a superfície consome, não possui) e o sufixo "Projection" sobrevende um item de
   `Projection.actions[]`. `Action` é o nome do conceito na **própria ADR-012**
   (`InteractionContext → Projection → Action → Intent → Mutation`) — o rename **alinha o código ao
   ADR-012**, não se afasta dele. Zero-residual ([[feedback_zero_residuals]]).

## Relação com ADR-012 (refinamento, não contradição)

ADR-012 diz que a **Projection** "deve carregar dados, **copy operacional**, disponibilidade, promises,
timers, errors e actions suficientes para a superfície renderizar **sem inferir regra de negócio**", e
que `label` é "copy curta pronta para a superfície".

O **objetivo real** do ADR-012 é impedir a superfície de **inventar regra de negócio/política** (qual
produto, tem hoje, qual prazo, qual pagamento, qual CTA, como recuperar). Esse objetivo é **preservado
integralmente**: toda política continua decidida pelo orquestrador e selada na `Projection`.

O que o ADR-014 **refina** é onde a *copy* mora. Embutir a string final em cada Projection foi o que
inflou o orquestrador. A copy **continua autoritativa e centralizada** (`OmotenashiCopy`, dono =
orquestrador) — ela **não** é inventada pela superfície. Apenas passa a ser **exposta como Projection de
copy** (`shop/projections/copy.py`, resolvida por `key/moment/audience`) e **colocada** pela camada de
Presentation. Assim:

- a garantia anti-invenção do ADR-012 **fica** (copy vem de config do orquestrador, não da superfície);
- a `Projection` carrega a **chave/semântica** (`reason_code`, `Availability` enum, `label` como
  **key**), não a string renderizada;
- a fonte de bloat (copy/format embutidos no dado) **some**.

O contrato **Projection-com-Actions** (`Action`: ref/kind/label/enabled/reason/href/
method/payload_schema/idempotency/confirmation) e a cadeia
`InteractionContext → Projection → Action → Intent → Mutation` **não mudam** — a `Projection` continua
no orquestrador (ADR-012), e ganha a contraparte de Presentation na superfície.

## Consequências

**Positivas**
- `order_tracking.py`/`*_context`/payload de UI do `pos.py` saem da espinha; `shop/services/` volta a
  ser write-side puro. A divergência preço-vitrine vs carrinho fica impossível (uma Projection, zero
  re-política).
- Um shape de card, um caminho de copy, um lifecycle (`operator_orders.next_status_for`).
- Agentic rodada 2 (in-chat) fica barata: mesma Projection, só render-como-mensagem.
- O corte é **executável e durável** (R-A..R-D testam o que era convenção).
- **O conceito ADR-012 fica:** `Projection`/`shop/projections/` ficam; o único rename de tipo
  (`SurfaceActionProjection`→`Action`) **aproxima** o código do vocabulário do ADR-012, não o afasta.

**Custos / riscos**
- Trabalho de split no `shop/` (read-side): **autorizado, mas cada passo sinalizado ao Pablo**
  (S1–S8 no blueprint §7). A espinha (`lifecycle`/`config`/`rules`/`handlers`/`adapters`/`models`) e
  `packages/` ficam **intocados**.
- Migração da Presentation para superfícies reconstruídas do zero (Fase 3) — não é reescrita do Core.
- As pastas `<surface>/projections/` atuais renomeiam para `<surface>/presentation/` (free na
  reconstrução da Fase 3; reaponta os alvos de teste).
- `shop/projections/copy.py`: formato exato (catálogo único vs builder por moment) decidido na WP4 com o
  primeiro caso real (copy do order_tracking).

## Alternativas descartadas

- **`ReadModel` (dado) + `Presentation` (superfície).** Coerente e CQRS-explícito (read_models/ ao lado
  de services/), mas **renomearia o vocabulário do ADR-012** ("Projection"→"ReadModel"). Como ReadModel e
  Projection são sinônimos, isso não comprava clareza — só churn. Preferiu-se **manter "Projection"**
  (canon do 012) e só nomear a camada nova de Presentation. (Decisão Pablo 2026-06-05.)
- **`DataReadModel` (dado) + `PresentationProjection` (superfície)** — proposta inicial deste WP.
  Descartada: usa dois sinônimos (ReadModel/Projection) split entre as camadas, sugerindo uma distinção
  que as palavras não carregam; e *invertia* o uso de "Projection" do ADR-012 (movia pro lado da
  superfície). Confuso. Substituída por Projection+Presentation.
- **Afrouxar `test_import_boundaries`** (deixar a superfície ler o Core / fachada read-only). Descartado:
  o corte mecânico não era a vilã, era incompleto. Afrouxar reabriria o `cart.py::get_cart`.
- **Manter os read-models de tela no orquestrador** (status quo). Descartado: é a causa do bloat.
- **Um BFF separado entre orquestrador e superfícies.** Descartado para o nosso caso (single-tenant,
  `Shop` singleton): Presentation por-superfície + Projections no orquestrador já dá o corte limpo sem
  mais um processo/camada (KISS).
```
