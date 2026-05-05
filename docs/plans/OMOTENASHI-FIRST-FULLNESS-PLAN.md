# OMOTENASHI-FIRST-FULLNESS-PLAN

Data: 2026-05-02

## Objetivo

Levar o Django Shopman de "Omotenashi como contexto e copy" para
"Omotenashi como protocolo operacional de fluxo".

O objetivo nao e deixar o sistema caloroso, fofo ou persuasivo. O objetivo e
fazer com que cada superficie conduza cliente e operador com elegancia pratica:
menos duvida, menos erro, menos ruido, mais seguranca de promessa.

Este plano complementa:

- [`docs/omotenashi.md`](../omotenashi.md)
- [`docs/reference/omotenashi-audit-framework.md`](../reference/omotenashi-audit-framework.md)
- [`docs/omotenashi-checklist.md`](../omotenashi-checklist.md)
- [`docs/plans/OMOTENASHI-PLAN.md`](OMOTENASHI-PLAN.md)
- [`docs/plans/PROJECTION-UI-PLAN.md`](PROJECTION-UI-PLAN.md)

## Principio central

Um sinal de contexto so esta implementado quando muda ao menos uma decisao de
fluxo, prioridade, CTA, bloqueio, recuperacao, recomendacao, notificacao,
promessa ou guardrail.

Se o sinal muda apenas uma frase, ele ainda e decoracao.

## Estado atual resumido

Ja existe uma fundacao real:

- `OmotenashiContext` calcula QUANDO e QUEM: momento do dia, saudacao, horario
  da loja, audiencia, nome, aniversario, ultimo pedido e categoria favorita.
- `resolve_copy()` e `OmotenashiCopy` permitem defaults e overrides via Admin.
- Varios templates consomem `{% omotenashi %}` e `omotenashi_ctx`.
- `CatalogProjection` ja recebe `favorite_category_ref`.
- `OrderTrackingProjection` ja introduziu um contrato de promessa operacional
  para tracking.

Mas ainda nao ha plenitude:

- Momento do dia ainda aparece mais como copy do que como ordenacao,
  disponibilidade guiada e decisao de fluxo.
- Personas e cenarios nao formam uma matriz obrigatoria de QA.
- Contexto externo e operacional ainda e parcial: canal, fila, carga da loja,
  risco de atraso, risco de estoque fantasma, origem WhatsApp, gateway,
  conectividade, SLA e preferencias de notificacao nao estao unificados como
  insumos de fluxo.
- Backstage ainda serve menos o operador do que deveria.
- Testes automatizados ainda precisam provar jornadas praticas, nao apenas
  services isolados.

## Execucao em 2026-05-02

Concluido nesta rodada:

- `OmotenashiContext` ficou com uma unica implementacao canonica em
  `shopman.shop.omotenashi.context`; o pacote `shopman.storefront.omotenashi`
  foi removido, sem facade/reexport.
- `PaymentProjection` e `PaymentStatusProjection` passaram a expor
  `PaymentPromiseProjection`.
- A tela de pagamento passou a renderizar promessa operacional: estado atual,
  acao, prazo, proximo evento, recovery e aviso ativo.
- `notification.send` passou a deduplicar por pedido/evento e a marcar eventos
  criticos de notificacao ativa.
- A entrega de notificacao agora respeita canais habilitados quando ha
  `customer_ref`; WhatsApp de origem segue como rota transacional do pedido; e
  evento critico sem canal/recipiente falha visivelmente em vez de virar
  silencio. Em `DEBUG`, `console` funciona como mock explicito.
- Falha ao gerar pagamento enfileira `payment_failed` alem do alerta
  operacional.
- Seed e E2E foram realinhados para o fluxo availability-first com pagamento
  `post_commit` e Pix com prazo de 10 minutos.

Verificacao desta rodada:

- Suíte critica integrada: `241 passed, 9 subtests passed`.

## Execucao em 2026-05-05

Concluido nesta rodada:

- Matriz manual QA Omotenashi virou comando executável: `make omotenashi-qa`.
- O comando aponta URLs, viewport, persona, expectativa e evidência seed para
  mobile cliente, tablet/KDS, produção, POS, fechamento e desktop gerente.
