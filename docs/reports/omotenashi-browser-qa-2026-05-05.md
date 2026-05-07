# Omotenashi Browser QA — 2026-05-05

Rodada visual/tatil local da matriz Omotenashi usando o seed Nelson, servidor
Django local em `http://127.0.0.1:8000` e Chrome headless via DevTools Protocol.
A execução agora é reproduzível por `make omotenashi-browser-qa strict=1`.

## Resultado

| Checagem | Resultado |
|----------|-----------|
| `make seed` | Passou; banco local foi limpo e recriado com os cenarios deterministicos. |
| `manage.py migrate --noinput` | Passou; health local deixou de apontar migrations pendentes. |
| `manage.py omotenashi_qa --json` | `14 ready`, `0 missing`, `14 total`. |
| `make omotenashi-browser-qa strict=1` | `14 pass`, `0 review`, `0 fail`. |

Screenshots locais foram gerados em
`/tmp/shopman-omotenashi-qa-screens/`. O relatorio JSON bruto ficou em
`/tmp/shopman-omotenashi-qa-browser.json`.

## Matriz Navegada

| Cenário | Viewport | URL | Resultado |
|---------|----------|-----|-----------|
| `mobile.catalog.browse` | mobile 375x812 | `/menu/` | pass |
| `mobile.checkout.intent` | mobile 375x812 | `/checkout/` | pass |
| `mobile.payment.pix_pending_near_expiry` | mobile 375x812 | `/pedido/WEB-260505-8G1B/pagamento/` | pass |
| `mobile.payment.pix_expired` | mobile 375x812 | `/pedido/WEB-260505-H2AD/pagamento/` | pass |
| `desktop.payment.after_cancel` | desktop 1440x900 | `/admin/operacao/pedidos/WEB-260505-0RRQ/` | pass |
| `mobile.tracking.ready` | mobile 375x812 | `/pedido/DELIVERY-260505-FFS3/` | pass |
| `tablet.kds.station` | tablet 1024x768 | `/operacao/kds/estacao/expedicao/` | pass |
| `tablet.kds.customer_board` | tablet/display 1280x720 | `/operacao/kds/cliente/` | pass |
| `desktop.orders.queue` | desktop 1440x900 | `/admin/operacao/pedidos/` | pass |
| `desktop.marketplace.ifood_stale` | desktop 1440x900 | `/admin/operacao/pedidos/IFOOD-260505-RRLC/` | pass |
| `desktop.pos.counter` | desktop/touch 1280x800 | `/gestor/pos/` | pass |
| `tablet.production.kds` | tablet 1024x768 | `/gestor/producao/kds/` | pass |
| `desktop.closing.day` | desktop 1440x900 | `/admin/operacao/fechamento/` | pass |
| `desktop.cash_register.shift` | desktop/touch 1280x800 | `/gestor/pos/` | pass |

## Critérios Observados

- Nenhuma rota caiu em tela de login inesperada com a sessão autenticada.
- Nenhum documento apresentou overflow horizontal global.
- Nenhum controle interativo ficou fora da viewport fora de containers
  horizontalmente rolaveis.
- Cardapio mobile usa rail horizontal de categorias; a parte cortada do chip a
  direita foi classificada como pista intencional de rolagem, nao como overflow
  global.
- Checkout, pagamento PIX pendente, PIX expirado e tracking abriram no estado
  seed correto.
- Superficies operacionais KDS, POS, fila de pedidos, pedido iFood atrasado,
  pedido cancelado e fechamento abriram com contexto operacional visivel.

## Limites da Evidência

Esta rodada e evidencia local forte e repetivel, mas ainda nao e gate
automatizado de CI. Ela tambem nao substitui teste em dispositivo fisico com
toque real, teclado virtual, rede degradada e credenciais sandbox/staging dos
gateways.

Para release com trafego real, mantenha como pendentes:

- executar a mesma matriz em staging com PostgreSQL, Redis e assets finais;
- validar pelo menos um aparelho mobile fisico e um tablet de cozinha;
- decidir se Playwright/Chrome deve virar gate formal antes do piloto publico.
