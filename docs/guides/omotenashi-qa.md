# QA Manual Omotenashi E2E

Este roteiro transforma a rodada manual mobile/tablet/desktop em contrato
executável. Ele não substitui testes automatizados; cobre toque, foco, leitura,
latência percebida, estado vazio/erro e clareza operacional.

## Preparação

Use sempre o seed canônico, porque a matriz depende de cenários determinísticos:

```bash
make seed
make omotenashi-qa strict=1
```

Para gerar evidência auditável:

```bash
make omotenashi-qa json=1
```

Se o comando falhar em modo `strict=1`, a rodada manual não está pronta. Corrija
o seed ou a matriz; não ajuste o roteiro para caber no dado disponível.

Para navegar a matriz em Chrome headless local, com screenshots e relatório
JSON:

```bash
make run
make omotenashi-browser-qa strict=1
```

O target espera um servidor Shopman já rodando em `http://127.0.0.1:8000`,
gera uma sessão admin local automaticamente e grava:

- screenshots em `/tmp/shopman-omotenashi-qa-screens`;
- relatório JSON em `/tmp/shopman-omotenashi-qa-browser.json`.

Use `base_url=...`, `screenshots=...`, `report=...` ou `matrix=...` quando
precisar apontar para outro ambiente ou anexar artefatos específicos.

## Matriz Canônica

| Cenário | Viewport | Superfície | O que abrir | Foco da validação |
|---------|----------|------------|-------------|-------------------|
| `mobile.catalog.browse` | mobile 375x812 | Storefront | `/menu/` | Exploração, PDP, disponibilidade e próxima ação sem dead end. |
| `mobile.checkout.intent` | mobile 375x812 | Storefront | `/checkout/` | Etapa atual, bloqueio claro, recuperação e CTA único. |
| `mobile.payment.pix_pending_near_expiry` | mobile 375x812 | Storefront | URL do pedido seed | PIX pendente com prazo, ação do cliente e sem confirmação por refresh. |
| `mobile.payment.pix_expired` | mobile 375x812 | Storefront | URL do pedido seed | Expiração com recuperação segura e contexto preservado. |
| `mobile.tracking.ready` | mobile 375x812 | Storefront | URL de tracking seed | Estado atual, ação do cliente e próximo evento. |
| `tablet.kds.station` | tablet 1024x768 | KDS | estação KDS seed | Toque, foco, tempo, som/fallback e ausência de ruído. |
| `tablet.kds.customer_board` | display 1280x720 | KDS cliente | painel de retirada | Só informação necessária, sem dado sensível. |
| `tablet.production.kds` | tablet 1024x768 | Produção | KDS de produção | Lote, passo, ação primária e falta de insumo. |
| `desktop.orders.queue` | desktop 1440x900 | Backstage | fila de pedidos | Urgência, bloqueios, pagamento e ação primária. |
| `desktop.marketplace.ifood_stale` | desktop 1440x900 | Backstage | pedido iFood seed | Pedido externo atrasado com ação segura. |
| `desktop.payment.after_cancel` | desktop 1440x900 | Backstage | pedido cancelado seed | Alerta crítico, reembolso e comunicação. |
| `desktop.pos.counter` | touch/desktop 1280x800 | POS | `/gestor/pos/` | Venda, edição, comanda e caixa sem admin genérico. |
| `desktop.cash_register.shift` | touch/desktop 1280x800 | POS | `/gestor/pos/` | Estado de caixa, sangria/fechamento e diferença. |
| `desktop.closing.day` | desktop 1440x900 | Backstage | fechamento do dia | Sobras, D-1, caixa e divergências sem planilha paralela. |

## Critério de Aceite

- Nenhum texto, botão, badge ou card deve sobrepor outro elemento.
- A ação primária precisa ser óbvia sem ler documentação.
- Estado de erro deve dizer: o que aconteceu, o que significa, o que fazer agora
  e o que o sistema fará automaticamente.
- Mobile deve ser navegável com teclado virtual aberto.
- KDS/tablet deve funcionar com toque impreciso e baixa atenção.
- Backstage deve preservar contexto operacional antes de pedir decisão.
- Toda divergência financeira ou de webhook deve apontar para alerta/runbook.

Registre screenshots ou vídeo curto por cenário quando a rodada for usada como
evidência de release.

## Evidência Atual

A primeira rodada browser local foi registrada em
[`docs/reports/omotenashi-browser-qa-2026-05-05.md`](../reports/omotenashi-browser-qa-2026-05-05.md):
`14 pass`, `0 review`, `0 fail` em Chrome headless, cobrindo mobile, tablet,
display e desktop.

Essa evidência valida navegação/renderização local da matriz seed, mas ainda
não transforma QA visual em gate de CI nem substitui dispositivo físico.
