# Omotenashi fullness audit - WP-OF-0

Data: 2026-05-02

Escopo: Storefront, Backstage, KDS, tracking, pagamento, conta, historico,
access link, Admin de copy e testes existentes.

Metodo: auditoria estatica de templates, projections, services, docs e testes
automatizados existentes. Este WP nao substitui o teste manual em browser nem
os roteiros praticos com seed; ele congela o ponto de partida e diz onde a
implementacao precisa ser endurecida.

Nota pos-auditoria: o primeiro achado de WP-OF-1 foi corrigido logo apos este
baseline. `shopman.shop.omotenashi.context` passou a ser a implementacao
canonica do `OmotenashiContext`, e o pacote duplicado
`shopman.storefront.omotenashi` foi removido.

Nota pos-auditoria 2: `PaymentProjection` e `PaymentStatusProjection` passaram
a carregar `PaymentPromiseProjection`; a tela de pagamento agora renderiza
estado atual, acao do cliente, prazo, proximo evento, recovery e aviso ativo.
Tambem foi criado contrato de notificacao ativa em `notification.send`, com
dedupe por pedido/evento, filtro por canal habilitado quando ha `customer_ref`,
rota transacional para origem WhatsApp e falha visivel para evento critico sem
canal entregavel. Os E2E de lifecycle foram realinhados para o fluxo real
availability-first com pagamento `post_commit`.

Referencias:

- `docs/omotenashi.md`
- `docs/reference/omotenashi-audit-framework.md`
- `docs/plans/OMOTENASHI-FIRST-FULLNESS-PLAN.md`
- `docs/plans/PROJECTION-UI-PLAN.md`

## Veredito executivo

O Shopman ja tem uma fundacao real de Omotenashi: contexto temporal/pessoal,
copy editavel, projections tipadas, tracking com promessa operacional, order
queue por zonas, KDS com timers e varias suites de teste.

Mas ainda nao esta em plenitude Omotenashi-first. A lacuna principal nao e copy:
e contrato de promessa. Tracking esta mais perto do modelo correto, mas Payment,
Checkout, Backstage e KDS ainda nao sao guiados pelo mesmo tipo de contrato
explicito de estado atual, acao, prazo, proximo evento, recuperacao e
notificacao ativa.

Conclusao pratica:

- Kernel/lifecycle: forte.
- Projections: direcao correta.
- Storefront antes do checkout: parcialmente contextual, ainda pouco ativo.
- Payment: bloqueante para plenitude.
- Tracking: bom, mas depende de notificacao ativa que ainda nao esta governada.
- Backstage/KDS: operacionalmente util, mas ainda nao prova contrato 1:1 com a
  promessa mostrada ao cliente.
- Testes: bons em varios pontos, mas fragmentados. Ainda falta matriz E2E de
  mundo real por persona/cenario.

## ReadModel vs Projection

Nao ha motivo para manter dois conceitos concorrentes.

O codigo consolidou o padrao como `*Projection`:

- `CatalogProjection`
- `CartProjection`
- `CheckoutProjection`
- `PaymentProjection`
- `PaymentStatusProjection`
- `OrderTrackingProjection`
- `OrderTrackingPromiseProjection`
- `OrderTrackingStatusProjection`
- `OrderQueueProjection`
- `TwoZoneQueueProjection`
- `KDSBoardProjection`
- `CustomerProfileProjection`
- `OrderHistoryProjection`

Os docs antigos usam "read model" como termo conceitual de CQRS leve, nao como
uma segunda camada. A regra daqui para frente deve ser:

- Nome publico/codigo: `Projection`.
- Descricao tecnica: "projection/read model" apenas quando explicando conceito.
- Nenhuma classe nova chamada `ReadModel`.
- Nenhuma segunda fonte de leitura paralela a uma projection.

Achado relevante no baseline: existiam dois `OmotenashiContext`.

- `shopman/storefront/omotenashi/context.py` calculava historico e
  `favorite_category`.
