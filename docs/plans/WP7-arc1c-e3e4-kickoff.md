# WP7 · Arc 1 · sub-step C (E3/E4) — kickoff autossuficiente

> Prompt de abertura para sessão limpa. Branch `redesign/surface-excellence`.
> **Fecha o Arc 1 do WP7** (seam de dado & contrato do PDV). S4 (drain CQRS-puro) e
> B (schema POS compartilhado) já FEITOS e verdes. Falta **C = E3/E4**.

## Postura & autonomia

**AUTONOMIA TOTAL** (Pablo, 2026-06-06): decidir por mérito e prosseguir sem perguntar.
**NUNCA menor-diff/menor-esforço** — só a solução mais Simples/Robusta/Elegante pelo mérito
(`feedback_never_recommend_smallest_diff`; Pablo cobrou isso no S4 deste mesmo Arc, e eu tive de
refazer — não repetir o reflexo). Zero gambiarra, zero residual em renames/deleções, não inventar
features. Verde a cada passo; commit coerente ao fim.

**Core SAGRADO** (`packages/`, intocável sem autorização). `shop/` é orquestrador editável, mas
**cada mudança sinalizada**. Antes de "o Core/orquestrador não cobre", assumir que cobre e procurar
onde (`feedback_respect_core_no_reinvent`).

## Ler primeiro (obrigatório)
- Memória **`project_wp7_pos_status`** — estado do WP7, S4/B feitos, e o mapa completo de C (sites + infra).
- Memória **`project_wp8_backoffice_status`** — E3/E4 nasceu como pendência herdada do WP8 Arc E.
- `docs/redesign/04-architecture.md` §4.2 — **regra R-B**: `shop/projections/` (read-side de DADO) **não
  pode** carregar apresentação (copy PT, formatação, cor/classe). É exatamente o que E3/E4 conserta.
- `docs/redesign/PLAN.md` §WP7 — texto canônico de E3/E4 (decisão Pablo 2026-06-06: fazer no WP7).
- `docs/decisions/adr-014-...md` — copy continua autoritativa/centralizada no orquestrador
  (`OmotenashiCopy`), exposta como Projection de copy e **colocada** pela Presentation; nunca inventada
  pela superfície, nunca hardcoded nela.

## O problema (R-B violado)
`shopman/shop/projections/types.py` carrega **apresentação dentro do read-side de DADO** — labels PT e
classes Tailwind de cor, hoje serializados crus como `CharField` para o Nuxt/REST. Confirmar as linhas
(mapeadas 2026-06-06, reconferir):
- `AVAILABILITY_LABELS_PT` (~25), `PAYMENT_METHOD_LABELS_PT` (~57), `ORDER_STATUS_LABELS_PT` (~66),
  `ORDER_STATUS_COLORS` (~78, classes Tailwind tipo `"bg-info/10 text-info border border-info/20"`).

## E3 — labels PT → OmotenashiCopy (copy de verdade, com lookup runtime)
Mover os labels para entradas de `OmotenashiCopy` e resolvê-los na **Presentation** de cada superfície.
- **Infra a reusar (NÃO reinventar):** `shopman/shop/omotenashi/copy.py` (`OMOTENASHI_DEFAULTS[key][moment]
  [audience]=CopyEntry(title,message)`, `resolve_copy` cascata DB→default nunca-raise, `all_keys`).
  `shopman/shop/projections/copy.py::build_copy(namespace, moment, audience) -> CopyCatalog` (frozen,
  `.title(key)`/`.message(key)`). Presentations já consomem (merchandising/order_tracking/checkout/
  payment). Admin em `shop/admin/omotenashi.py`; seed via migrations `shop/migrations/0002`/`0004`.
- Modelar chave por enum-membro (ex.: `ORDER_STATUS_NEW`→title "Recebido"; `PAYMENT_METHOD_PIX`→"PIX";
  `AVAILABILITY_AVAILABLE`→"Disponível"). Seed os defaults; a Presentation resolve via `build_copy`.

## E4 — cores → enum `tone` semântico (dado) + mapa na Presentation
`ORDER_STATUS_COLORS` (classes Tailwind) sai do read-side. Em `types.py` fica só um **`tone` semântico**
(enum: `info`/`warning`/`success`/`danger`/`neutral`) + `ORDER_STATUS_TONES: dict[str, Tone]`. O mapa
**tone→classe Tailwind** é Presentation. Decisão aberta (por mérito): lar do mapa — por-superfície vs.
um helper compartilhado (as classes são design-tokens iguais nas duas superfícies). O serializer
continua emitindo `status_color` **byte-idêntico** mapeando tone→classe.

## Sites a tocar (~15, mapeados 2026-06-06 — reconferir antes de editar)
- `storefront/presentation/`: `catalog.py:389`, `product_detail.py:250`, `checkout.py:262`,
  `order_tracking.py:277-278` e `:319-320`, `order_history.py:91-92`.
- `backstage/projections/`: `order_queue.py:231-232` e `:336-337`, `production.py:891`
  (`production.py` tem também `WO_STATUS_LABELS`/`WO_STATUS_COLORS` — enum DIFERENTE, decidir se entra no
  mesmo padrão ou fica fora do escopo).
- Serializers (contrato REST/Nuxt): `storefront/api/serializers.py:92,154,250-251,328-329`.
- POS: `backstage/projections/pos.py` tem `status_label="Livre"/"Em uso"` hardcoded (avaliar).

## Mandato byte-compat (crítico)
`status_label`/`status_color`/`availability_label` são `CharField` serializados crus e consumidos
**prontos** pelo Nuxt/HTMX. **Não mudar 1 caractere das strings finais.** O seed de copy deve reproduzir
exatamente os labels atuais; o mapa tone→classe deve reproduzir exatamente as classes atuais. Uma letra
a mais quebra o cliente sem teste pegar. Sugestão: capturar as strings atuais antes (snapshot) e diffar.

## Estratégia
Fazer **por-arquivo** (E3+E4 juntos no mesmo site, não em duas passadas) para não tocar os mesmos
arquivos duas vezes. Começar pelo enum `tone` + helper (E4, mais contido), depois o seed de copy + os
sites de label (E3).

## Gates (verde ao fim)
- `pytest shopman/shop/tests shopman/storefront/tests shopman/backstage/tests -q` — E3/E4 cruza a
  fronteira storefront, então **storefront/tests entra no gate** (além de shop+backstage). **NÃO**
  `make test-framework` (`project_backstage_pos_test_pollution`).
- `cd surfaces/pos-uithing-nuxt && npx nuxi typecheck` (ignorar erros pré-existentes conhecidos em
  `djangoProxy.ts`/`nuxt.config.ts`) + `vitest`. PATH com `/opt/homebrew/bin` (Node 20+).
- **`make admin`** se tocar superfície Admin/Unfold — `order_queue`/`production` projections podem cruzar
  o gate canônico; provavelmente necessário. Ler a skill `unfold-admin-canonical` antes se for o caso.
- `ruff check` limpo nos arquivos tocados.
- Confirmar a regra **R-B** do `test_import_boundaries` (se existir/ativa) passa — é o que E3/E4 satisfaz.

## Ao terminar
Commit coerente fechando o **Arc 1**. Atualizar `project_wp7_pos_status` (C done → Arc 1 fechado).
Seguir para **Arc 2** (Presentation TS + telas núcleo do PDV) conforme `docs/plans/WP7-pos-kickoff.md`.
```bash
pytest shopman/shop/tests shopman/storefront/tests shopman/backstage/tests -q
```