- O seed Nelson passou a ser validado contra a matriz canônica por teste; se o
  seed deixar de cobrir um cenário sensível, o teste falha.
- Roteiro manual documentado em
  [`docs/guides/omotenashi-qa.md`](../guides/omotenashi-qa.md).

Pendente:

- Executar a rodada visual/tátil em navegador/dispositivo e anexar evidências de
  release. O comando garante prontidão do seed; não substitui inspeção humana de
  toque, foco, layout e latência percebida.

## Nao objetivos

- Nao criar uma entidade `OmotenashiDecision`.
- Nao criar um "motor magico" central que decide tudo fora das projections.
- Nao transformar copy em marketing.
- Nao adicionar banners, upsells ou frases afetivas para mascarar fluxo ruim.
- Nao duplicar fontes de verdade de pedido, pagamento, estoque ou cliente.

## Arquitetura alvo

Omotenashi deve entrar como lente nos builders de projections e nos services de
orquestracao, nao como camada paralela.

Fluxo conceitual:

```text
Domain state + ChannelConfig + OmotenashiContext + Operational signals
  -> Projection builder / service
  -> Surface contract
  -> Template / HTMX partial / notification
```

Regras:

- `OmotenashiContext` continua sendo a fonte para contexto temporal e pessoal
  do request.
- Estado operacional vem das fontes existentes: order, payment, stock,
  fulfillment, directives, channel config, notification preferences.
- Cada projection deve expor campos de decisao, nao so textos.
- Templates nao podem recomputar semantica de prazo, prioridade ou status.
- HTMX continua para servidor; Alpine continua para DOM local.

## Contrato minimo por superficie

Toda superficie critica deve renderizar um contrato explicito:

```python
@dataclass(frozen=True)
class SurfacePromise:
    headline: str
    current_state: str
    customer_action: str          # none | choose | pay | wait | contact | retry
    primary_cta_label: str
    primary_cta_url: str | None
    deadline_at: str | None
    deadline_kind: str | None     # availability | payment | pickup | delivery | retry
    next_event: str
    recovery: str
    active_notification: str
    stale_after_seconds: int | None
```

Esse contrato nao precisa virar uma classe unica global. O nome e forma podem
variar por projection, mas os campos semanticos precisam existir onde houver
promessa operacional.

Exemplos:

- Tracking ja tem `OrderTrackingPromiseProjection`.
- Payment deve ter promessa propria de pagamento, com prazo, acao e recovery.
- Checkout deve ter promessa de envio de pedido, com etapas e guardrails.
- Backstage deve ter promessa de operacao: pedido novo, SLA, risco, acao
  primaria do operador.

## Matriz de contexto obrigatoria

Todo fluxo deve ser testado ao menos nas cinco lentes:

| Lente | Sinais minimos |
|---|---|
| QUEM | anon, novo, recorrente, VIP, aniversario, restricoes, historico |
| QUANDO | madrugada, manha, almoco, tarde, fechando, fechado, feriado |
| ONDE | web, WhatsApp access link, mobile browser, desktop, backstage, KDS |
| O QUE | explorar, repetir, comprar, pagar, acompanhar, retirar, cancelar, pedir ajuda |
| COMO | pressa, fome/espera, duvida, erro, atraso, friccao, recuperacao |

Um fluxo so e considerado completo quando seu contrato responde a essa matriz
sem dead ends.

## Work Packages

### WP-OF-0 - Baseline auditavel

Objetivo: congelar o ponto de partida antes de mexer.

Entregas:

- Criar relatorio `docs/reports/omotenashi-fullness-audit-YYYY-MM-DD.md`.
- Pontuar cada superficie usando `docs/reference/omotenashi-audit-framework.md`.
- Mapear cada tela em: contexto usado, decisao de fluxo, copy, recovery,
  notificacao ativa e testes existentes.
- Listar hardcoded strings que deveriam ser copy apenas quando forem texto
  configuravel, sem confundir labels tecnicas com copy operacional.

Superficies:

