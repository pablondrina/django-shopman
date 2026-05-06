# Omotenashi Browser QA — 2026-05-06

Rodada local após o seed Nelson passar a incluir checklists operacionais de
abertura, rotina e fechamento.

## Resultado

| Checagem | Resultado |
|----------|-----------|
| `make omotenashi-browser-ci port=8001` | Passou |
| Matriz browser | `14 pass`, `0 review`, `0 fail` |
| Screenshots locais | `/tmp/shopman-omotenashi-qa-screens` |
| Relatório JSON | `/tmp/shopman-omotenashi-qa-browser.json` |

## Matriz Navegada

| Cenário | Viewport | Resultado |
|---------|----------|-----------|
| `mobile.catalog.browse` | 375x812 | pass |
| `mobile.checkout.intent` | 375x812 | pass |
| `mobile.payment.pix_pending_near_expiry` | 375x812 | pass |
| `mobile.payment.pix_expired` | 375x812 | pass |
| `desktop.payment.after_cancel` | 1440x900 | pass |
| `mobile.tracking.ready` | 375x812 | pass |
| `tablet.kds.station` | 1024x768 | pass |
| `tablet.kds.customer_board` | 1280x720 | pass |
| `desktop.orders.queue` | 1440x900 | pass |
| `desktop.marketplace.ifood_stale` | 1440x900 | pass |
| `desktop.pos.counter` | 1280x800 | pass |
| `tablet.production.kds` | 1024x768 | pass |
| `desktop.closing.day` | 1440x900 | pass |
| `desktop.cash_register.shift` | 1280x800 | pass |

## Limite da Evidência

Esta evidência continua sendo headless/local. Para release real ainda é
necessário executar a matriz em staging e em dispositivo físico com toque,
teclado virtual, latência percebida e credenciais sandbox/staging dos gateways.
