# BACKSTAGE-MATURITY-PLAN — v3

Plano de ação para elevar a camada `shopman/backstage/` (POS, KDS, Pedidos, Produção, Fechamento) ao mesmo nível de maturidade do core (`packages/*`) e do `shopman/storefront/`.

> Status: ativo — v3 em 2026-04-28
> v1 (manhã) propôs WP-BS-1..6. v2 (tarde) confirmou WP-BS-1..5 entregues e detalhou WP-BS-7..12.
> v3 (noite) confirma WP-BS-7..11 entregues no código. Resta WP-BS-12 parcial + 3 WPs finais (13/14/15) de refinamento.
> Escopo: somente `shopman/backstage/`. Core (`packages/`, `shopman/shop/`) não muda. Storefront não muda.

---

## 1. Estado atual

### 1.1 Score de maturidade

| Camada | Maturidade | Score |
|---|---|---|
| `packages/*` (core) | ⭐⭐⭐⭐⭐ | — |
| `shopman/shop/` (orquestrador) | ⭐⭐⭐⭐⭐ | — |
| `shopman/storefront/` | ⭐⭐⭐⭐ | — |
| `shopman/backstage/` | ⭐⭐⭐⭐ | **~85/100** (v1: 56, v2: 68, v3: 85) |

A camada deixou de ter dívidas arquiteturais. O que resta é **refinamento**: observabilidade, automação de a11y e cobertura cross-area.

### 1.2 WPs entregues (auditoria de código real)

| WP | Estado | Evidência |
|----|---|---|
| WP-BS-1 — Tirar Produção do admin | ✅ done | `views/production.py` sem `admin_site`, namespace `backstage:`, herda `gestor/base.html` |
| WP-BS-2 — KDS produção + Dashboard + Alertas | ✅ done | `projections/production.py` (`build_production_dashboard/kds`), templates `gestor/producao/{dashboard,kds}.html`, handler `production_alerts.py` com 3 triggers, migration 0003 |
| WP-BS-3 — SSE backstage | ✅ done | `_emit_backstage` em `shop/handlers/_sse_emitters.py` cobrindo orders, production, kds, alerts. `test_backstage_sse.py` |
| WP-BS-4 — Operator context + design unificado | ✅ done | `operator/context.py` + `context_processors.py`. Zero `--ped-*`/`--kds-*` em templates, zero herança de `admin/base_site.html` |
| WP-BS-5 — Service layer + cobertura | ✅ done | 7 services tipados, 166 testes / 3.2k linhas em backstage |
| WP-BS-7 — Relatórios CSV produção | ✅ done | `views/production.py:149` `StreamingHttpResponse`, `services/production.py:187` `export_reports_csv`, templates `producao/relatorios/`, migration 0004, `test_production_reports.py` (11 testes) |
| WP-BS-8 — Cobertura + e2e | ⚠️ parcial | 166 testes incluindo projections. Falta e2e cross-area coordenado. **Resolvido em WP-BS-14**. |
| WP-BS-9 — Sync produção↔pedidos | ✅ done | `Order.data["awaiting_wo_refs"]` + `WorkOrder.meta["committed_order_refs"]`, `test_production_order_sync.py`, templates `wo_commitments.html` + `partials/order_shortage.html` |
| WP-BS-10 — SSE KDS + audio | ✅ done | `emit_kds_change` em `_sse_emitters.py:194-206`, `test_kds_sse.py` + `test_kds_audio.py`, Alt+S, polling fallback 30s, `docs/guides/backstage-realtime.md` |
| WP-BS-11 — Reconciliação + Recipe.steps | ✅ done | `DayClosing.data["reconciliation_errors"]`/`production_summary`, `test_day_closing_reconciliation.py`. `current_step/step_progress_pct` em `projections/production.py`, `test_production_kds_steps.py` |
| WP-BS-12 — A11y sistemática | ⚠️ parcial | `test_a11y_backstage_baseline.py` valida HTML estático (ARIA, role=dialog, min-h-11). Falta automação dinâmica (axe + keyboard e2e). **Resolvido em WP-BS-14**. |

### 1.3 Princípios (mantidos)

1. **Core é sagrado** — não toca `packages/*` nem `shopman/shop/services/production.py`.
2. **Reutilizar antes de criar**.
3. **Zero gambiarras**.
4. **Zero residuals em renames**.
5. **Persona names only**.

---

## 2. Resumo dos Work Packages restantes

