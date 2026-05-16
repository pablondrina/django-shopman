# Headless Surface Contract

Status: contrato canonico para acoplamento de superficies.
Data-base: 2026-05-15

Este contrato descreve como qualquer superficie acopla em Shopman sem virar coproprietaria de regra de pedido, catalogo, pagamento, estoque, availability ou recovery.

## Regra central

```text
InteractionContext -> Projection -> canonical node(actions[]) -> Action -> Intent -> Mutation -> Projection
```

Superficies publicas enxergam **Projection com Actions**. O restante e mecanismo interno do core/orquestrador.

Django/Penguin foi a primeira referencia completa/madura de implementacao, mas nao e canon.

| Conceito | Publico para superficie? | Dono | Papel |
| --- | --- | --- | --- |
| `InteractionContext` | Nao | Shopman core/orquestrador | Normaliza canal, superficie, cliente, sessao, momento, device, origem, localidade e alvo da interacao. |
| `Projection` | Sim | Shopman core/orquestrador | Estado resolvido, factual e pronto para renderizacao. |
| `Action` | Sim | Shopman core/orquestrador | Opcao acionavel, ja filtrada por contexto, policies, availability e seguranca. |
| `Intent` | Nao | Adapter/API Shopman | Escolha normalizada feita a partir de uma Action. |
| `Mutation` | Nao | Services canonicos | Efeito idempotente que altera estado usando Orderman/Payman/Stockman/Guestman/Doorman. |
| `ChannelPolicyResolution` | Nao | ChannelConfig/services/builders | Insumo interno de policy/resolution, nao volante de UX da superficie. |
| `Recovery` | Sim, como Actions | Projection builder | Actions de retomada para erro, bloqueio, expiracao ou estado parcial. |

## Como uma superficie deve operar

1. Enviar ou carregar um `InteractionContext` implicito: canal, superficie, sessao/cliente, pedido/carrinho em foco e contexto tecnico.
2. Buscar uma Projection canonica.
3. Renderizar dados, copy, timers, availability e actions recebidos.
4. Quando o usuario escolhe algo, disparar a Action declarada sem recriar regra local.
5. O adapter/API normaliza isso em Intent.
6. Um service canonico aplica a Mutation idempotente.
7. A superficie atualiza a tela/conversa com a nova Projection.

Nuxt, Ionic, ManyChat, POS e Django/Penguin seguem o mesmo ciclo. A diferenca entre elas e ergonomia de interacao, nao regra de negocio.

## O que deve estar em Projection

Quase tudo que a interface mostra deve derivar de Projection, especialmente:

- produtos ofertados, secoes, categorias, ordem, destaque e busca;
- preco, desconto, promocao, loyalty e taxa;
- disponibilidade, estoque apresentavel, low stock, sold out, holds e janela temporal;
- fulfillment, delivery/pickup, slots, endereco, area atendida e deadlines;
- pagamento, payment gate, PIX, hosted checkout, status e polling;
- pedido, tracking, timeline, next_event, recovery e cancelamento;
- copy operacional, omotenashi, mensagens de bloqueio e confirmacoes;
- actions primarias, secundarias, destrutivas, handoff e atendimento.

Uma superficie pode ter estado local de UI: modal aberto, foco, scroll, skeleton, cache, haptic, animacao, storage temporario. Ela nao pode derivar decisao operacional local quando Shopman consegue projetar essa decisao.

## Action schema minimo

Novas projections que expõem acoes devem convergir para um formato pequeno:

| Campo | Obrigatorio? | Descricao |
| --- | --- | --- |
| `ref` | Sim | Identificador estavel da acao. |
| `kind` | Sim | `link`, `mutation`, `external`, `copy`, `instruction` ou extensao documentada. |
| `label` | Sim | Texto curto pronto para botao/menu/resposta. |
| `priority` | Sim | `primary`, `secondary`, `danger`, `quiet`. |
| `enabled` | Sim | Se pode executar agora. |
| `reason` | Quando bloqueada | Motivo factual para omotenashi e debugging. |
| `href` | Para link/handoff | URL ou rota canonica. |
| `method` | Para mutation | Metodo HTTP esperado. |
| `payload_schema` | Quando ha payload | Forma minima esperada, sem regra escondida. |
| `idempotency` | Para mutation | `none`, `recommended` ou `required`. |
| `confirmation` | Para risco | Copy e severidade da confirmacao. |

O schema deve ficar pequeno. Se uma action exige muitos campos especificos, primeiro verifique se ela deveria ser uma Projection propria ou uma extension existente.

## Onde actions vivem

Actions vivem no menor no canonico que ja representa a decisao operacional.
Isso evita control plane paralelo e evita duplicar estado.

