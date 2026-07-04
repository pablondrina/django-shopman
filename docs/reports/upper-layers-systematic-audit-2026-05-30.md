# Auditoria sistemática — camadas acima do Core

**Data:** 2026-05-30
**Branch:** `feat/pos-phase2-comanda`
**Escopo:** `shopman/shop` (orquestrador), `shopman/storefront`, `shopman/backstage`.
`packages/` (Core/kernel) **não** auditado, exceto para confirmar fronteiras.
Surfaces Nuxt (`surfaces/*`) = eixo separado, não coberto aqui.
**Método:** fan-out de 5 agentes Explore read-only (camada × dimensão), com
verificação manual no código real dos achados de maior severidade antes de
reportar. Sucessora de [`upper-layers-smell-audit-2026-05-29.md`](upper-layers-smell-audit-2026-05-29.md).

---

## Sumário executivo

A conclusão da auditoria anterior **se mantém: não há rot sistêmico.** A
disciplina das 3 camadas é alta — fronteira de dependência respeitada (inclusive
o padrão de adapter lazy-import em `shop/adapters/`), sem duplicação de lógica de
negócio entre camadas, sem código morto relevante, zero marcadores TODO/FIXME
reais, e `except Exception` silenciosos zerados (catraca em `{shop: 0,
storefront: 0}`).

**Porém a auditoria anterior fechou o A1 (alias `CashRegisterSession`) cedo
demais.** Existe uma **segunda camada de resíduo do mesmo rename** que passou
batido: shims de compatibilidade no model `CashShift`/`CashMovement` e nos
services POS, mantidos **vivos apenas para os testes antigos não quebrarem**.
Isso viola a mesma regra constitucional (`Zero backward-compat aliases` /
`Zero residuals em renames`) que o A1 — é o achado mais importante deste passe.

### Contagem por severidade

| Severidade | Qtd | Achados |
| --- | --- | --- |
| 🔴 Alto | 1 | C1 — resíduo de rename `CashShift`/`CashMovement` (shims test-only) |
| 🟡 Médio | 3 | D1 (keys JSONField não documentadas), E1 (`_bootstrapped` não resetado), E2 (cache `shop_singleton` não resetado) |
| 🟢 Baixo/benigno | 4 | colors.py args mortos, `_legacy_payment_method`, `HAS_STOCKMAN` triplicado, vertical food no kernel (backlog conhecido) |

### Os achados que importam (top 4)