- `shopman/shop/omotenashi/context.py` ainda deixa `favorite_category` como
  `None`.

Isso era risco real de divergencia. Foi corrigido sem facade: a versao completa
foi movida para `shopman.shop.omotenashi.context`, e os consumidores devem
importar diretamente de `shopman.shop.omotenashi`.

## Pontuacao por superficie

Escala: A Contexto Macro / B Contexto Individual / C Antecipacao /
D Recuperacao / E Elegancia.

| Superficie | A | B | C | D | E | Total | Classe |
|---|---:|---:|---:|---:|---:|---:|---|
| Home | 11 | 12 | 15 | 10 | 15 | 63 | ALERTA |
| Menu/catalogo | 9 | 9 | 13 | 9 | 15 | 55 | ALERTA |
| Product detail | 8 | 6 | 13 | 9 | 16 | 52 | ALERTA |
| Cart drawer/page | 9 | 8 | 17 | 14 | 15 | 63 | ALERTA |
| Checkout | 8 | 13 | 16 | 11 | 15 | 63 | ALERTA |
| Payment Pix/card | 7 | 5 | 12 | 14 | 11 | 49 | BLOQUEADO |
| Order confirmation | 7 | 9 | 13 | 12 | 15 | 56 | ALERTA |
| Tracking | 11 | 9 | 20 | 16 | 17 | 73 | BOM |
| Account | 7 | 14 | 12 | 10 | 15 | 58 | ALERTA |
| Order history/reorder | 7 | 13 | 14 | 10 | 14 | 58 | ALERTA |
| Login/access link | 8 | 12 | 15 | 13 | 14 | 62 | ALERTA |
| Backstage order queue | 8 | 7 | 15 | 14 | 16 | 60 | ALERTA |
| Backstage order detail | 7 | 6 | 13 | 12 | 14 | 52 | ALERTA |
| KDS preparo/picking | 7 | 5 | 14 | 11 | 15 | 52 | ALERTA |
| KDS expedicao | 7 | 5 | 13 | 11 | 15 | 51 | ALERTA |
| Admin OmotenashiCopy | 6 | 8 | 12 | 12 | 15 | 53 | ALERTA |

Observacao: "BOM" no Tracking nao significa pronto para producao plena. Significa
que a superficie ja tem contrato de promessa mais maduro que as demais. Ela
ainda depende de notificacao ativa, seed e testes E2E para ficar excelente.

## Evidencias por superficie

### Home

Evidencias positivas:

- Usa `MENU_SUBTITLE`, `BIRTHDAY_HERO_*`, `closing_awareness`,
  `quick_reorder`, banner de origem WhatsApp e preview de disponibilidade.
- `HomeView._reorder_context` usa `last_reorder_context` com `REORDER_MIN_DAYS = 0`.
- Teste protege fechamento de overlays antes de HTMX no reorder.

Gaps:

- Contexto de almoco/fechando ainda muda mais copy/section do que decisao de
  fluxo.
- Hero e "como funciona" ainda podem prometer pagamento/confirmacao rapida de
  forma generica, sem explicar a verificacao de disponibilidade.
- Nao ha contrato unico de "melhores escolhas para agora".

Prioridade: P1 para ranking contextual real.

### Menu/catalogo

Evidencias positivas:

- `CatalogProjection` recebe `favorite_category_ref`.
- Dynamic sections entram antes das static sections.
- Categoria favorita aparece visualmente no pill.

Gaps:

- Categoria favorita nao reordena suficientemente o cardapio.
- Busca vazia ainda nao conduz para semelhantes/substitutos.
- Indisponivel nao vira protocolo de recuperacao.
- Contexto de almoco nao governa ranking de forma obrigatoria.

Prioridade: P1.

### Product detail

Evidencias positivas:

- `ProductDetailProjection` tem disponibilidade, quantidade maxima, alergeno,
  conservacao, ingredientes e nutricao.