- Home
- Menu
- Product detail
- Cart drawer/page
- Checkout
- Payment Pix/card
- Order confirmation
- Tracking
- Account
- Order history
- Login/access link
- Backstage order queue
- Backstage order detail
- KDS/preparo
- KDS/expedicao
- Admin OmotenashiCopy

Aceite:

- Cada superficie tem nota A-E.
- Cada gap tem severidade P0/P1/P2/P3.
- Nenhum "parece bom" sem evidencia de fluxo ou teste.

### WP-OF-1 - Context contract real

Objetivo: ampliar o contexto sem criar nova fonte de verdade.

Entregas:

- Documentar quais sinais sao canônicos e de onde vem:
  - pessoa: `request.customer`, Guestman, loyalty, historico.
  - tempo: `OmotenashiContext`.
  - canal/origem: session, access link, channel ref, ManyChat metadata.
  - operacao: Shop/ChannelConfig, estoque, fila, directives, status.
  - pagamento: Payman intent/status, prazo, metodo, erros recuperaveis.
  - notificacao: preferencias, consentimento, canais disponiveis.
- Criar helper leve, sem persistencia, para expor origem/canal quando necessario
  aos builders de projection.
- Garantir que `OmotenashiContext` nao consulte dados caros em excesso por
  request; qualquer consulta historica deve ser cacheavel ou limitada.
- Definir budget de performance por request.

Aceite:

- Nao ha modelo novo.
- Nao ha duplicacao de status de pedido/pagamento/estoque.
- Cada sinal documentado tem uma decisao de fluxo associada.

### WP-OF-2 - Protocolos de intencao por jornada

Objetivo: sair de "telas" e modelar jornadas praticas.

Protocolos obrigatorios:

1. Cliente anonimo explorando cardapio.
2. Cliente recorrente repetindo pedido.
3. Cliente vindo do WhatsApp/ManyChat por access link.
4. Cliente em horario de almoco.
5. Cliente com loja fechando.
6. Cliente com loja fechada.
7. Cliente com item indisponivel ou estoque parcial.
8. Cliente finalizando checkout para retirada.
9. Cliente finalizando checkout para delivery.
10. Cliente Pix aguardando disponibilidade.
11. Cliente Pix apos disponibilidade confirmada.
12. Cliente Pix expirado.
13. Cliente cartao autorizado e aguardando captura.
14. Cliente acompanhando pedido ativo.
15. Cliente com pedido atrasado ou stale.
16. Cliente com pedido pronto para retirada.
17. Cliente delivery pronto aguardando entregador.
18. Cliente delivery saiu para entrega.
19. Cliente tentando cancelar fora da janela.
20. Operador recebendo pedido novo.
21. Operador confirmando disponibilidade.
22. Operador ajustando item dentro de guardrails.
23. KDS preparando itens.
24. Expedicao finalizando retirada/delivery.

Para cada protocolo:

- Contexto: QUEM, QUANDO, ONDE, O QUE, COMO.
- Estado inicial.
- Promessa atual.
- Acao do cliente.
- Acao do operador.
- Deadline.
- Notificacao ativa.
- Recuperacao.
- Teste E2E.

Aceite:

- Os protocolos estao em documento versionado.
- Cada protocolo tem ao menos um teste automatizado ou roteiro manual com seed.

### WP-OF-3 - Storefront antes do checkout

Objetivo: antecipacao real no momento de escolha.

Home:

- Se horario de almoco, priorizar uma area de "boas escolhas para agora" com
  produtos adequados, nao apenas subtitle.
- Se cliente recorrente, mostrar reorder sem bloquear cardapio.
- Se veio do WhatsApp, reconhecer origem e seguir para a intencao do link.
- Se loja fechando, mostrar prazo real antes do checkout.
- Se loja fechada, permitir explorar e, se aplicavel, encomendar para proximo
  horario sem prometer atendimento imediato.

Menu:

- Ordenar por relevancia: disponiveis, favoritos/recentes, momento do dia,
  categorias apropriadas, depois demais.
- Nao esconder indisponiveis sem explicacao; rebaixar e sugerir alternativas.
- Favorito/recentes devem afetar ordem ou atalho, nao apenas icone.
- Busca deve respeitar disponibilidade e alternativas.

