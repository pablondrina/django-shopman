# Plano de Ação — Redesign de Excelência (Work Packages)

> Iniciativa [[project_excellence_refactor_initiative]]. Consolida a discussão estratégica em
> **Work Packages com prompts autocontidos** para execução em sessões novas. Contexto compartilhado
> (LER ANTES de qualquer WP): `docs/redesign/00-core-capability-map.md` (o que o Core/orquestrador
> oferece), `01-surface-audit.md` (frankenstein + causa-raiz), `02-confronto.md` (decisões D1-D7 +
> tenets), `03-spec-storefront.md` (1ª spec), e os dossiês de benchmark em `docs/research/pos-benchmarks/`.

## Princípios inegociáveis (valem para TODOS os WPs)
- **Arquitetura 3 camadas:** Core (domínio, intocado) → Orquestrador (comandos + saga + política +
  read-models de **DADO**) → Superfícies (projeção de **apresentação**: shape puro, zero política,
  zero Core, zero HTML-em-view).
- **Corte política/apresentação; superfície NUNCA toca o Core** (mantém `test_import_boundaries`).
- **Core SAGRADO:** conhecer a fundo antes de propor; refactor de kernel só com **autorização
  explícita do Pablo**. Orquestrador (`shop/`) é editável, mas **sinalizar cada mudança**.
- **Config-driven é a regra:** comportamento/copy/branding por `ChannelConfig`/`RuleConfig`/
  `OmotenashiCopy`/`NotificationTemplate`/`Shop`. **Vertical food/BR NUNCA hardcoded.**
- **Instância = config + dados + marca** (tende a config pura; ver WP3).
- **Não contaminar com a arquitetura atual das superfícies** ("frankenstein"): reconstruir limpo,
  pescando bons padrões; preservar a espinha; split do read-side.
- Convenções: `ref` not `code`, `_q` centavos, no-jargon, zero-residuals, omotenashi+acessibilidade
  first-class.

## Fases e dependências
```
Fase 1 (blueprint, só docs)   WP1 Arquitetura(D) ─┬─ WP2 Specs restantes ─ WP3 Plano instância
Fase 2 (orquestrador refactor) WP4 Read-side split ─ WP5 Drain da instância   [precisam WP1]
Fase 3 (superfícies, limpo)    WP6 Storefront · WP7 PDV · WP8 Backoffice · WP9 Agentic  [precisam WP1/WP4]
Fase 4 (capacidades outbound)  WP10 Sync de catálogo · WP11 Anúncios+automação
```
Branch limpa do redesign: criar na transição Fase 1→2 (decisão Pablo: branch só na etapa D).

---

## WP1 — Arquitetura (Etapa D): o contrato preciso das 3 camadas
**Objetivo:** documento de arquitetura que define o **contrato exato** read-model-de-DADO (DTO
agnóstico de superfície, laden de política, dono = orquestrador) **vs** projeção-de-apresentação
(por superfície), o padrão de **superfície = consumidor do contrato**, a estrutura de pastas/módulos,
e o refinamento da política de import-boundary. É a fundação de todo código.
**Depende de:** nada (lê 00/01/02).
**Entregável:** `docs/redesign/04-architecture.md` + ADR(s).
**Prompt autocontido:**
> Leia `docs/redesign/00-core-capability-map.md`, `01-surface-audit.md`, `02-confronto.md` e a
> memória `project_excellence_refactor_initiative`. Defina a arquitetura de superfícies do redesign:
> (1) o **contrato projection+comando** — a forma exata do *read-model de DADO* (DTO frozen,
> agnóstico de superfície, dono do orquestrador) vs a *projeção de apresentação* (por superfície,
> consome o DADO + SurfaceActionProjection e dá shape de tela); (2) como cada tipo de superfície
> (storefront/PDV/admin-custom/agentic) consome esse contrato de forma idêntica; (3) onde o
> orquestrador expõe os read-models de DADO (ex.: `shop/read_models/` ou via os `*_context` limpos);
> (4) o refinamento do `test_import_boundaries` (superfície segue sem importar o Core; mas a fronteira
> dado/apresentação precisa ser nova-regra-testável); (5) estrutura de pastas. NÃO escreva código de
> feature; é o blueprint. Respeite: Core sagrado, superfície=apresentação pura, config-driven.

