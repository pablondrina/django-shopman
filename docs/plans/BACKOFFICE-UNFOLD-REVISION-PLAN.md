# Plano — Revisão Completa do Backoffice Unfold

> **Objetivo (Pablo, 2026-06-19):** o backoffice (Django Admin/Unfold) também virou um
> "Frankenstein". Revisar TUDO, em três camadas **nesta ordem**:
> 1. **Correção funcional** — funcionar certo, sem falhas, **sem gambiarra alguma**.
> 2. **Completude** — permitir tudo que o backend oferece e que o operador deva
>    configurar/selecionar/editar, **sem faltar nada**.
> 3. **UX de primeiríssima linha** — sem dever nada aos benchmarks (Shopify, Odoo,
>    STORES, Take.app).
>
> Método: auditoria reversa (3 exploradores, 2026-06-19) → este plano → executar por WP
> com aprovação, cada WP auto-contido, gates verdes e verificação ao vivo.

---

## 0. Escopo e base

**Backoffice Unfold** = a superfície **Django Admin** estilizada com django-unfold (0.92.0):
todos os `ModelAdmin` (config + dados) + as páginas custom `admin_console`
(Pedidos/Produção/Fechamento) + a navegação. **NÃO** inclui (exceções explícitas, adr-013/014):
- **POS** (Nuxt, `surfaces/pos-uithing-nuxt`) — superfície própria.
- **Storefront** (Nuxt headless) — cliente.
- **KDS** (HTMX hoje; decisão Nuxt pendente — coordena com `SURFACE-CONVERGENCE-PLAN`).

**Base recomendada:** a branch `feat/admin-config-omotenashi` (WP-1..8 já entregues — ver §1)
**após** o Pablo revisar/mergear, OU ramificar a partir dela. Decisão do Pablo no kickoff.

**Restrições inegociáveis (ver §6):** Unfold Canonical Gate (`make admin`), Core sagrado
(admin de packages só via `contrib/admin_unfold`), zero gambiarra, planos no repo.

---

## 1. Já feito (NÃO refazer) — WP-1..8 do ADMIN-CONFIG-OMOTENASHI

A revisão da camada de **configuração** já aconteceu (capítulo anterior, branch
`feat/admin-config-omotenashi`). A auditoria de completude abaixo tem achados que **já estão
resolvidos** — ignore-os:

- ✅ Página da Loja quebrada em **9 páginas focadas** (proxy models): Loja & contato, Marca &
  aparência, Horários & operação, Cardápio, Pedidos & entrega, Fidelidade, PDV & alertas,
  Produção, Integrações. `Shop.defaults` é **tipado** (não é mais JSON cru).
- ✅ **Promotion/Coupon admin EXISTEM** (`storefront/admin/promotions.py`), com badge de situação.
- ✅ **RuleConfig.params tipado** por tipo de regra; fim do JSON cru p/ happy_hour/d1/employee.
- ✅ Fidelidade admin-configurável (`Shop.defaults["loyalty"]`); resolvers Core-sagrados.
- ✅ Tunables triados: POS discount threshold + stock alert cooldown → admin.
- ✅ Sidebar com grupo **Configurações**; guestman loyalty/grupo em Unfold.
- ✅ Listas arrastáveis (`ordering_field`): Faixas de distância, Zonas, Canais, Regras, Coleções.
- ✅ Badges nativos `@display(label=)`; multi-select de meses; ArrayWidget (social_links, coleções).
- ✅ Catálogo i18n: `locale/pt_BR` traduzindo strings próprias do Unfold.

> Onde a auditoria de completude (§3) e este plano divergirem do estado real, **o estado real
> manda** — confira no código antes de agir.

---

## 2. CAMADA 1 — Correção funcional, sem gambiarra (P0)

> **Estado (2026-06-19): CAMADA 1 ENTREGUE.** WP-C1 ✅ `80ac462b`, WP-C4 ✅ `9fc33b94`,
> WP-C2 ✅ `8cf7c13e`, WP-C3 ✅ `f1378ad2`. WP-C5 ⏸️ adiado p/ SURFACE-CONVERGENCE.
> Tudo na branch `feat/admin-config-omotenashi`. `make test`(2077)/`lint`/`admin` verdes;
> verificado ao vivo. Próximo: Camada 2 (D1-D5) em sessão nova.

