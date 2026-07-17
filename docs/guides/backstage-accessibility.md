# Backstage Accessibility Baseline

Baseline operacional para POS, KDS, Pedidos, Produção e Fechamento.

## Regras

| Área | Baseline |
|---|---|
| Touch targets | Ações principais devem usar `min-h-11`, `size-11` ou equivalente quando a superfície for touch-first. Ações densas de tabela podem usar `h-8` somente quando há alternativa textual/contextual. |
| Ícones | Botões só com ícone precisam de `aria-label` ou `title` claro. |
| HTMX | Regiões que recebem refresh operacional devem declarar `aria-live` ou estado visual de carregamento. |
| Modais | `role="dialog"` e `aria-modal="true"` quando bloqueiam o fluxo. |
| KDS | Novos tickets anunciam por `aria-live="polite"` e som opcional persistido por estação. |
| Produção | Avisos de insumo e pedidos vinculados usam modal/alert legível e ação de confirmação explícita. |

## Auditoria 2026-04-28

| Surface | Status | Observações |
|---|---|---|
| POS | Monitorado por testes existentes de layout/keyboard. |
| KDS pedidos | SSE `kds`, `aria-live`, toggle de som com `Alt+S`. |
| Pedidos | Badge de produção no card e detalhe colapsável com progressbar. |
| Produção | Relatórios, links de pedidos vinculados e warning de redução com modal. |
| Fechamento | Card de produção do dia e bloco de discrepâncias com badges textuais. |

## Cobertura Automatizada

Baseline enforced via testes — falham se regredir:

| Teste | Verifica |
|---|---|
| `tests/test_a11y_backstage_baseline.py` | Templates estáticos: `aria-live`, `role="dialog"`, `aria-modal`, conteúdo textual de discrepâncias. |
| `tests/test_a11y_dynamic.py` | Render real de cada surface (POS, KDS, Pedidos, Produção, Dashboard, KDS produção, Relatórios, Fechamento, Alertas). Heading hierarchy, `<main>` landmark, botões com nome acessível, dialogs bem-formados. |
| `tests/test_a11y_keyboard.py` | Skip link `#backstage-main`, ausência de `tabindex` positivo, focusable em modais, navegação landmark com `aria-label`. |
| `tests/test_exception_hygiene.py` | Nenhum `except Exception` silencioso (todos com `logger.*` ou `raise`). |

## Skip Link

`gestor/base.html` injeta `<a href="#backstage-main">Pular para o conteúdo principal</a>` como primeiro filho do `<body>`. Visível ao receber foco (Tab a partir do load). O `<main>` tem `id="backstage-main"` e `tabindex="-1"` para ser alvo programático.

## Live Regions

- `#operator-alerts-panel` em `gestor/base.html`: `role="status"` + `aria-live="polite"` + `aria-relevant="additions"` — anuncia novos alertas.
- KDS display: `aria-live="polite"` + `aria-relevant="additions"` no container de tickets.
- Sync produção↔pedidos: dependências de OP aparecem no detalhe Admin de pedidos com percentual de avanço por OP.

## Como Auditar Localmente

1. Rodar `python manage.py runserver`.
2. Abrir `/admin/operacao/pedidos/`, `/admin/operacao/kds/<ref>/`, `/admin/operacao/fechamento/`, `/gestor/pos/` e `/gestor/producao/kds/`. (A produção é o Fournil, `surfaces/production-nuxt`; auditar lá.)
3. Rodar axe DevTools em cada tela.
4. Testar navegação por teclado nos fluxos críticos.
5. Em macOS, ativar VoiceOver e validar que os updates do KDS e alertas do fechamento são anunciados.

## Riscos Conhecidos

As tabelas densas de produção usam alguns botões compactos (`h-7`/`h-8`) por ergonomia operacional em matriz. Onde isso ocorre, há `title`/`aria-label` e a ação principal também aparece em contexto expandido.