## WP2 — Specs restantes (Etapa C): PDV, Agentic, Backoffice
**Objetivo:** completar as specs por superfície (storefront já é 03). Backoffice DEVE incluir gestão
de **sync de catálogo** (WP10) e **anúncios/automação** (WP11) como capacidades de gestão.
**Depende de:** 02 (decisões), 03 (modelo de spec). Idealmente após/junto WP1.
**Entregável:** `05-spec-pos.md`, `06-spec-agentic.md`, `07-spec-backoffice.md`.
**Prompt autocontido:**
> Leia `docs/redesign/02-confronto.md` (decisões D1-D7 + tenets), `03-spec-storefront.md` (modelo),
> `00-core-capability-map.md`, e os dossiês em `docs/research/pos-benchmarks/`. Escreva 3 specs no
> mesmo formato da 03: **PDV** (D2 layout adiado; D3 web/Nuxt; consome SurfaceActionProjection +
> API; comanda/move_lines/fire-kitchen/manager-PIN/caixa-cego; numpad; multi-select de linha do
> Shopify; ergonomia de balcão), **Agentic** (headless; R1 ponte AccessLink sem-login + fluxos
> ManyChat + copy OmotenashiCopy; R2 in-chat previsto — binário resolve-tudo-ou-leva-pra-web;
> transaciona como cliente autenticado; `conversation`+`remote_mutations`), **Backoffice** (Unfold
> canônico p/ gestão+CRM/RFM/loyalty+config+relatórios; dedicado p/ operacional KDS/fila; um
> transporte; permissões únicas; lifecycle single-source `operator_orders.next_status_for`; +
> **gestão de sync de catálogo** e **gestão/disparo de anúncios+automação**). Omotenashi-first,
> config-driven, contrato-ancorado.

## WP3 — DISSOLVER o app da instância (Nelson = config+dados+marca, sem código de tenant)
**Decisão (Pablo 2026-06-05):** não "encolher" a instância — **dissolvê-la**. No modelo "nosso
próprio Shopify", tenant NÃO é pacote de código; o `Shop` já é singleton (single-tenant por
deployment), então "Nelson" = Shop singleton + dados DB (Channels/ChannelConfig/RuleConfig/
OmotenashiCopy/catálogo) + assets de marca + settings do deployment. `instances/<app>` é vestígio de
tratar tenant como código → eliminar o pacote `instances/nelson/` como código.
**Objetivo:** especificar a relocação total de cada item de `instances/nelson/` até o app deixar de
existir como código.
**Depende de:** WP1.
**Entregável:** seção em `04-architecture.md` ou `08-instance-drain.md`.
**Relocação decidida:** D1/HappyHour → rule types genéricos no orquestrador `rules/` + RuleConfig
(por canal); customer_strategies → default no orquestrador + resíduo Nelson thin; taxonomia
(migration) → seed/fixtures (não migration em models compartilhados); ícones → Shop branding;
seed.py + apps.py ficam.
**Prompt autocontido:**
> Leia a tabela de relocação da instância em `project_excellence_refactor_initiative` e
> `instances/nelson/`. Especifique: (1) os **rule types genéricos** "desconto por flag de
> disponibilidade" (D-1) e "desconto por janela de horário" (Happy Hour) no orquestrador `shop/rules/`
> (já há wrappers `D1Rule`/`HappyHourRule` — consolidar) + os params via `RuleConfig` por canal; (2)
> migrar `customer_strategies` genéricas pro orquestrador; (3) trocar a migration de taxonomia por
> seed/fixtures; (4) ícones → branding do Shop. Meta: `instances/nelson/` ≈ settings + dados + marca.
> Core sagrado; mudanças no shop/ sinalizadas.