| WP | Título | Prioridade | Estimativa |
|----|---|---|---|
| WP-BS-13 | Exception hygiene + observabilidade | 🟠 | 4h |
| WP-BS-14 | A11y automation + e2e cross-area | 🟠 | 10-14h |
| WP-BS-15 | Polish final (CSV download, schemas, validação, override UI, multi-instance) | 🟡 | 6h |

**Total: ~3 dias de trabalho.** Sem dependência entre os 3 — paralelizável. Ordem sugerida: 13 → 15 → 14 (mais barato → polish → maior).

---

## 3. Work Packages

### WP-BS-13 — Exception hygiene + observabilidade

**Prioridade:** 🟠 Alta
**Estimativa:** 4h

#### Objetivo
Eliminar 16 ocorrências de `except Exception` sem rethrow/log consistente. Padronizar via decorator com observabilidade.

#### Escopo

1. **Inventário factual** dos 16 sites:
   - `projections/production.py` (3+)
   - `projections/closing.py` (1)
   - `projections/pos.py` (2)
   - `projections/order_queue.py` (1)
   - `projections/dashboard.py` (3)
   - `services/production.py` (3)
   - `views/production.py` (1)
   - `views/pos.py` (1)
   - `admin/dashboard.py` (1)

2. **Classificação**:
   - **Degradar graciosamente** (projections de UI, admin dashboard): manter catch, adicionar log + decorator `@robust_projection` que retorna fallback tipado.
   - **Bug real escondido** (services, views): converter em exception tipada que sobe.

3. **Decorator `@robust_projection(fallback)`** em `projections/_helpers.py`:
   - Captura `Exception`, loga via `logger.warning(..., exc_info=True)` no logger do módulo.
   - Retorna `fallback` (passado como argumento ou default factory).

4. **Aplicar nos sites** classificados como UI degradation.

5. **Converter** sites de service/view em exceptions tipadas (já existe `ProductionError`, `POSError`, etc.).

#### Entregáveis
- `projections/_helpers.py::robust_projection` decorator
- 16 sites refatorados (cada um com log explícito ou exception tipada)
- Teste `test_exception_hygiene.py` que faz `grep`-like assertion: nenhum `except Exception:` sem log no módulo

#### Done
- [ ] `grep -rn "except Exception:\s*$" shopman/backstage/` ≤ 0
- [ ] `grep -rn "except Exception:" shopman/backstage/` cada hit tem `logger.` na linha seguinte ou está dentro de `@robust_projection`
- [ ] `make test` passa

---

### WP-BS-14 — A11y automation + e2e cross-area

**Prioridade:** 🟠 Alta
**Estimativa:** 10-14h

#### Objetivo
Cobertura dinâmica (axe + keyboard + viewports) e cenários cross-area. Hoje a11y é só HTML estático e e2e cross-area é zero.

#### Escopo

1. **Stack de teste dinâmico**:
   - Avaliar `pytest-playwright` + `axe-playwright-python`. Se não instalável no ambiente, fallback: parsing HTML mais profundo com BeautifulSoup + assertions de heading hierarchy / focus order semântico.
   - Asset axe-core em `shopman/backstage/static/test/axe.min.js` (CDN local) se for usar.

2. **Testes a11y dinâmicos** (`tests/test_a11y_dynamic.py`):
   - Render via Django test client + parse HTML profundo:
     - Heading hierarchy (h1 → h2 → h3, sem pulos)
     - Inputs sem label/aria-label
     - Modais sem `role="dialog"` + `aria-modal="true"` + `aria-labelledby`
     - Buttons sem texto nem `aria-label`
   - Surfaces: POS, KDS index, KDS display, Pedidos, Produção (matriz, dashboard, KDS), Fechamento, Relatórios
   - Critério de fail: violations serious/critical = 0; moderate ≤ 2 por surface.

3. **Testes de keyboard** (`tests/test_a11y_keyboard.py`):
   - Tab order via inspeção de `tabindex` e ordem natural de DOM
   - Focus trap em modais (`material_shortage`, `order_shortage`): primeiro/último elemento focável dentro
   - Skip links presentes na base (`gestor/base.html`)

4. **E2E cross-area** (`tests/test_backstage_e2e.py`):
   - **Cenário 1** — Pedido confirmado dispara KDS ticket (orderman + backstage)
   - **Cenário 2** — WO start → finish atualiza estoque + sync `awaiting_wo_refs` no pedido vinculado
   - **Cenário 3** — Tentativa de finish com falta de estoque dispara `ProductionStockShortError` + alert `production_stock_short`
   - **Cenário 4** — POS open cash → venda → close cash → fechamento do dia consolida sem erro
   - **Cenário 5** — `check_late_started_orders` cria alert `production_late` com WO esquecido em STARTED