1. **🔴 C1 — Rename `CashRegisterSession→CashShift` ainda tem resíduo vivo.**
   O A1 removeu o alias de classe, mas deixou: property `closing_amount_q`
   ("Compatibility alias for the former field name"), tradução de kwargs
   `session`→`shift` no `__init__`/queryset/manager do `CashMovement`, e os
   wrappers `open_cash_session`/`close_cash_session` ("Compatibility wrapper for
   the former service name"). **Todos consumidos só por testes** — produção já
   usa os nomes novos. É exatamente a doença do A1, meio-curada.

2. **🟡 D1 — 4 chaves JSONField não documentadas** em `Order.data`:
   `pos_committed_at`, `client_request_id` (POS), `external_order_code`,
   `merchant_id` (iFood). As `nfce_*` da auditoria anterior **já foram
   documentadas** (gap fechado).

3. **🟡 E1/E2 — Estado global de processo não resetado entre testes:** flag
   `rules.engine._bootstrapped` e cache `shop_singleton`. O `conftest` raiz já
   resolve o registry de validators do orderman + cache de rules (issue
   conhecido, corrigido), mas não estende a mesma higiene a estes dois. A suíte
   está verde hoje (rodada por-package mascara), mas é frágil a reordenação.

4. **🟢 Vertical food/BR no kernel** permanece backlog estratégico conhecido
   (`order.py` valida transições delivery-exclusivas) — re-confirmado, não é
   regressão nova. Ver [[project_analise_critica_codigo_2026_04_18]].

---

## Achados por dimensão

### Dimensão 1 — Aliases / renames incompletos / resíduo de move

#### 🔴 C1 — Resíduo de rename `CashRegisterSession→CashShift` / `session→shift` / `closing_amount_q→blind_closing_amount_q`

A auditoria anterior (A1) removeu o alias de classe `CashRegisterSession =
CashShift`. Mas o **mesmo rename** deixou três famílias de shim de
backward-compat vivas, **consumidas exclusivamente por testes** (produção já
migrou para os nomes novos):

| Local | Resíduo | Consumidor |
| --- | --- | --- |
| `backstage/models/cash_register.py:129-136` | property+setter `closing_amount_q` → docstring literal "Compatibility alias for the former field name"; mapeia p/ `blind_closing_amount_q` | `test_pos_cash_service.py:102` |
| `backstage/models/cash_register.py:146-158` | `CashShift.close()` aceita **dois** kwargs (`blind_closing_amount_q` **e** `closing_amount_q`), preferindo o novo — o segundo é compat | `test_pos_cash_register.py:59,69` |
| `backstage/models/cash_register.py:220-237` | `_CashMovementQuerySet` + `_cash_movement_legacy_kwargs` — traduz kwargs `session`/`session_id` → `shift`/`shift_id` em `.filter/.get/.exclude` | `test_pos_cash_register.py:137` |
| `backstage/models/cash_register.py:286-291` | `CashMovement.__init__` traduz kwarg `session=`/`session_id=` → `shift=`/`shift_id=` | `test_pos_cash_register.py:76` |
| `backstage/models/cash_register.py:293+` | properties `session`/`session_id` espelhando os FKs antigos | (espelho do acima) |
| `backstage/services/pos.py:36-42` | `open_cash_session()` → docstring "Compatibility wrapper for the former service name"; delega a `open_cash_shift()` | `test_pos_cash_service.py:26,27` |
| `backstage/services/pos.py:88-94` | `close_cash_session()` → idem; delega a `close_cash_shift()` | `test_pos_cash_service.py:86,93` |

**Verificação:** confirmei via grep que **nenhum** desses shims é chamado por
código de produção — só pelos arquivos de teste acima. Os hits de
`has_open_cash_session` (projection) e `session=` em `views/pos.py`,
`omotenashi_qa.py`, `operator/context.py` são, respectivamente, um campo de
projection e a `request.session`/variáveis locais do Django — **não** o FK
renomeado.

**Por que é 🔴:** viola diretamente `Zero backward-compat aliases` e `Zero
residuals em renames` (regras constitucionais do CLAUDE.md). É o mesmo padrão do
A1, que a auditoria anterior julgou resolvido. A raiz é a mesma do "cheiro" que o
Pablo sentiu: a disciplina de rename do Core escorregou na superfície — aqui os
**testes** não foram migrados junto com a produção, e shims foram criados para
mascarar isso em vez de atualizar os testes.

**Recomendação (estrutural — pede autorização explícita antes de aplicar):**
migrar os ~5 call-sites de teste para os nomes novos
(`open_cash_shift`/`close_cash_shift`, `shift=`/`shift_id=`,
`.close(blind_closing_amount_q=)`, `.blind_closing_amount_q`) e **deletar todos
os shims** (properties, queryset custom, `__init__` translation, kwargs compat
de `close()`, wrappers de service). Baixo risco (mecânico), mas toca model +
service + 2 arquivos de teste → não é fix de 1 linha.

#### 🟢 Limpos (verificados)
- Personas antigas (Offering/Stocking/Crafting/Ordering) **não** vazam em código
  não-migration; `OrderingValidationError` é símbolo legítimo do `orderman`.
- `.code` vs `.ref`: sem mau uso; hits são `exc.code`, `rule.code`,
  `Product.sku`, `WorkOrder.code` (exceções deliberadas).
- Nenhum alias de classe `OldName = NewName` em código vivo.

### Dimensão 2 — Gambiarras / workarounds

#### 🟢 colors.py — args mortos (cosmético, já conhecido)
`shop/colors.py:253-268` — `generate_design_tokens()` aceita 5 args de cor
**ignorados** ("mantidos só por compatibilidade de assinatura"). Conhecido da
auditoria anterior. Cosmético; remover os params mortos quando conveniente.

#### 🟢 `_legacy_payment_method` — helper de migração legítimo
`shop/services/pos.py:1290-1307` — reconstrói método de pagamento de formatos de
order antigos (payload → tenders → requested). Não é gambiarra; é fallback de
dados intencional. **OK.**

### Dimensão 3 — TODO/FIXME/HACK/XXX reais

🟢 **Zero reais** — reconfirmado. Os "for now" em
`omotenashi/context.py` e `services/storefront_context.py` são comentários
explicativos de comportamento, não marcadores de dívida.

### Dimensão 4 — Bypass do Core

#### 🟢 `ifood_ingest` — bypass conhecido e justificável (sem mudança de status)
`shop/services/ifood_ingest.py:121` cria `Order` direto e monta `snapshot` à mão,
paralelo ao `CommitService`. Já documentado na auditoria anterior como bypass de
marketplace (pedido externo pré-pago, sem sessão). Permanece 🟡 conhecido —
candidato a um service de ingestão no Core algum dia, **não urgente**.

#### 🟢 Resto limpo (verificado)
- Sem mutação rogue de `session.items` fora do `ModifyService`.
- `Directive.objects.create(...)` (11 sites) = padrão correto da fila.
- `Session.objects.create` em `sessions.py` = legítimo (orquestrador).

### Dimensão 5 — JSONField não documentado

#### 🟡 D1 — 4 chaves de `Order.data` não documentadas em `data-schemas.md`

| Chave | Escrita em | Contexto |
| --- | --- | --- |
| `pos_committed_at` | `shop/services/pos.py` (`_mark_tab_committed`) | timestamp ISO de finalização POS (pós-commit) |
| `client_request_id` | `shop/services/pos.py` (`_mark_tab_committed`) | chave de idempotência de checkout POS |
| `external_order_code` | `shop/services/ifood_ingest.py:102` | ID externo iFood (duplicado em `ifood.order_code`) |
| `merchant_id` | `shop/services/ifood_ingest.py:103,115` | ID do merchant iFood (duplicado em `ifood.merchant_id`) |

**Verificação:** confirmei via grep que as 4 não constam em
`docs/reference/data-schemas.md`. As `nfce_*` da auditoria anterior **já estão
documentadas** (10 hits) — gap fechado. `trusted` não existe mais no código.

**Recomendação (doc-only, baixo risco):** registrar as 4 chaves em
`data-schemas.md` (seção pós-commit / seção iFood). Avaliar a duplicação
`external_order_code` vs `ifood.order_code` (consolidar num só lugar).

### Dimensão 6 — Fronteira / acoplamento

🟢 **Compliant.** Verificado pelo agente + spot-check:
- `storefront` ↔ `backstage`: **zero** imports de produção entre si (único hit é
  `test_checkout_error_paths.py:52` importando `CashShift` para setup de teste —
  aceitável).
- `shop/adapters/{kds,pos,alert,promotion,pricing}.py` importam de
  backstage/storefront via **lazy import dentro de função**, documentado nos
  headers ("Keeps shop/ free of direct shopman.backstage imports"). Padrão de
  adapter intencional e correto, não violação.
- `packages/**` **não** importa de shop/storefront/backstage (kernel limpo).
- Sem imports profundos a símbolos privados (`_x`) entre pacotes; tudo via
  re-exports públicos.

🟢 **Vertical food/BR no kernel** (backlog conhecido, não regressão):
`packages/orderman/.../models/order.py:216-230` valida transições
delivery-exclusivas (`fulfillment_type`/`delivery_method`). Conceitos genéricos
de fulfillment, não food-específicos. Já mapeado em
[[project_analise_critica_codigo_2026_04_18]] como WP-ARCH-vertical-extraction.

### Dimensão 7 — Duplicação / código morto / handlers legacy

🟢 **Limpo.** Verificado:
- Formatação monetária/telefone centralizada em `shopman.utils`
  (`format_money`); sem reimplementação nas camadas.
- Cart/pricing/availability: storefront e backstage **delegam** a
  `shop/services/*` (facade pattern), não duplicam.
- Handlers em `shop/handlers/__init__.py` (`ALL_HANDLERS`, 25+) — todos com site
  de dispatch (alguns via directive por string, verificado). Sem handler órfão.
- Feature flags `HAS_STOCKMAN`/`HAS_AUTH` — legítimas e condicionais, não aliases.

🟢 **Menor:** `HAS_STOCKMAN = True` redefinido em 3 arquivos
(`storefront/constants.py:35`, `backstage/projections/_helpers.py:12`,
`shop/services/substitutes.py:17`) em vez de importado de um módulo único.
Sem impacto funcional; centralizar quando conveniente.

### Dimensão 8 — Higiene de teste / estado global de processo

O `conftest` raiz (`shopman/conftest.py`) **já** resolve os dois vazamentos
conhecidos via autouse `_isolate_rules_state`: snapshot/restore do registry de
validators do `orderman` + `cache.delete(CACHE_KEY)` das rules. Storefront tem
fixtures que limpam omotenashi copy + rate-limit. **Esses estão corretos.**

Dois stores de processo **não** cobertos por nenhuma fixture:

#### 🟡 E1 — `rules.engine._bootstrapped` nunca resetado
`shop/rules/engine.py:35-36,152-175` — flag module-level `_bootstrapped: bool`.
Setada `True` uma vez por `bootstrap_active_rules()`, nunca volta a `False`.
Um teste que altera disponibilidade do DB ou espera re-bootstrap não consegue.
**Recomendação:** estender `_isolate_rules_state` para resetar
`rules_engine._bootstrapped = False` no teardown.

#### 🟡 E2 — cache `shop_singleton` não limpo entre testes
`shop/models/shop.py:322-328` — `Shop.load()` cacheia sob `SHOP_CACHE_KEY`;
`.save()` invalida. Mas testes que criam/alteram `Shop` sem `cache.delete` deixam
instância stale; um teste seguinte com `Shop.load()` pode pegar a antiga (a row
some no rollback, o cache não). Vários testes de storefront criam `Shop` por
fixture sem limpar o cache no teardown.
**Recomendação:** `cache.delete(SHOP_CACHE_KEY)` em fixture autouse de teardown
(raiz ou storefront conftest).

**Nota de severidade:** E1/E2 não causam falha hoje (`make test` verde, e a
execução por-package reduz a exposição), mas são frágeis a reordenação de testes
e à eventual migração para uma execução conjunta. 🟡 = estado global não-resetado
confirmado, ainda não-reproduzido como falha.

🟢 Signals (`apps.py`, `_sse_emitters.py`) usam `dispatch_uid` → idempotentes,
sem risco de dupla conexão. **OK.**

---

## Ordem de ataque — RESOLVIDO (autorizado pelo Pablo, 2026-05-30)

| Ordem | Achado | Status |
| --- | --- | --- |
| 1 | **C1** — deletar shims de rename do cash + migrar testes | ✅ APLICADO |
| 2 | **D1** — documentar 6 chaves JSONField em `data-schemas.md` | ✅ APLICADO |
| 3 | **E1+E2** — estender `conftest` (reset `_bootstrapped` + `shop_singleton`) | ✅ APLICADO |
| 4 | 🟢 colors.py args mortos + `HAS_STOCKMAN` centralizado + dedup `external_order_code`/`ifood.order_code` | pendente (oportunístico) |

### O que foi feito

- **C1** — Removidos TODOS os shims de backward-compat do cash register:
  property `closing_amount_q` + kwarg compat de `close()`, custom queryset
  `_CashMovementQuerySet` + `_cash_movement_legacy_kwargs`, `CashMovement.__init__`
  com tradução `session→shift`, properties `session`/`session_id`, e os wrappers
  `open_cash_session`/`close_cash_session`. Migrados os ~5 call-sites de teste
  para os nomes novos; deletadas as assertions/blocos que existiam só para testar
  os shims. **Bônus:** limpos os resíduos de vocabulário internos
  (`cash_session` var → `cash_shift` em `views/pos.py` e `operator/context.py`;
  campo `OperatorContext.shift_cash_session_id` → `cash_shift_id`). Verde:
  backstage 427, shop 868.
  - **Deixado de fora (separate axis):** a chave de projection
    `has_open_cash_session` (`backstage/projections/pos.py:240,323`) é consumida
    pelas surfaces **Nuxt** (`pos-nuxt`, `backstage-nuxt`) — renomear
    cruza o contrato headless. 🟢 follow-up no eixo de superfícies.
- **D1** — Documentadas as 6 chaves em `data-schemas.md` (seção pós-commit):
  `pos_committed_at`, `client_request_id`, `pos` (POS) e `external_order_code`,
  `merchant_id`, `ifood` (ingest iFood).
- **E1+E2** — `shopman/conftest.py` `_isolate_rules_state` agora também reseta
  `rules.engine._bootstrapped` e o cache `shop_singleton` (SHOP_CACHE_KEY) ao
  redor de cada teste. **Isso expôs uma poluição latente real:**
  `test_lifecycle.py::test_shop_defaults_manual_no_auto_action` chamava
  `Shop.load()` assumindo que existia um `Shop` — só passava porque um teste
  irmão deixava um cacheado. Corrigido com o padrão self-sufficient
  (`Shop.objects.get_or_create` antes do `load()`). Verde: shop 868, storefront 882.