## WP4 — Split do read-side do orquestrador (refactor autorizado de shop/)
**Objetivo:** separar os read-models de **DADO** (ficam, limpos) da **apresentação** (migra pras
superfícies). Drenar vertical (copy/thresholds) pra OmotenashiCopy/ChannelConfig/RuleConfig.
Refinar o import-boundary.
**Depende de:** WP1.
**Alvos (do audit):** `order_tracking.py` (1.652 linhas: dado fica, copy/ETA/steps vão pro
storefront), `storefront_context`/`checkout_context`/`catalog_context`/`cart_context` (separar dado
de apresentação; externalizar copy/thresholds), `pos.py` (2.179 linhas: separar commit/orquestração
de payload-de-UI). **Sinalizar cada mudança ao Pablo.**
**Prompt autocontido:**
> Leia `01-surface-audit.md` (causa-raiz: import-boundary forçou read-models pra dentro do shop/) e
> `04-architecture.md` (WP1). Execute o split do read-side de `shop/services/`: extraia os DADOS
> (read-models agnósticos, ficam no orquestrador) da APRESENTAÇÃO (copy/format/layout → migra pras
> projeções de apresentação das superfícies). Drene literais vertical food/BR (mensagens, thresholds
> 0.05/happy-hour/freshness) pra `OmotenashiCopy`/`ChannelConfig`/`RuleConfig` (já existem). Refine
> `test_import_boundaries` conforme WP1. Preserve a espinha (lifecycle/config/adapters/rules). Core
> sagrado; cada mexida em shop/ sinalizada. Testes verdes via `make test`.

## WP5 — Drenagem da instância (executar WP3)
**Depende de:** WP3, WP4.
**Prompt autocontido:** > Execute `08-instance-drain.md` (WP3): mova D-1/Happy Hour pra rule types
> genéricos + RuleConfig; customer strategies pro orquestrador; taxonomia pra seed; ícones pro Shop.
> Instância vira config+dados+marca. `make test` verde.

## WP6 — Storefront limpo (reconstruir per 03-spec)
**Depende de:** WP1, WP4.
**Prompt autocontido:**
> Leia `03-spec-storefront.md` + `04-architecture.md`. Reconstrua o storefront como superfície de
> apresentação pura consumindo o contrato: aposente `storefront/cart.py::get_cart` e
> `services/product_cards.py`; um shape de card só; checkout one-page com recálculo ao vivo;
> Maps-first endereço; PIX-first; cross-sell "Talvez você também goste"; availability acionável +
> planned-hold UX; SEO; PWA. HTMX/Alpine, tokens do Shop, OmotenashiCopy. Zero política/Core/HTML-em-
> view. `make test` + verificação no preview.

## WP7 — PDV limpo (reconstruir per 05-spec)
**Depende de:** WP1, WP4, WP2(spec PDV).
**Prompt autocontido:**
> Leia `05-spec-pos.md` + `04-architecture.md` + memória do POS ([[project_pos_uithing_redesign_goal]]).
> Reconstrua o PDV (Nuxt/UI Thing) consumindo o `SurfaceActionProjection` + API headless que já
> existem; elimine HTML-em-f-string das views Django de POS; schema POS compartilhado (gerar tipos,
> matar a dupla manutenção posIntent.ts↔build_session_ops). Layout (D2) e impressão (D3) na fase de
> shell. Comanda/move_lines/fire-kitchen/manager-PIN/caixa-cego preservados.

**Pendência herdada do WP8 (E3/E4) — fazer aqui, no passe do contrato REST/Nuxt:**
> Os campos `status_label`/`status_color`/`availability_label` são hoje `CharField` serializados em
> `storefront/api/serializers.py` e consumidos crus pelo Nuxt. O WP8 Arc E deixou-os de propósito
> (purgar presentation da projection-payload é trabalho deste WP). Ao retrabalhar o schema/contrato:
> **E3** — labels PT (`ORDER_STATUS_LABELS_PT`/`PAYMENT_METHOD_LABELS_PT`/`AVAILABILITY_LABELS_PT`) →
> `OmotenashiCopy` (seed de copy + lookup DB em runtime); **E4** — cores (`ORDER_STATUS_COLORS`) →
> enum `tone` semântico (dado), cada superfície mapeia tone→classe (incl. mapa no serializer p/ manter
> o Nuxt byte-compatível). Decisão Pablo (2026-06-06): adiar do WP8 p/ cá, coordenado. ~15 sites
> storefront+backstage.