#### Entregáveis
- `tests/test_a11y_dynamic.py` (≥10 testes)
- `tests/test_a11y_keyboard.py` (≥6 testes)
- `tests/test_backstage_e2e.py` (≥5 cenários)
- Atualização de `docs/guides/backstage-accessibility.md` com baseline real

#### Done
- [ ] ≥10 testes a11y novos passando
- [ ] ≥5 cenários e2e passando
- [ ] `make test` < 90s
- [ ] Acessibilidade documentada em `backstage-accessibility.md` com violations conhecidas

---

### WP-BS-15 — Polish final

**Prioridade:** 🟡 Média
**Estimativa:** 6h

Saco-de-coisas-pequenas. Cada item commit/teste independente.

#### Escopo

1. **CSV download validado** (3 testes em `test_production_reports.py`):
   - Para cada `report_kind` (history, operator_productivity, recipe_waste): GET com `?format=csv` valida Content-Type, BOM UTF-8, headers em PT-BR, presença de cada coluna esperada.

2. **`ReconciliationError` dataclass** em `projections/closing.py`:
   - `@dataclass(frozen=True)` com campos tipados (sku, sold_qty, available_qty, deficit_qty)
   - `build_day_closing` retorna `tuple[ReconciliationError, ...]` em vez de `tuple[dict, ...]`
   - Atualizar `data-schemas.md` com schema canônico

3. **Validação de filtros de relatório** (`production_reports_view`):
   - Form `ProductionReportFiltersForm` em `services/production.py` ou inline
   - Validar `date_from <= date_to`, refs existentes
   - Retorna 400 com mensagem amigável se inválido

4. **UI "Avançar passo" em KDS produção**:
   - Botão no `gestor/producao/kds.html` (ou `partials/kds_cards.html`) chamando endpoint POST que faz `wo.meta["steps_progress"] = N+1`
   - Endpoint `production_advance_step_view` em `views/production.py`
   - Service `apply_advance_step(wo_ref, actor)` em `services/production.py`
   - Teste em `test_production_kds_steps.py`

5. **Teste KDS multi-instance** em `test_kds_sse.py`:
   - 2 `KDSInstance` distintas, cada uma emite/recebe eventos próprios sem cross-talk

#### Entregáveis
- 3 testes novos em `test_production_reports.py`
- `ReconciliationError` dataclass + atualização de schema doc
- Form de validação + 2 testes
- Endpoint + botão + service + 1 teste para advance step
- 1 teste em `test_kds_sse.py`

#### Done
- [ ] Todos os testes passam
- [ ] `data-schemas.md` atualizado
- [ ] `make test` passa

---

## 4. Métricas de sucesso

| Métrica | Hoje | Pós-plano |
|---|---|---|
| Score backstage | ~85/100 | ≥92/100 |
| `except Exception:` broad catch | 16 | ≤ 4 (todos com log) |
| Testes a11y dinâmicos | 0 | ≥16 |
| Cenários e2e cross-area | 0 | ≥5 |
| CSV download validado | 0 | 3 testes |
| Total testes backstage | 166 | ≥185 |

---

## 5. Não-objetivos

- Não toca `packages/*` nem `shopman/shop/services/`.
- Não muda design system / tokens.
- Não introduz Selenium/Playwright se atritar com env — fallback é HTML parsing profundo.
- Não adiciona feature de produto.
- Não muda permissões/roles.
- Não exporta PDF.

---

## 6. Histórico

- **2026-04-28 manhã**: v1 — WP-BS-1..6 propostos
- **2026-04-28 tarde**: v2 — WP-BS-1..5 confirmados done, WP-BS-7..12 detalhados
- **2026-04-28 noite**: v3 — WP-BS-7..11 confirmados done, WP-BS-12 parcial absorvido em WP-BS-14, WP-BS-13/14/15 detalhados
- **2026-04-28 noite (final)**: WP-BS-13/14/15 entregues. 25 testes novos (a11y dinâmica, keyboard, e2e cross-area, exception hygiene). `ReconciliationError` tipado. Skip-link no shell. Live region em `#operator-alerts-panel`. Botão "Avançar passo" no KDS de produção. Suite full: **1552 passed, 0 failed**.