PDP:

- Se produto indisponivel, apresentar substituto ou "ver semelhantes".
- Se estoque baixo, prevenir erro antes do carrinho.
- Se alergeno/restricao conhecida, destacar sem drama.
- Se horario/momento torna produto pouco pertinente, nao bloquear; apenas
  priorizar escolhas melhores no menu/home.

Carrinho:

- Minimo, estoque parcial e loja fechando devem aparecer antes do checkout.
- Remocao de item com undo e dismiss.
- Reorder com skips deve explicar o que entrou e o que nao entrou.

Aceite:

- `CatalogProjection` ou builders associados expõem ranking/reason flags.
- Testes cobrem almoco, recorrente, favorite_category, indisponivel e loja
  fechando.

### WP-OF-4 - Checkout como resolucao guiada de intencao

Objetivo: checkout deve parecer inevitavel e seguro, nao formulario.

Entregas:

- Cada step deve ter:
  - resumo quando completo.
  - motivo claro quando bloqueado.
  - CTA unico quando atual.
  - recovery quando falha.
- "Contato" fica colapsado quando conhecido.
- Fulfillment default vem de historico/origem/contexto quando confiavel.
- Retirada nao deve passar por endereco.
- Delivery nao deve deixar passar sem endereco valido.
- Pagamento mostra metodo escolhido e consequencia operacional.
- Botao final permanece "Enviar pedido".
- Ao enviar, copy deve deixar claro que o estabelecimento conferira
  disponibilidade antes do pagamento ser capturado/confirmado conforme metodo.

Aceite:

- F5 e back/forward mantem step correto.
- Nao ha caminhos por URL que pulem guardrails.
- Testes reais cobrem pickup, delivery, editar endereco, trocar usuario e
  carrinho alterado durante checkout.

### WP-OF-5 - Pagamento e tracking como promessa operacional

Objetivo: eliminar ambiguidades entre disponibilidade, pagamento e preparo.

Pagamento:

- Pix so aparece como acao principal quando disponibilidade estiver confirmada.
- Se Pix ainda nao pode ser pago, cliente nao deve ver tela de pagamento seca.
- Quando disponibilidade confirmar, o cliente deve ser levado ou notificado
  ativamente para pagar.
- QR code mock em dev deve simular o fluxo de producao, sem confirmar pagamento
  por refresh.
- Cartao usa autorizacao/captura sem exigir nova acao do cliente quando possivel.
- Falha de criacao de intent deve ter retry idempotente e mensagem operacional.

Tracking:

- Sempre responder:
  - o que esta acontecendo agora.
  - se o cliente precisa fazer algo.
  - qual prazo importa.
  - o que acontece depois.
  - como recuperar se atrasar/falhar.
- Nao mostrar steps futuros quando isso causar ruido.
- Nao manter alertas superados.
- Timestamp visivel para eventos cumpridos.
- Estado stale/offline explicito: "Atualizado ha X min"; se passar do limite,
  mostrar que estamos conferindo atualizacao.
- Pickup e delivery precisam ter contratos diferentes.

Aceite:

- `OrderTrackingProjection` e projection/status partial sao a unica fonte de
  semantica de tracking.
- Testes cobrem Pix pendente, Pix expirado, pagamento reconhecido, preparo,
  pronto para retirada, aguardando entregador, saiu para entrega, entregue,
  concluido e cancelado.

### WP-OF-6 - Notificacao ativa e preferencia de canal

Objetivo: eventos criticos nao podem depender de refresh silencioso.

Eventos criticos:

- disponibilidade confirmada com Pix pendente.
- pagamento expirado.
- pagamento falhou.
- pedido confirmado.
- pedido atrasou alem da promessa.
- pedido pronto para retirada.
- pedido pronto aguardando entregador.
- saiu para entrega.
- entregue.
- cancelado ou rejeitado.

Entregas:

- Criar matriz evento -> canal:
  - push, se autorizado.
  - WhatsApp/ManyChat, se origem ou preferencia permitir.
  - SMS/email como fallback conforme consentimento.
  - tracking SSE/polling como superficie passiva.