- Em checkout, a decisao acionavel pertence a `CheckoutProjection`, portanto
  fica em `checkout.actions[]`.
- Em tracking e payment, a decisao acionavel pertence a promise operacional ja
  existente, portanto fica em `promise.actions[]`.
- Em conversa, `RemoteConversationProjection.actions[]` e uma projection
  compacta derivada da promise escolhida para WhatsApp/ManyChat.

Lista vazia e o contrato para "nada acionavel agora". Nao usar action falsa
como `wait`, `none` ou `noop` para preencher ausencia de acao.

## InteractionContext

`InteractionContext` e cidadao de primeira classe, mas nao deve virar control plane novo. Ele e envelope de entrada para Projection builders e services.

Fontes tipicas:

- `channel_ref`: `web`, `whatsapp`, `mobile`, `pdv`, marketplace.
- `surface_ref`: `nuxt`, `ionic`, `manychat`, `django_penguin`, `pos`.
- `customer_ref`, sessao anonima, telefone normalizado, consentimentos.
- momento, timezone, janela de producao, data prometida, feriado, abertura/fechamento.
- device, viewport/capacidade tecnica, origem e handoff anterior.
- carrinho, pedido, payment intent ou AccessLink em foco.
- localidade, endereco, area atendida, distancia e disponibilidade operacional.
- selecoes ainda transientes que mudam a Projection, como `delivery_date`
  no checkout: slots devem ser projetados para o carrinho e para a data
  escolhida, nao recalculados pela superficie.

`OmotenashiContext` e uma lente dentro desse contexto, nao sinonimo dele. Omotenashi e cross-system: decide a forma humana, acionavel e cuidadosa da Projection em storefront, WhatsApp, POS e backstage.

## Relação com ChannelConfig e policy resolution

`ChannelConfig` continua sendo o contrato forte para variacao por canal: confirmacao, pagamento, fulfillment, stock, notifications, pricing, editing e rules.

ChannelPolicyResolution pode existir como resultado intermediario de policy/resolution. A regra e:

- `ChannelConfig` define policy.
- Services resolvem disponibilidade e fatos.
- Builders produzem Projection com Actions.
- Superficies renderizam Projection com Actions.

Uma superficie nao deve perguntar "posso mostrar esse botao?" lendo policy crua se a Projection ja pode entregar a Action pronta. ChannelPolicyResolution e insumo interno.

Nao existe compatibilidade aberta: se uma API ainda retorna policy crua ou usa nomenclatura antiga para mutation, isso e detalhe de implementacao existente. Nenhuma superficie nova deve depender disso para UX, e todo fluxo tocado deve convergir para Projection/Action/Intent/Mutation.

## Relação com ManyChat

ManyChat coleta Intent conversacional e renderiza Projection. Ele pode apresentar preco, estoque, prazo, taxa, opcoes e recovery quando esses dados vierem do Shopman.

Continua proibido manter regra autoritativa de pricing, stock, availability, payment gate ou lifecycle no editor do ManyChat. A automacao deve chamar Shopman, receber Projection com Actions e responder.

## Relação com Nuxt/Ionic

Nuxt e Ionic devem ser consumidores equivalentes do mesmo contrato. A diferenca esperada e visual/interativa:

- componentes, layout, navegacao e storage local;
- affordances mobile como safe-area, gestures e haptic;
- adaptacao de `href`/rotas para a shell da superficie.

Nao devem existir BFF paralelo, union local de status de pedido, fallback local de pricing/stock ou CTA inventado por tela.

## Anti-padroes

- Criar `RemoteOrder`, `RemoteLifecycle`, `remote_status` ou status oficial novo sem prova de gap real.
- Tratar Django/Penguin como canon porque foi a primeira implementacao completa.
- Fazer ManyChat ou Nuxt calcularem preco, disponibilidade, payment gate, timers ou permissao de `cancel_order`.
- Usar policy crua como volante publico de UX.
- Criar Actions localmente na superficie quando o backend poderia projetar.
- Transformar Recovery em estado separado; recovery e actions em uma Projection.
- Criar nomenclatura paralela para Mutation como linguagem publica nova.

## Checklist para nova superficie

1. Mapeie rotas/fluxos para projections canonicas existentes.
2. Liste actions necessarias por tela/conversa.
3. Quando faltar action, estenda a Projection antes de criar regra local.
4. Quando faltar fato/contexto, estenda o Projection builder ou InteractionContext.
5. Mutacoes sensiveis devem ser idempotentes.
6. Toda resposta de erro recuperavel deve voltar com recovery actions.
7. Rode matriz E2E e suite de paridade antes de refinar layout.