> Critério: cada superfície abre, salva e executa ações sem erro; zero HTML/JS cru "na mão"
> onde há primitiva Unfold; zero monkey-patching; zero acoplamento frágil. `make admin` verde
> de verdade (não por waiver preguiçoso).

### WP-C1 — Matar o monkey-patching do OrderAdmin/ProductAdmin ✅ (`80ac462b`)
> Concluído. Fulfillment inline→orderman; D-1→offerman form; filtros/batch-link→stockman
> contrib; payment_info→subclasse shop via unregister+re-register. Zero `type()`-patching.
> Achado: a página de Product 500a (campos de nutrição injetados em `__init__` não são
> declarados) — **pré-existente** (500 idêntico no HEAD), será corrigido no WP-C4.

**Problema:** `shopman/shop/admin/orders.py` faz monkey-patching em runtime das classes já
registradas (`_extend_order_admin()` via `type(admin.site._registry[Order])`, idem
`_extend_product_admin`), adicionando inline de Fulfillment, `payment_info`, campos. Frágil
(depende da ordem de `INSTALLED_APPS`, quebra silenciosa em refactor do Core, sem testes).
**Ação:** mover essas extensões para o padrão canônico do projeto —
`orderman/contrib/admin_unfold/` e `offerman/contrib/admin_unfold/` (ou um ponto de extensão
explícito exportado pelo Core). Eliminar `type()`-patching. Teste garantindo o inline/َcampos.
**Restrição:** Core sagrado — a mudança é no `contrib/admin_unfold` (presentation), não no model.

### WP-C2 — Refatorar displays/widgets com HTML+JS inline ✅
> Concluído. payment_info → componente Unfold `table.html` (template varrido, canônico);
> resolved_config_display → JSON escapado (corrige injeção) + classes Unfold; FontPreviewWidget,
> color_preview e storefront_preview → Alpine no lugar de `<script>` cru + classes Unfold no
> chrome; sobra só o estilo inline irredutível (cor do swatch, font-family, altura do iframe —
> sem token/primitiva Unfold). Verificado ao vivo (Alpine aplica font-family, sem erros).
> Nota: `shop/admin/*.py` não é varrido pelo gate; estes são previews custom autorizados (§4 tier 3).

Inventário de HTML/JS cru em métodos de admin (mark_safe/format_html com `<div>/<table>/<script>/<pre>` + `style=`):
- `shop/admin/widgets.py` **FontPreviewWidget** — `<script>` + `<div style>` inline (pior caso).
- `shop/admin/shop.py` **color_preview** (~60 linhas de `<div style>`), **storefront_preview**
  (`<iframe>` + `<script>` inline).
- `shop/admin/channel.py` **resolved_config_display** — `<pre>` cru.
- `shop/admin/orders.py` **_payment_info** — `<table style>` cru.
**Ação, por item, escolher (nesta ordem de preferência):**
1. Primitiva Unfold equivalente (`unfold/components/...` via `{% component %}`, helpers).
2. Template + Alpine/HTMX (sem `style=`, só classes do CSS compilado do Unfold).
3. Se não houver equivalente (swatch de cor, iframe de preview): **waiver canônico válido**
   (`authorized-by` real, `authorization-ref`, `reason` ≥20 chars) + remover `style=` inline.
**Meta:** zero `mark_safe(f"<…")` com estilo inline sem waiver; `check_unfold_canonical` limpo.

### WP-C3 — Fallback plain dos admins de Core não pode ativar em produção ✅
> Concluído. Guarda runtime `test_core_models_use_unfold_admin` (parametrizada sobre todo o
> registry de models de Core; sem allowlist) plugada no `make admin`. Os 7 admins CRM do
> guestman que eram Django plain → Unfold: 5 feature-contribs (consent/identifiers/insights/
> preferences/timeline) base-swap in-place; ContactPoint/ExternalIdentity portados p/
> `contrib/admin_unfold` com badges canônicos (sem style inline). Scan: 0 admins de Core
> vanilla. Verificado ao vivo (ContactPoint com badges booleanos Unfold + datas pt-BR).

**Problema:** cada package tem `admin.py` plain (Django vanilla) + `contrib/admin_unfold`. Se
o contrib sair de `INSTALLED_APPS`, o admin cai para vanilla (sem Unfold) silenciosamente.
**Ação:** teste/guard que TODOS os models de Core estão registrados com `unfold.admin.ModelAdmin`
no runtime do deployment (estende a guarda do WP-4 para todos os Core), e check de release que
falha se algum cair em vanilla. Documentar o contrato.