- Template avisa mudanca de estoque e bloqueia add quando indisponivel.
- Existe decisao documentada no proprio template: PDP nao lista substitutos.

Gaps:

- Para Omotenashi pleno, indisponivel nao pode ser fim de linha. Precisa "ver
  semelhantes", "avisar quando voltar" ou substituto baseado nos mecanismos de
  disponibilidade ja existentes.
- Restricoes/alergenos estao bem expostas, mas ainda nao cruzam com preferencia
  conhecida do cliente para alerta proativo.

Prioridade: P1.

### Cart

Evidencias positivas:

- `CartProjection` concentra minimo, indisponiveis, itens aguardando
  confirmacao, upsell e contexto de quantidade.
- Drawer/page mostram minimo, bloqueios, undo e dismiss.
- Reorder pode avisar skips.

Gaps:

- Upsell ainda e generico e tem label `Add` em ingles.
- Quando item fica indisponivel, falta alternativa direta.
- Pontos, minimo, indisponivel e loja fechando ainda nao compoem um contrato
  de "o que falta resolver antes de enviar".

Prioridade: P2/P1, dependendo do fluxo de estoque.

### Checkout

Evidencias positivas:

- `CheckoutProjection` agrega carrinho, contato, enderecos, metodo de pagamento,
  slots, fidelidade e configuracoes da loja.
- Template tem `coerceStep`, `canAdvance`, pickup sem address step, modal de
  troca de conta e CTA "Enviar pedido".
- Testes cobrem alguns guardrails de UI.

Gaps:

- Falta promessa explicita do fluxo decidido: "enviaremos para o
  estabelecimento conferir disponibilidade; depois o pagamento segue conforme o
  metodo".
- Payment step ainda mostra metodo como formulario, nao como consequencia
  operacional.
- Falta contrato de origem WhatsApp/access link na projection.
- Validacoes/copies de step ainda aparecem parcialmente hardcoded.

Prioridade: P1.

### Payment Pix/card

Evidencias positivas:

- `PaymentProjection` centraliza metodo, valor, QR/copia-e-cola, expiry,
  checkout URL e status URL.
- `PaymentStatusProjection` trata paid, expired, cancelled e redirect.
- Pix tem countdown ancorado em `server_now_iso`.
- Dev mock confirm e POST-only.

Gaps bloqueantes:

- `PaymentProjection` nao tem promessa operacional completa: acao, prazo,
  proximo evento, recovery, notificacao ativa, estado stale.
- Quando QR/copia-e-cola nao existe, o placeholder pode parecer uma tela pronta,
  mas sem acao real.
- Card sem `checkout_url` usa copy seca "atualize em instantes", sem recovery
  operacional.
- O status pago via HTMX redireciona direto; isso pode ser correto, mas precisa
  ser contrato explicito e testado como yoin/transicao, nao comportamento
  acidental.
- Falha de intent precisa retry idempotente e alerta operacional com UX clara.

Prioridade: P0.

### Order confirmation

Evidencias positivas:

- Existe superficie de confirmacao e tests de tracking/reorder relacionados.
- Fluxo ja redireciona para tracking/pagamento conforme estado.

Gaps:

- Confirmacao ainda precisa ficar alinhada com o fluxo availability-first:
  pedido recebido nao e pedido garantido; pagamento Pix so deve ser acionado
  depois da disponibilidade.
- Falta protocolo de notificacao ativa: o cliente precisa saber que sera avisado
  quando houver acao dele.

Prioridade: P1.

### Tracking

Evidencias positivas:

- `OrderTrackingPromiseProjection` ja expoe `state`, `title`, `message`,
  `deadline_at`, `deadline_kind`, `deadline_action`,
  `requires_active_notification`, `customer_action`, `next_event`, `recovery`,
  `active_notification`.
- Tracking usa SSE + polling + countdown-expired.
- Mostra "Atualizado agora" e stale depois de 45s.
- Pickup info so aparece para pickup.
- Testes cobrem Pix pendente/expirado, payment gate, tracking status partial,
  copy superada, ready delivery/pickup e timestamps.

