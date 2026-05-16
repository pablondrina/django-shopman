# ADR-012 - Contrato headless de superficie: Projection com Actions

**Status:** Accepted
**Data:** 2026-05-15
**Escopo:** Nuxt, Ionic, ManyChat, Django/Penguin, POS e futuras superficies/adapters.

---

## Contexto

Shopman precisa permitir pedido remoto em qualquer superficie sem copiar regra de negocio para cada implementacao visual ou conversacional. Django/Penguin foi a primeira referencia de implementacao completa e madura, util para descobrir UX, copy, recuperacao e casos esquecidos; ele nao e canon de dominio.

O canon e Shopman core/orquestrador: Orderman, Payman, Stockman, Guestman, Doorman, ChannelConfig, Directives, services, projections e contratos documentados. A filosofia que governa este contrato e core enxuto, flexivel, agnostico, KISS, DRY, YAGNI, Omotenashi-first, WhatsApp-first e Mobile-first.

O ponto fragil identificado era vocabulario: policy crua, action, intent e mutation estavam perto demais. Isso criava risco de cada superficie montar seu proprio control plane.

## Decisao

O contrato publico de superficie e **Projection com Actions**.

```text
InteractionContext -> Projection -> canonical node(actions[]) -> Action -> Intent -> Mutation -> Projection
```

Superficies consomem somente:

- **Projection:** estado resolvido, factual e pronto para renderizacao.
- **Action:** proxima acao oferecida pelo Shopman, ja filtrada por contexto, politica, disponibilidade, seguranca e canal.

Backend/orquestrador usa internamente:

- **InteractionContext:** envelope de contexto da interacao atual.
- **Intent:** resposta normalizada quando uma Action e acionada.
- **Mutation:** efeito idempotente aplicado pelos services canonicos.
- **ChannelPolicyResolution:** insumo interno de policy/resolution, nunca volante de UX da superficie.

Mutation idempotente e o unico nome canonico para efeitos vindos de Actions. Nomenclatura paralela para o mesmo papel nao deve permanecer quando o fluxo for tocado.

Nao existe compatibilidade aberta. Ponte tecnica existente nao e contrato canonico, nao deve ganhar novos consumidores e deve convergir para Projection/Action/Intent/Mutation assim que o fluxo for tocado.

## Conceitos

### InteractionContext

Entrada normalizada para resolver uma Projection. Ele captura `channel_ref`, `surface_ref`, cliente/sessao, momento, device, origem, localidade, pedido/carrinho em foco, consentimentos conhecidos e qualquer lente contextual necessaria para decidir o que e adequado mostrar ou oferecer agora.

`OmotenashiContext` nao substitui `InteractionContext`; ele e uma lente essencial dentro dele, especialmente QUANDO/QUEM e memoria relacional. Omotenashi e cross-system: tambem governa backstage, POS, recovery, copy operacional e a escolha de Actions.

### Projection

Resposta autoritativa para uma superficie. Uma Projection deve carregar dados, copy operacional, disponibilidade, promises, timers, erros recuperaveis e actions suficientes para a superficie renderizar sem inferir regra de negocio.

Se uma superficie precisa decidir "quais produtos oferecer", "tem hoje?", "qual prazo?", "qual pagamento?", "qual CTA?", "como recuperar?", a resposta deve vir de uma Projection ou de extensao de Projection existente.

### Action

Opcao acionavel que Shopman oferece. Ela e a manifestacao pratica do Omotenashi: nao basta informar, a resposta deve ser acionavel quando houver caminho seguro.

Actions vivem no menor no canonico que ja representa a decisao operacional:
`CheckoutProjection.actions[]` no checkout, `promise.actions[]` em
tracking/payment e `RemoteConversationProjection.actions[]` quando a conversa
achata a promise escolhida para WhatsApp/ManyChat. Lista vazia significa que
nao ha acao acionavel agora; nao se usa `wait`, `none` ou `noop` como action
falsa.