### WP-C4 — Smoke test por ModelAdmin + páginas custom ✅ (`9fc33b94`)
> Concluído. `shopman/backstage/tests/test_admin_smoke.py` (67 models × changelist+add,
> +Order change semeado, +7 páginas console), plugado no `make admin`. Pegou e corrigiu o
> Product 500 (campos de nutrição → declarados em escopo de classe). Varredura: 0 outras quebras.

**Ação:** teste que percorre `admin.site._registry` e faz GET no changelist e no add/change de
cada model (com um objeto seed), + GET de cada página `admin_console`, afirmando 200 e ausência
de erro de template/field. Pega `list_display`/`fieldsets` quebrados, ações órfãs, imports.

### WP-C5 — Higiene de superfícies legado (coordenar com SURFACE-CONVERGENCE-PLAN) ⏸️ ADIADO
> Adiado por decisão do Pablo (2026-06-19): o kill do POS-HTMX legado (migração de ~12 testes
> `test_pos_*` + remoção de views/templates/rotas) será tratado no `SURFACE-CONVERGENCE-PLAN`,
> não nesta revisão. Camada 1 entregue como C1-C4 + C3.

POS-HTMX legado (`backstage/views/pos.py`, `templates/pos/`) está morto-vivo (POS é Nuxt). Não é
"Unfold", mas polui o backoffice/nav. **Ação:** confirmar com o Pablo o kill (migrar ~12 testes
`test_pos_*` para a API Nuxt antes), e limpar nav/rotas órfãs. Fora do escopo se o Pablo preferir
tratar no SURFACE-CONVERGENCE.

---

## 3. CAMADA 2 — Completude: tudo que o operador deve poder configurar (P1)

> **Estado (2026-06-19): CAMADA 2 ENTREGUE.** WP-D1 ✅ `56434cf1`, WP-D2 ✅ `3cbb79c4`,
> WP-D3 ✅ `9dc31b14`, WP-D4 ✅ `23e59470`, WP-D5 ✅ (este). Branch `feat/admin-config-omotenashi`.
> `make test`(2088)/`lint`/`admin` verdes; verificado ao vivo. Vários achados da auditoria
> estavam desatualizados (já feitos) — confirmado no código. Próximo: Camada 3 (U1-U6).

> Critério: nada que seja **política/operação** fica preso em env, settings ou JSON cru; toda
> capacidade relevante do backend tem porta no admin (campo, ação, inline). Infra real
> (credenciais, timeouts de deploy) fica fora — triagem item a item com o Pablo (como no WP-5).

### WP-D1 — Settings/env → Admin (continuação do WP-5)
Triar e migrar para config tipada da Loja (`Shop.defaults`/`Shop.integrations` ou proxies) o que
for **política**, mantendo infra fora. Candidatos achados na auditoria:
`SHOPMAN_STOREFRONT_CHANNEL_REF`, `SHOPMAN_POS_CHANNEL_REF`, `GOOGLE_MAPS_API_KEY` (chave →
provavelmente infra/secret, decidir), `MANYCHAT_WEBHOOK_SECRET` (secret → infra), seleção de
adapters de pagamento/notificação (`Shop.integrations` já existe — **tipá-lo** com dropdowns dos
adapters disponíveis em vez de JSON). **Regra:** secret/credencial = infra (fora); ref de canal /
escolha de adapter = política (admin). Coletar decisão do Pablo item a item.

### WP-D2 — JSONField cru → tipado/parseado ✅
> Concluído. `PaymentIntent.gateway_data` → display **parseado** read-only (expande o
> client_secret/QR da EFI, rótulos amigáveis, sem JSON cru) + fieldsets agrupados;
> `Order.data` → aba **Resumo** com visão curada (tipo, cliente, endereço, entrega, taxa,
> cupom, observações, presente). Recipe.steps/meta e RecipeItem.meta **já eram tipados**
> (steps_text + meta fields — achado da auditoria estava desatualizado). Hold/POSTerminal/
> Product.metadata: dados avançados raramente tocados, JSONField cru mantido (sem valor de
> tipar). Verificado ao vivo.

Por domínio, dar forma a JSONs que o operador precisa ler/editar:
- `Order.data` — editor/visão tipada (fulfillment_type, delivery_address, notes, gift) read-side
  pelo menos parseado; write só onde seguro (respeitar CommitService como contrato).