Gaps:

- `active_notification` ainda e promessa visual; precisa ser comprovado pelo
  servico de notificacao com preferencias/consentimento.
- A tabela status x payment x fulfillment x deadline precisa virar contrato
  versionado e testado como matriz.
- Stale/offline esta visivel, mas recovery ainda e passivo.

Prioridade: P1 para notificacao ativa e matriz E2E.

### Account

Evidencias positivas:

- `CustomerProfileProjection` inclui fidelidade, enderecos, pedidos recentes,
  preferencias de notificacao e preferencias alimentares.
- Services de account exportam dados e respeitam customer ref.

Gaps:

- Historico, fidelidade e reorder precisam de cenario seedado que prove que a
  mesma identidade mostra dados consistentes em todos os pontos.
- Preferencias de notificacao existem na conta, mas ainda nao estao provadas
  como policy obrigatoria no envio de eventos criticos de pedido.
- Novo acesso/dispositivos esta anotado no produto, mas precisa protocolo
  proprio de seguranca e conta.

Prioridade: P1/P2.

### Order history/reorder

Evidencias positivas:

- `customer_orders.history_summaries_for_customer` unifica `customer_ref` e
  `phone`, reduzindo contradicao entre loja, conta e pedidos.
- Home reorder usa `last_reorder_context`.
- Tests cobrem quick reorder e skips.

Gaps:

- A experiencia precisa garantir que fidelidade que referencia pedido e
  historico de pedidos nunca divergem.
- Reorder deve explicar de forma objetiva o que entrou, o que nao entrou e por
  que.

Prioridade: P2, com seed obrigatorio.

### Login/access link

Evidencias positivas:

- Access link com `next` existe e os testes protegem URL segura.
- ManyChat/WhatsApp ja geram URLs de tracking/reorder quando ha UUID.
- Auth intents sanitizam `next`.

Gaps:

- Padrao `next` deve ser o unico, sem `entry_url` paralelo em novos fluxos.
- Access link precisa aceitar payload manychat/phone/name de forma canonica
  quando essa for a entrada operacional, sem exigir que o operador saiba UUID.
- UX de origem WhatsApp deve guiar a intencao: menu, checkout, tracking ou
  reorder.

Prioridade: P1.

### Backstage order queue

Evidencias positivas:

- `TwoZoneQueueProjection` separa Entrada, Preparo e Saida.
- Cards mostram pagamento pendente e bloqueiam confirmar enquanto pagamento
  digital nao estiver completo.
- SSE/HTMX atualiza a lista e ha preservacao de scroll por `data-preserve-scroll`.
- Timer do card usa `server_now_iso`.
- Testes cobrem confirm/reject/advance, gate de pagamento e ausencia de mark
  paid no card.

Gaps:

- "Pagamento pendente" ainda e badge dentro da Entrada/Confirmed, nao uma zona
  operacional clara. Isso favorece a sensacao de limbo.
- Se o operador precisa agir em disponibilidade, a fila deve separar "conferir
  disponibilidade" de "aguardando pagamento" de forma inequivoca.
- A preservacao de scroll existe, mas precisa teste de UI/DOM que prove que
  novo pedido nao faz a tela pular durante interacao.
- Mark paid, quando existir para admin, precisa caminho raro, contextual,
  auditavel e fora da tarefa primaria.

Prioridade: P1.

### Backstage order detail

Evidencias positivas:

- Detail projection inclui timeline, itens, payment status, fulfillment e notas.

Gaps:

- Ainda falta painel de contexto operacional antes da acao: prazo restante de
  disponibilidade, risco de estoque, itens com substituicao possivel, alergias,
  restricoes e impacto no cliente.
- Ajuste de pedido dentro de guardrails ainda nao aparece como caminho operador
  completo.

Prioridade: P1.