## WP8 — Backoffice consolidado (per 07-spec) — ✅ A–F + E1/E2 feitos; E3/E4 → WP7
**Depende de:** WP1, WP4.
**Prompt autocontido:**
> Leia `07-spec-backoffice.md` + `01-surface-audit.md`. Consolide: Unfold canônico (gold standard
> `admin_console`) p/ gestão/config/CRM/relatórios; dedicado p/ operacional (KDS/fila); UM transporte
> de comando; `backstage/permissions.py` único; lifecycle single-source (`operator_orders.next_status_for`);
> decidir destino do KDS-no-Admin. Um contrato projection+comando.

## WP9 — Superfície Agentic (per 06-spec)
**Depende de:** WP1, WP6 (storefront p/ a ponte).
**Prompt autocontido:**
> Leia `06-spec-agentic.md`. Implemente R1: ponte low-friction conversa→loja via `AccessLink`
> (sem-login, `PRESERVE_SESSION_KEYS`) + fluxos ManyChat + copy via `OmotenashiCopy`. Headless:
> renderiza `conversation` projection como mensagem, emite comando via `remote_mutations`. Projete o
> contrato p/ a R2 (in-chat) ser barata. Nenhuma UI própria.

## WP10 — Sync de catálogo multi-canal (Google/IG/WhatsApp/TikTok Shop)
**Objetivo:** projetar e manter sincronizado o catálogo (info/preço/promoção) nos canais externos,
alavancando `CatalogService.project_catalogs()` + `CatalogProjectionBackend` + sync incremental +
signals (`product_created`/`price_changed`). Gestão no backoffice.
**Depende de:** WP4 (read-side limpo) — desejável; pode iniciar em paralelo (é orquestrador+adapters).
**Prompt autocontido:**
> Leia `00-core-capability-map.md` (§Offerman projection: `project_catalogs`, `CatalogProjectionBackend`,
> `PROJECTION_BACKENDS`, sync incremental por `last_projected_skus`, adapter iFood existente). Adicione
> **projection adapters** por canal: Google Merchant Center, Meta Catalog (Instagram Shopping +
> WhatsApp Catalog), TikTok Shop. Credenciais via `Shop.integrations`/settings. Wire o sync
> incremental (signals → re-project) e a gestão no backoffice (status por canal, full-sync, retração).
> Config-driven por canal. Core sagrado (Offerman já tem o contrato — não tocar o kernel; só adapters
> no shop/ + config).

## WP11 — Anúncios sensíveis a contexto/tempo + automação
**Objetivo:** compor e disparar anúncios (ex.: "fornada saiu", "só X croissants") em canais social
(Google Posts, IG Stories, Threads, TikTok), com dados de contexto interpolados; depois regras de
automação (gatilho→ação). MVP manual fácil → automação.
**Depende de:** WP4. (Subsistema novo; reusa directive/adapter/template + nova camada de regras.)
**Prompt autocontido:**
> Subsistema NOVO de marketing/broadcast. Gatilhos = eventos de domínio que o Core já emite
> (produção finalizada/fornada via `holds_materialized`/Move "Recebido de produção"; estoque baixo via
> StockAlert; tempo via `business_calendar`). Ação = post outbound em social. Implemente: (1) **social
> adapters** (Google Posts, IG Stories, Threads, TikTok) no shop/adapters; (2) directive `social.post`
> + handler; (3) **templates de anúncio** (copy interpolada com contexto — modelar tipo
> NotificationTemplate/OmotenashiCopy, mas marketing); (4) MVP de backoffice "compor + disparar"
> (manual, fácil, selecionar canais, preview com contexto ao vivo); (5) **camada de regras de
> automação** (gatilho→ação, config-driven, on/off por canal — espelhar o padrão RuleConfig).
> Consentimento/limites onde aplicável. Config-driven; Core sagrado.

---

## Estado de partida para a sessão nova
- Estratégia concluída: docs/redesign/00→03 + PLAN escritos; decisões D1-D7 + arquitetura 3 camadas
  + corte política/apresentação + instância=config + 2 requisitos outbound capturados.
- Próximo passo recomendado: **WP1 (arquitetura)** → **WP2 (specs restantes)** → criar branch limpa →
  Fase 2/3/4.
- Pendência prática herdada: reverter a trial Shopify (password "righex" + apagar produto teste)
  quando o Pablo decidir — não bloqueia o redesign.
</content>