- `PaymentIntent.gateway_data` — **display parseado** por gateway (PIX: txid/QR; cartão:
  brand/last4/auth) em vez de JSON cru. Read-only (mutado via PaymentService).
- `Product.metadata`, `Recipe.steps` (ArrayWidget ordenável), `Recipe.meta`, `RecipeItem.meta`,
  `Hold.metadata`, `POSTerminal.metadata` — formas tipadas ou displays. Core → via `contrib/admin_unfold`.
- `Shop.integrations` / `Shop.opening_hours` / `tracking_copy` — verificar o que já ficou tipado
  no WP-1..8; completar o que faltar.

### WP-D3 — Inlines e campos faltando ✅
> Concluído. Achados da auditoria estavam majoritariamente DESATUALIZADOS (verificado no
> código + ao vivo): `OrderItem.meta` já em readonly_fields do inline; `Listing.description`
> já editável no fieldset; `ProductComponent` já renderizava `qty` (sem `fields=` → todos os
> campos; `unit` não existe no modelo, é atributo do Product pai); RecipeItem dietário já
> exposto via `diet`/`allergens_text`. Única ação: tornar o inline de bundle **explícito**
> (`fields=["component","qty"]`) p/ a quantidade ficar sempre visível/intencional.

- `ProductComponent` inline sem `quantity`/`unit` (bundle sem quantidade visível).
- `OrderItem.meta`, `RecipeItem.meta` invisíveis nos inlines.
- `Listing.description` não editável.
(Tudo em Core → `contrib/admin_unfold`.)

### WP-D4 — Ações faltando (admin actions) ✅
> Concluído. **PaymentIntent: reembolso total** (`PaymentService.refund`) via row action +
> bulk (DANGER); parcial deliberadamente fora (exige form de valor + cuidado financeiro).
> **Quant: recalcular** (`quant.recalculate()`) bulk. **Coupon: zerar contador** de usos.
> **CashMovement: admin auditado** registrando sangria/suprimento/ajuste (inclusive pós-
> fechamento), valor em Reais→centavos, `created_by` carimbado; existentes imutáveis (trilha).
> Testes novos (cash reais→centavos + audit; coupon reset) + verificado ao vivo.

- **PaymentIntent: reembolso** (parcial/total) via `PaymentService` (não há porta hoje).
- **Quant: recalcular** cache divergente (`quant.recalculate()`).
- **Coupon: resetar contador** de usos.
- **CashShift: corrigir fechamento** / **registrar sangria/suprimento** pós-fechamento (com audit).
- Revisar todas as ações existentes: cada uma tem efeito e feedback ao operador.

### WP-D5 — Read-only ↔ editável (com audit) ✅
> Concluído. **Destravado:** `CashShift.notes` (gerente anota/corrige turno fechado; auditado
> pelo histórico do admin/LogEntry). **Travado (o inverso):** `OperationTaskRunAdmin` não tinha
> nenhum readonly_field — evidência (`evidence_text/number/data`) e trilha de execução
> (`executed_by/at`, `supervised_by/at`), que são o registro anti-fraude capturado pelo app,
> agora são read-only; `status`/`notes` seguem corrigíveis (auditados). Testes de contrato +
> verificado ao vivo. `evidence_*` decidido como app-only (read no admin).

Campos que o operador precisa ajustar e hoje são read-only: `CashShift.notes`,
`OperationTaskRun.evidence_*` (decidir — pode ser só via app), etc. Editar **sempre com trilha**
(quem/quando). E o inverso: travar o que não deveria ser editável.

---

## 4. CAMADA 3 — UX de primeira linha (P2, benchmark-grade)

> Critério: um operador novo entende e opera sem treino; nada fica atrás de Shopify/Odoo/STORES/
> Take.app em clareza, densidade certa, descoberta e velocidade. Tudo canônico Unfold.

### WP-U1 — Navegação / Arquitetura de Informação final
Revisão completa da sidebar (grupos, ordem, ícones, badges de atenção), separando claramente
**Operação ao vivo** · **Dados** (catálogo/pedidos/clientes/estoque) · **Configurações** ·
**Auditoria**. Quick actions no topo. (WP-2 já criou "Configurações"; aqui é a passada final no todo.)