### KDS preparo/picking

Evidencias positivas:

- KDS tem `KDSBoardProjection`, tickets por estacao, timers, alerta de atraso,
  som e offline banner.
- `complete_ticket` marca todos os itens e move o pedido para `ready` quando
  todos os tickets terminam.
- Se pedido esta `confirmed`, o KDS garante `preparing` antes de `ready`, desde
  que pagamento permita trabalho fisico.

Gaps:

- Botao "Pronto" marca todos os itens sem pedir item-by-item; isso e eficiente,
  mas precisa copy/confirmacao/guardrail quando o risco for alto.
- KDS nao mostra a promessa do cliente associada ao ticket: cliente esta
  aguardando preparo, retirada, entregador?
- Contrato KDS -> tracking precisa ser testado contra todos os estados.

Prioridade: P1.

### KDS expedicao

Evidencias positivas:

- Expedition usa pedidos `ready`.
- Delivery tem "Despachar"; pickup tem "Entregar".
- Core impede completar delivery direto de `ready`.

Gaps:

- Copy operacional deveria refletir exatamente a promessa cliente:
  "aguardando entregador" antes de "saiu para entrega".
- "Entregar" para pickup pode significar "retirado pelo cliente"; label deve
  ser mais preciso.
- Falha de action retorna "Acao invalida" seca; precisa recovery.

Prioridade: P1/P2.

### Admin OmotenashiCopy

Evidencias positivas:

- Copy tem defaults em codigo e override por Admin.
- Admin mostra uso e historico basico.

Gaps:

- Admin nao deve permitir que copy mude semantica operacional. Prazos/status
  devem vir de dominio/projection, nao texto livre.
- Falta mapa "onde esta chave aparece", preview por moment/audience e risco de
  copy vazia.
- Seed deve conter copies realistas por fluxo, nao atalhos que induzem teste
  falso.

Prioridade: P1.

## Findings priorizados

### P0 - Bloqueantes

F-001 - Payment nao tem contrato de promessa completo. Resolvido apos baseline.

Impacto: cliente pode cair numa tela seca, sem saber exatamente prazo, acao,
proximo evento ou recovery. Isso e critico para Pix.

Solucao aplicada: `PaymentProjection`/`PaymentStatusProjection` agora expõem
`PaymentPromiseProjection` com `state`, `customer_action`, `deadline_at`,
`deadline_kind`, `next_event`, `recovery`, `active_notification` e
`stale_after_seconds`.

F-002 - Notificacao ativa ainda nao e governada por matriz obrigatoria.
Parcialmente resolvido apos baseline.

Impacto: eventos criticos podem depender de refresh/tracking passivo. Para Pix,
pedido pronto, atraso e cancelamento isso e operacionalmente inseguro.

Solucao aplicada ate aqui: `notification.send` marca eventos criticos, deduplica
pedido/evento, respeita canais habilitados quando ha `customer_ref`, permite
WhatsApp transacional para pedidos originados do WhatsApp e falha visivelmente
quando evento critico nao tem canal/recipiente. Ainda falta push real e
observabilidade completa de preferencias por canal na UI operacional.

F-003 - Contrato Backstage/KDS/Storefront ainda nao esta provado E2E.

Impacto: operador pode ver "a coletar" enquanto cliente ve "saiu para entrega",
ou KDS pode mudar pedido sem tracking refletir a promessa correta.

Solucao: testes de contrato por status: confirmed unpaid, confirmed paid,
preparing, ready pickup, ready delivery aguardando entregador, dispatched,
delivered, completed, cancelled.

F-004 - Testes praticos ainda nao cobrem a matriz de mundo real.
Parcialmente resolvido apos baseline.

Impacto: testes unitarios/projection passam, mas fluxos podem continuar
quebrando no caminho real do cliente/operador.

Solucao aplicada ate aqui: os E2E de lifecycle agora cobrem o fluxo real
availability-first/post_commit para Web/WhatsApp. Ainda falta browser/HTMX com
usuario real para ajuste operador, pedido rejeitado, stale/offline e expedicao.