- Envio deve respeitar preferencias do cliente.
- Cada notificacao deve ser idempotente por evento/ref.
- Falha de notificacao vira alerta operacional, nao log perdido.

Aceite:

- Testes provam que evento critico dispara tentativa ativa.
- Testes provam que preferencia/consentimento e respeitado.
- Notificacao nao duplica em refresh.

### WP-OF-7 - Backstage Omotenashi para operador

Objetivo: o sistema servir o operador para que o operador sirva o cliente.

Order queue:

- Pedido novo aparece sem refresh manual.
- Lista nao deve piscar nem voltar ao topo quando atualiza.
- Atualizacao preferencial por HTMX/SSE com swap granular.
- Separar zonas por acao operacional: entrada, disponibilidade, pagamento
  pendente, preparo, pronto, aguardando entregador/retirada, transito.
- Cada card mostra acao primaria correta e bloqueios explicados.

Detalhe do pedido:

- Operador ve contexto antes de agir:
  - prazo restante de disponibilidade.
  - status de pagamento.
  - fulfillment.
  - itens, observacoes, restricoes/alergenos.
  - risco de estoque.
- Confirmar disponibilidade so quando status permitir.
- Ajustar pedido dentro de guardrails aproveitando mecanismos de quantidade e
  substitutos existentes.
- Mark paid, quando existir para admin, deve ser caminho explicito, contextual,
  auditavel e raro, nao atalho que mistura tarefas.

KDS:

- Status de KDS e tracking precisam ter contrato 1:1.
- "Marcar pronto" deve deixar claro se e item, pedido, retirada ou delivery.
- Pedido delivery pronto nao pode aparecer para cliente como "saiu para entrega"
  antes do despacho real.

Aceite:

- Testes de contrato backstage <-> storefront.
- Teste de scroll/refresh da fila.
- Teste de ajuste/substituto.
- Teste de acao bloqueada com motivo claro.

### WP-OF-8 - Kintsugi sistemico

Objetivo: toda falha ter recuperacao elegante, objetiva e segura.

Cenarios obrigatorios:

- Pix expirado.
- Falha ao gerar Pix.
- Card recusado.
- Gateway fora.
- Database locked em dev.
- Estoque insuficiente apos checkout.
- Produto removido/pausado.
- CEP invalido.
- Fora da area de entrega.
- Loja fecha durante carrinho/checkout.
- Tracking stale.
- Pedido rejeitado pelo estabelecimento.
- Cancelamento recusado.
- Notificacao falhou.

Padrao:

```text
O que aconteceu.
O que isso significa para o pedido.
O que voce pode fazer agora.
O que faremos automaticamente.
```

Aceite:

- Nenhum erro visivel sem CTA ou proxima acao.
- Nenhum estado terminal ainda mostra promessa ativa.
- Falhas recuperaveis mantem carrinho/pedido quando possivel.

### WP-OF-9 - Admin e governanca de copy

Objetivo: permitir ajuste fino sem permitir quebrar o fluxo.

Entregas:

- Admin de `OmotenashiCopy` deve mostrar:
  - chave.
  - onde aparece.
  - default atual.
  - moment/audience.
  - preview.
  - risco se copy for vazia.
- Copy editavel nao pode mudar semantica operacional.
- Estados/prazos/status nao devem ser editados como texto livre quando sao
  contrato de dominio.
- Seed deve criar exemplos bons e realistas, nao atalhos falsos.

Aceite:

- Teste garante que toda key usada em template/projection existe.
- Teste garante que copy vazia nao quebra UI.
- Admin nao permite criar combinacoes ambiguas sem fallback.

### WP-OF-10 - Observabilidade de promessa

Objetivo: saber quando Omotenashi falha em producao.

Metricas:

- tempo em cada etapa do pedido.
- prazo de disponibilidade cumprido/estourado.
- prazo de pagamento Pix cumprido/expirado.
- atraso de preparo.
- atraso de entregador.
- tracking stale.
- tentativas de notificacao e falhas.
- recovery usado.
- refresh manual em paginas que deveriam atualizar sozinhas.
- operador tentou acao bloqueada.

Entregas:

- Eventos estruturados.
- Painel backstage com promessas em risco.
- Logs com `order_ref`, `event`, `promise`, `deadline`, `channel`.

Aceite:

- Toda promessa com deadline gera metrica.
- Toda breach gera alerta ou registro operacional.

### WP-OF-11 - Testes praticos e seed de realidade

Objetivo: impedir que teste dobre a realidade para passar.

Camadas:

- Unit tests para resolucao de contexto.
- Projection tests para contratos de UI.
- Service tests com DB real para lifecycle.
- Web tests para templates e HTMX partials.
- E2E prático com dev/mock simulando producao.
- Manual scripts com seed para jornadas sensiveis.

Seed obrigatorio:

- cliente anonimo.
- cliente novo.
- cliente recorrente com ultimo pedido.
- cliente VIP.
- cliente aniversario.
- pedido Pix aguardando disponibilidade.
- pedido Pix aguardando pagamento.
- Pix expirado.
- cartao autorizado aguardando captura.
- pedido em preparo.
- pickup pronto.
- delivery pronto aguardando entregador.
- delivery em transito.
- pedido cancelado por pagamento expirado.
- pedido rejeitado por indisponibilidade.
- operador com fila cheia.
- produto com estoque baixo.
- produto indisponivel com substituto.
- loja fechando.
- loja fechada.

Aceite:

- Dev/mock segue o mesmo fluxo semantico de producao.
- Nenhum teste confirma pagamento por refresh.
- Nenhum teste chama service interno para pular tela obrigatoria sem declarar
  explicitamente que e teste de service.
- Cada bug grave corrigido ganha teste de jornada ou contrato.

### WP-OF-12 - Quality gates permanentes

Objetivo: garantir que a plenitude nao regrida.

Gates:

- `OmotenashiContext` nao pode virar apenas copy.
- Toda nova surface precisa de projection ou contrato equivalente.
- Toda nova promessa precisa de deadline/stale/recovery quando aplicavel.
- Toda acao de operador precisa de guardrail e feedback.
- Todo evento critico precisa de notificacao ativa ou justificativa documentada.
- Toda copy critica precisa estar no Admin/defaults.
- Todo novo status de pedido precisa atualizar tracking e backstage.

Automacoes:

- Teste que mapeia keys de copy usadas.
- Teste que procura strings proibidas sem recovery.
- Teste que compara contratos backstage/storefront para status.
- Teste que valida seeds de cenarios.
- Teste que valida ausencia de URL shortcuts perigosos.

## Ordem recomendada

1. WP-OF-0 - auditoria e matriz.
2. WP-OF-1 - contexto e origem/canal.
3. WP-OF-2 - protocolos de jornada.
4. WP-OF-5 - pagamento/tracking, por ser area mais sensivel.
5. WP-OF-7 - backstage, para alinhar promessa operacional.
6. WP-OF-6 - notificacoes ativas.
7. WP-OF-3 - home/menu/PDP/cart.
8. WP-OF-4 - checkout.
9. WP-OF-8 - kintsugi sistemico.
10. WP-OF-9 - admin/governanca.
11. WP-OF-10 - observabilidade.
12. WP-OF-11/12 - seed e gates permanentes.

Essa ordem prioriza confianca operacional antes de refinamento de descoberta.

## Definicao de pronto

Omotenashi-first pleno significa:

- Cliente sempre sabe o que esta acontecendo agora.
- Cliente sempre sabe se precisa agir.
- Cliente sempre ve prazo quando ha prazo.
- Cliente nunca ve promessa superada.
- Cliente nunca precisa refresh para entender estado critico.
- Operador ve a acao certa, no momento certo, com bloqueio explicado.
- Backstage e storefront contam a mesma historia.
- Mock de dev simula producao em fluxo, nao em atalho.
- Toda falha recuperavel tem caminho.
- Toda decisao sensivel tem teste.
- Copy e objetiva, editavel onde deve ser, e nunca substitui fluxo.

## Frase de verificacao

Ao revisar qualquer mudanca, perguntar:

"Este contexto tornou a jornada mais segura, clara e adequada, ou apenas deixou
a frase mais simpática?"

Se a resposta for a segunda, ainda nao e Omotenashi.