### WP-U2 — Changelists nível benchmark (todas as listas)
Para cada ModelAdmin de dados/config: `list_display` rico (badges de status/tipo, valores
formatados em R$/data pt-BR), `list_filter` com filtros Unfold (dropdown/radio/date-range),
`search_fields` úteis, `autocomplete_fields` para FKs grandes, `list_editable` onde fizer sentido,
ordenação/sortable, **empty states** ("nenhum X ainda — crie o primeiro"), `compressed_fields`,
exportação onde útil. Benchmark: a list view do Shopify (Orders/Products) e Odoo (list+kanban).

### WP-U3 — Change forms nível benchmark
Tabs/sections do Unfold para forms longos; agrupamento lógico; help text acolhedor; validação
cedo/inline; previews onde agregam (cores/tipografia/storefront já existem — padronizar).

### WP-U4 — Dashboard (home do admin)
Home com KPIs do dia (pedidos novos, em produção, fechamento pendente, alertas), atalhos e
gráficos — à la "Home" do Shopify. Consumir projection `dashboard.py` registrada (contrato canônico).

### WP-U5 — Consoles operacionais (Pedidos/Produção/Fechamento)
Passada de UX nas páginas `admin_console` (já canônicas/WP8): fluxo, densidade, feedback,
responsividade, consistência com os changelists. Benchmark: fila de pedidos do Take.app, KDS/board.

### WP-U6 — Consistência transversal
Paleta de badges única; ícones coerentes; **i18n pt-BR completo** (estender `locale/pt_BR` a toda
string do Unfold que aparecer); datas/moeda pt-BR; acessibilidade (omotenashi 1ª classe).

### Decisão pendente — KDS
HTMX hoje vs Nuxt. Afeta convergência de design. Decisão do Pablo (coordena com SURFACE-CONVERGENCE).

---

## 5. Sequenciamento e gates

Ordem obrigatória pelas camadas: **Camada 1 (C1–C5) → Camada 2 (D1–D5) → Camada 3 (U1–U6)**.
Dentro de cada camada, os WPs são majoritariamente independentes (paralelizáveis com cuidado).

**Gate por WP (inegociável):**
- `make test` + `make lint` + `make admin` verdes.
- Verificação **ao vivo** no admin (preview Django porta 8000; navegar `127.0.0.1`) — mostrar a
  tela funcionando, não só testes.
- Commit por WP; atualizar este plano (marcar WP) + memória `project_admin_config_omotenashi` +
  `MEMORY.md`.
- **Nada de gambiarra**; solução mais correta pelo mérito (nunca menor-diff).

---

## 6. Restrições (Unfold Canonical Gate + arquitetura)

- **Gate canônico (`make admin`):** sem `<input>/<select>/<textarea>/<button>/<table>` cru; sem
  `style=` inline (mesmo em UI autorizada); componentes via `{% component "unfold/..." %}`;
  páginas custom seguem o contrato (`UnfoldModelAdminViewMixin` + `TemplateView` + projection
  registrada em `backstage/projections/`); widgets via `UnfoldAdmin*Widget`. Waiver só com
  autorização real do Pablo para a superfície exata. Ver `docs/engineering/unfold_canonical_policy.md`,
  `unfold_admin_page_playbook.md`, `unfold_canonical_inventory.md`, `.codex/skills/unfold-admin-canonical/SKILL.md`.
- **Core sagrado:** admin de packages só em `packages/*/contrib/admin_unfold/`; nunca acoplar
  Core→shop; preferir JSONField a novo campo; entender antes de mudar.
- **Exceções não-Unfold:** POS e Storefront são Nuxt; KDS é HTMX (decisão pendente). Não "unfoldizar".
- **`ordering_field` (lista arrastável)** só funciona com ordenação **ascendente** do campo
  (`sortRecords` faz `value = index`, topo→base); campos "peso/descendente" (priority) não encaixam
  sem inverter semântica (decisão do Pablo caso a caso).

---

## 7. Execução / sessão

Este plano é a **fonte de verdade**, auto-contido. Recomendação: **executar em sessão(ões) nova(s)**,
um WP (ou poucos) por vez, começando pela Camada 1. Cada sessão lê: (1) memória
`project_admin_config_omotenashi`; (2) este plano; (3) a seção "Admin/Unfold — Regra de
Canonicidade" do CLAUDE.md + os docs de política do §6; (4) o WP-alvo aqui.

**Antes de começar a execução:** decidir com o Pablo a **base** (mergear `feat/admin-config-omotenashi`
no `main` primeiro, ou ramificar a partir dela) e o **publish** dos WP-1..8 já prontos.