### P1 - Graves

F-005 - Dois `OmotenashiContext` divergentes. Resolvido apos baseline.

Impacto: contexto favorito pode existir numa superficie e nao em outra,
gerando falsa sensacao de implementacao plena.

Solucao aplicada: uma unica implementacao canonica em
`shopman.shop.omotenashi.context`. Sem compatibilidade com copia stale.

F-006 - Contexto de almoco/favoritos ainda nao governa ranking suficiente.

Impacto: o sistema sabe contexto, mas nao age consistentemente sobre ele.

Solucao: ranking flags na `CatalogProjection`: `rank_reason`, `is_contextual`,
`is_recent_or_favorite`, `is_good_for_now`.

F-007 - PDP indisponivel nao tem recuperacao omotenashi.

Impacto: cliente encontra dead-end quando o item nao pode ser comprado.

Solucao: integrar substitutos/semelhantes/notify-me usando disponibilidade
existente, sem criar nova fonte de verdade.

F-008 - Checkout nao explicita a promessa availability-first.

Impacto: cliente nao entende por que enviou pedido, mas ainda nao pagou, ou por
que Pix aparece depois.

Solucao: `CheckoutProjection` deve expor um `submit_promise`: estado, frase
curta, acao do estabelecimento, metodo de pagamento e notificacao esperada.

F-009 - Backstage nao separa suficientemente disponibilidade e pagamento.

Impacto: pedidos confirmados pela loja e aguardando pagamento podem parecer
sumidos ou em limbo.

Solucao: nova zona/projection operacional para `aguardando_pagamento` ou
subzona explicita, derivada de order status + payment status.

F-010 - KDS "Pronto" e eficiente, mas precisa guardrail contextual.

Impacto: operador pode concluir ticket sem revisar item em caso de risco.

Solucao: manter atalho, mas mostrar estado "todos os itens serao marcados como
prontos" ou exigir confirmacao quando houver observacao, alergeno, estoque
baixo ou item substituido.

F-011 - Admin de copy ainda nao protege semantica.

Impacto: copy editavel pode quebrar promessa se operador alterar texto critico.

Solucao: separar copy decorativa/editavel de labels contratuais vindas de
projection. Admin deve mostrar uso, preview e fallback.

### P2 - Moderados

F-012 - Cart upsell tem label em ingles e sugestao generica.

Solucao: projection deve expor razao de sugestao e label pt-BR.

F-013 - Account/history/loyalty precisam seed de identidade consistente.

Solucao: criar cliente seed com pedidos, pontos e historico validado em conta,
home, historico e checkout.

F-014 - Payment/card fallback esta seco.

Solucao: erro com CTA, retry idempotente e suporte/WhatsApp quando apropriado.

F-015 - Stale tracking e passivo.

Solucao: se stale persistir, mostrar recovery e acionar alerta/evento.

F-016 - `entry_url` deve sair dos novos fluxos.

Solucao: padronizar `next` para redirecionamento seguro.

## Timers e deadlines

Regra correta:

- Timer e sempre consequencia de um deadline server-side.
- O browser apenas renderiza a contagem usando `server_now_iso`.
- Storefront, Backstage e KDS nao podem inventar timers independentes para a
  mesma promessa.

Estado atual:

- Tracking ja se aproxima do correto com `deadline_at` e `stale_after_seconds`.
- Pix usa `pix_expires_at` e `server_now_iso`.
- Backstage card usa elapsed desde `created_at` e `server_now_iso`.
- KDS usa elapsed do ticket e alvo da estacao.

Gap:

- Esses timers pertencem a promessas diferentes, mas isso nao esta declarado em
  contrato unico. O usuario viu diferenca entre storefront e backstage porque o
  sistema ainda nao tem uma matriz de deadline por estado/papel.

Solucao:

- Criar tabela de deadline por promessa:
  - disponibilidade: pedido `new`, deadline de confirmacao manual.
  - pagamento Pix: pedido `confirmed`, payment intent pendente, deadline do Pix.
  - preparo: pedido `preparing`, baseline `preparing_at`.
  - entrega/coleta: pedido `ready` delivery/pickup, baseline `ready_at`.
  - stale: ultima atualizacao de tracking/SSE.

## Availability decision

Nao criar `availability_decision`.

O operador nao precisa de entidade nova. A decisao operacional deve continuar
como transicao de status do pedido dentro de guardrails:

- `new` -> confirmado/rejeitado/ajustado.
- pagamento digital separado em Payman/status de pagamento.
- disponibilidade/estoque consultados pelos mecanismos existentes.
- ajustes/substituicoes como comandos auditaveis sobre o pedido, nao nova fonte
  de verdade.

## Seed e testes de realidade

Cenarios minimos de seed/teste que devem existir:

1. Cliente anonimo em home/menu sem pedidos.
2. Cliente recorrente com ultimo pedido e categoria favorita.
3. Cliente com pontos e historico coerente.
4. Cliente vindo de ManyChat com `phone`, `first_name`, `last_name`,
   `manychat_id` e `next`.
5. Pedido pickup Pix: disponibilidade pendente, confirmada, Pix pendente,
   Pix expirado, Pix pago.
6. Pedido delivery Pix: ready aguardando entregador, dispatched, delivered,
   completed.
7. Pedido card: autorizado antes, captura apos disponibilidade, sem acao do
   cliente.
8. Produto indisponivel no PDP/cart.
9. Checkout pickup editando endereco nao deve quebrar fluxo.
10. Pedido rejeitado pelo estabelecimento.
11. Falha ao gerar pagamento.
12. Tracking stale/offline.
13. KDS com dois tickets; pedido so fica pronto quando todos concluem.
14. Operador tenta acao bloqueada e recebe motivo claro.

Cada cenario precisa de:

- seed ou factory legivel.
- teste projection.
- teste web/HTMX.
- roteiro manual curto.

## Proximo caminho recomendado

Sequencia pragmatica:

1. WP-OF-1: canonicalizar contexto e contrato de signals.
   - Duplicidade de `OmotenashiContext`: resolvida apos baseline.
   - Documentar sinais canonicos e suas decisoes de fluxo.
   - Padronizar `next` para access links.

2. WP-OF-5: Payment/Tracking promise contract.
   - Elevar `PaymentProjection` ao mesmo nivel semantico do tracking.
   - Garantir Pix QR/copia-e-cola/mock/dev sem comportamento magico.
   - Testes de payment gate, timeout, retry e redirect.

3. WP-OF-7: Backstage/KDS contrato operacional.
   - Separar fila por disponibilidade/pagamento/preparo/saida.
   - Contrato 1:1 KDS -> tracking.
   - Teste de scroll/refresh e SSE.

4. WP-OF-6: notificacao ativa.
   - Matriz evento/canal/consentimento.
   - Idempotencia por evento/ref.
   - Alerta operacional quando envio falhar.

5. WP-OF-3/WP-OF-4: Storefront antes do checkout e checkout guiado.
   - Ranking contextual.
   - PDP substitutos.
   - Checkout promise availability-first.

6. WP-OF-9/WP-OF-11: Admin copy, seed e teste de realidade.
   - Admin com preview/uso/fallback.
   - Seed sem atalhos falsos.
   - Browser E2E dos fluxos praticos.

## Criterio de aceite para sair de ALERTA

Uma superficie so sobe para BOM/EXCELENTE quando:

- Seu estado atual e derivado de projection.
- A projection expoe acao, prazo, next_event e recovery quando houver promessa.
- O template nao recomputa semantica.
- Evento critico tem notificacao ativa governada.
- Existe teste do fluxo real, nao apenas service isolado.
- Seed reproduz o mesmo caminho que producao usara.