Campos minimos recomendados para novas projections:

| Campo | Papel |
| --- | --- |
| `ref` | Identificador estavel da acao. |
| `kind` | `link`, `mutation`, `external`, `copy`, `instruction` ou vocabulario equivalente e pequeno. |
| `label` | Copy curta pronta para a superficie. |
| `priority` | `primary`, `secondary`, `danger` ou `quiet`. |
| `enabled` | Se a acao pode ser executada agora. |
| `reason` | Motivo factual quando bloqueada ou contextual. |
| `href` | Destino quando for navegacao ou handoff. |
| `method` | Metodo esperado quando for mutacao HTTP. |
| `payload_schema` | Forma minima esperada do payload quando necessario. |
| `idempotency` | `none`, `recommended` ou `required`. |
| `confirmation` | Confirmacao exigida para acao sensivel/destrutiva. |

### Intent

Intent e a escolha normalizada que chega ao backend depois que uma Action foi acionada. Action e "o que Shopman oferece"; Intent e "o que o cliente/operador/superficie escolheu ou informou". Eles nao sao a mesma coisa.

Intent nao deve carregar regra autoritativa de preco, estoque, disponibilidade, pagamento ou lifecycle. ManyChat, Nuxt e Ionic podem coletar Intent; Shopman resolve a verdade.

### Mutation

Aplicacao idempotente da Intent por service canonico. Exemplos: commit de checkout, cancelamento, reorder, rating, criacao de AccessLink, alteracao de endereco. Mutation nao cria lifecycle paralelo: ela usa Orderman, Payman, Stockman, Guestman, Doorman, Directives e services existentes.

### Recovery

Recovery nao e nova entidade nem novo lifecycle. E o conjunto de Actions oferecidas quando a Projection detecta bloqueio, erro, expiracao, ambiguidade ou estado parcial. Exemplos: pagar agora, copiar PIX, trocar forma de pagamento, revisar carrinho, chamar atendimento, abrir AccessLink, tentar novamente com chave idempotente.

### ChannelPolicyResolution

ChannelPolicyResolution resolve policy por canal para builders de Projection. `ChannelConfig` e services podem gerar essa resolucao interna. A superficie nao deve usar policy crua para inventar CTA, texto, status ou passo de fluxo quando uma Action/Projection equivalente existir.

## Consequencias

Aceitamos:

- Superficies ficam finas: renderizam Projection, disparam Action e atualizam pela nova Projection.
- ManyChat pode mostrar preco/estoque/prazo quando esses dados vierem do Shopman; continua proibido manter regra autoritativa no bot.
- Nuxt/Ionic/POS usam o mesmo contrato, mudando somente interacao, layout, navegacao e storage local.
- ChannelPolicyResolution e mutation adapters existentes sao detalhe de implementacao onde ja existem; nao sao zona de compatibilidade aberta nem justificativa para novo contrato paralelo.

Nao aceitamos:

- Criar `RemoteOrder`, status remoto ou lifecycle paralelo.
- Criar control plane novo para superficie quando Projection com Actions resolve.
- Tratar Django/Penguin como fonte canonica de dominio.
- Expor policy crua como API publica principal para decisoes de UX quando actions resolvidas ja existem.
- Duplicar pricing, stock, payment gate, timers, availability ou next_event em Nuxt, Ionic, ManyChat ou qualquer superficie.

## Referencias

- [ADR-005 - Orchestrator as Coordination Center](adr-005-orchestrator-as-coordination-center.md).
- [ADR-006 - Order Status Semantics](adr-006-order-status-semantics.md).
- [ADR-009 - WhatsApp via ManyChat](adr-009-whatsapp-via-manychat.md).
- [docs/reference/headless-surface-contract.md](../reference/headless-surface-contract.md).
- [docs/reference/storefront-surface-parity-contract.md](../reference/storefront-surface-parity-contract.md).
