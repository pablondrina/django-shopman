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

Para o gate local/CI completo, sem depender de servidor já aberto:

```bash
make omotenashi-browser-ci
```

No cutover headless, a superfície de cliente deixou de ser o Django e passou a ser
a loja Nuxt (`surfaces/storefront-uithing-nuxt`). Este alvo reflete a topologia
real: compila CSS, aplica migrations, recria o seed, **builda e sobe a loja Nuxt**
(`127.0.0.1:3100`) apontando o BFF para a API Django, sobe o **Django** (API +
páginas de operador) em `127.0.0.1:8001` com `SHOPMAN_STOREFRONT_BASE_URL`
apontando para a loja, navega a matriz Omotenashi em modo estrito e encerra apenas
os processos que ele iniciou. Use `port=...`/`nuxt_port=...` para trocar as portas.

A matriz mistura dois tipos de checkpoint, e o runner resolve cada um para a base
certa automaticamente:

- **Cliente** → URLs absolutas da loja Nuxt (via `storefront_links`).
- **Operador** (admin/KDS/produção/fechamento) → caminhos relativos do Django.

A sessão de QA é um cookie de superusuário gravado em **todas as origens** que a
matriz navega (Django + loja Nuxt). O BFF da loja repassa esse cookie ao Django,
onde o superusuário libera o acesso a pedidos — assim os checkpoints de
pagamento/acompanhamento renderizam o estado real, não o fallback de "não
encontrado".

O **POS** migrou para o seu próprio app Nuxt (`surfaces/pos-uithing-nuxt`), que
este gate não sobe: os checkpoints de POS são **pulados com aviso explícito** (não
silenciosamente, nem como falso verde) até `SHOPMAN_POS_BASE_URL` apontar para a
superfície. Essa cobertura entra na revisão do PDV (fase C).

## Matriz Canônica

| Cenário | Viewport | Superfície | O que abrir | Foco da validação |
|---------|----------|------------|-------------|-------------------|
| `mobile.catalog.browse` | mobile 375x812 | Storefront (Nuxt) | `/menu` | Exploração, PDP, disponibilidade e próxima ação sem dead end. |
| `mobile.checkout.intent` | mobile 375x812 | Storefront (Nuxt) | `/checkout` | Etapa atual, bloqueio claro, recuperação e CTA único. *Checkout gateia por login (`auth_gated`): cair na entrada é o guardrail esperado.* |
| `mobile.payment.pix_pending_near_expiry` | mobile 375x812 | Storefront (Nuxt) | `/pedido/<ref>/pagamento` | PIX pendente com prazo, ação do cliente e sem confirmação por refresh. |
| `mobile.payment.pix_expired` | mobile 375x812 | Storefront (Nuxt) | `/pedido/<ref>/pagamento` | Expiração com recuperação segura e contexto preservado. |
| `mobile.tracking.ready` | mobile 375x812 | Storefront (Nuxt) | `/tracking/<ref>` | Estado atual, ação do cliente e próximo evento. |
| `tablet.kds.station` | tablet 1024x768 | KDS (Django) | estação KDS seed | Toque, foco, tempo, som/fallback e ausência de ruído. |
| `tablet.kds.customer_board` | display 1280x720 | KDS cliente (Django) | painel de retirada | Só informação necessária, sem dado sensível. |
| `tablet.production.kds` | tablet 1024x768 | Produção (Django) | KDS de produção | Lote, passo, ação primária e falta de insumo. |
| `desktop.orders.queue` | desktop 1440x900 | Backstage (Django) | fila de pedidos | Urgência, bloqueios, pagamento e ação primária. |
| `desktop.marketplace.ifood_stale` | desktop 1440x900 | Backstage (Django) | pedido iFood seed | Pedido externo atrasado com ação segura. |
| `desktop.payment.after_cancel` | desktop 1440x900 | Backstage (Django) | pedido cancelado seed | Alerta crítico, reembolso e comunicação. |
| `desktop.pos.counter` | touch/desktop 1280x800 | POS (Nuxt próprio) | superfície POS | Venda, edição, comanda disponível e caixa aberto. *Pulado até `SHOPMAN_POS_BASE_URL` (fase C).* |
| `desktop.cash_register.shift` | touch/desktop 1280x800 | POS (Nuxt próprio) | superfície POS | Estado de caixa, sangria/fechamento e diferença. *Pulado até `SHOPMAN_POS_BASE_URL` (fase C).* |
| `desktop.closing.day` | desktop 1440x900 | Backstage (Django) | fechamento do dia | Sobras, D-1, caixa e divergências sem planilha paralela. |

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

## CI

O gate roda no workflow dedicado **`.github/workflows/omotenashi-gate.yml`**
("Omotenashi Gate") a cada PR e push para `main`: sobe Postgres, instala deps
Python + Node, instala Chrome, e executa `make omotenashi-browser-ci` (seed +
build/serve da loja Nuxt + Django + QA browser estrita). Screenshots, relatório
JSON e logs dos servidores sobem como artifact `omotenashi-browser-qa`.

> Histórico: no cutover headless, o gate antigo (que navegava as páginas Django de
> cliente, aposentadas) saiu do `Runtime Gate`. Este workflow o reconstrói para a
> superfície real — loja Nuxt (cliente) + Django (operador).

## Evidência Atual

Rodada browser local (2026-06-17, pós-headless) via `make omotenashi-browser-ci`:
**12 pass, 0 review, 2 skipped** em Chrome headless. Os 12 cobrem a loja Nuxt
(menu, checkout com gate de login, PIX pendente/expirado, tracking pronto — todos
no estado real autenticado) e o operador Django (KDS estação/cliente, produção,
fila de pedidos, iFood parado, pagamento pós-cancelamento, fechamento). Os 2
skipped são os checkpoints de POS, cuja superfície Nuxt própria este gate ainda
não sobe (entra na revisão do PDV, fase C).

A rodada anterior pré-headless está em
[`docs/reports/omotenashi-browser-qa-2026-05-05.md`](../reports/omotenashi-browser-qa-2026-05-05.md)
(navegava as páginas Django, hoje aposentadas).

Essa evidência valida navegação/renderização local+CI da matriz seed; não
substitui dispositivo físico.
