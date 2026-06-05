# Spec — Vendas Agênticas / Conversacional [Etapa C · WP2]

> Iniciativa [[project_excellence_refactor_initiative]]. Pilar **Vendas Agênticas**. Ancorada na
> [Arquitetura](04-architecture.md) (contrato `Projection`/`Action`/`Presentation`), na decisão
> [D4](02-confronto.md) e no [Mapa do Core](00-core-capability-map.md). Benchmark:
> [Take.app](../research/pos-benchmarks/take-app.md) (o pedido **é** uma mensagem) + Shopify Agentic.
> É a superfície **headless**: sem UI própria, **consumidor do MESMO contrato** que web/PDV/admin.

## 0. Posição na arquitetura (inegociável)
- A superfície agentic é **headless** = **apresentação pura sem tela própria**. A "Presentation" aqui é
  **render da `Projection` como mensagem** (texto/blocos de WhatsApp), e o "comando" é a `Action` emitida
  como cliente autenticado. **Zero política, zero Core, zero lifecycle paralelo.**
- **Núcleo (já existe no Core):** `conversation.build_order_conversation → RemoteConversationProjection`
  (a Projection achatada pra conversa, com `actions[]`) + `remote_mutations.run_idempotent_mutation` (o
  comando idempotente) + `AccessLink` (doorman — ponte sem-login chat→web) + `OmotenashiCopy` (copy da
  conversa, editável no Admin). **Não construir UI nem fluxo novo** — orquestrar o que já está pronto.
- **Transporte:** ManyChat ([[feedback_whatsapp_via_manychat]] — WhatsApp via ManyChat, **não** Meta
  Cloud API direta). O agentic **não fala com o cliente** por conta própria — ele renderiza a Projection
  como mensagem e ManyChat entrega; respostas viram `Action`/`Intent` que o orquestrador resolve.
- **Config-driven:** copy via `OmotenashiCopy` (key/moment/audience), comportamento via `ChannelConfig`
  do canal conversacional, consentimento via Guestman `ConsentService` (LGPD, gate pré-envio).

## 1. Tenets do Agentic (regem cada interação)
1. **Headless = mesmo contrato.** A conversa consome `Projection` + `Action` idêntico ao storefront/PDV.
   Se precisa de um dado/ação que a Projection não tem, a resposta é "a Projection passa a expor", nunca
   "o bot calcula". O agentic é o **canário** do corte dado/apresentação (só funciona se a Projection for
   100% surface-agnostic).
2. **Princípio binário (Pablo):** ou **resolve tudo no chat**, ou **leva pra web e segue** — sem
   meio-termo. Toda interação cai num desses dois trilhos.
3. **Transaciona como cliente autenticado.** Identidade via Guestman (`find_or_create_customer` por
   contato) + doorman (`AccessLink`/OTP). O bot age **como o cliente**, com as mesmas permissões — não há
   "modo bot" com regra própria.
4. **Omotenashi na conversa.** Copy acolhedora via `OmotenashiCopy`; acessibilidade (mensagens claras,
   uma decisão por vez); availability-first e timeouts transparentes ([[feedback_transparent_timeouts]])
   também valem no chat.
5. **Idempotência sempre.** Todo comando da conversa via `remote_mutations.run_idempotent_mutation`
   (chave idempotente) — re-tentativas de mensagem não duplicam pedido.
6. **Consentimento é gate.** `ConsentService.has_consent` antes de qualquer envio outbound (LGPD).

## 2. As duas rodadas (D4)

### 2.1 Rodada 1 (agora) — ponte low-friction conversa → loja
- **Função:** a conversa **direciona pra loja**. Compartilhar carrinho/contexto → **link sem-login**
  pro storefront (`AccessLink` do doorman, `PRESERVE_SESSION_KEYS` carrega o carrinho no destino).
- **Projection:** `RemoteConversationProjection` achatada → mensagem com `Action(kind="link", href=<AccessLink>)`.
- **Presentation (render-como-mensagem):** copy via `OmotenashiCopy` ("Montei seu carrinho, é só
  finalizar aqui 👉"); o link abre o storefront já com o carrinho (sem login).
- **Fluxos ManyChat:** os gatilhos/menus do ManyChat chamam o endpoint que monta a Projection e devolve a
  mensagem + link. **Copy configurável via Admin** (`OmotenashiCopy`), não hardcoded no flow.
- **Comando:** criar `AccessLink` via `shop.services.access` (`AccessLinkService.create_token`/`send_access_link`).

### 2.2 Rodada 2 (prevista — projetar o contrato pra ser barata depois) — in-chat
- **Função:** resolução **dentro do chat** (disponibilidade/carrinho/pagamento/confirmação na conversa)
  — quando der pra **resolver tudo no chat** (trilho binário). Caso contrário, cai na Rodada 1 (leva
  pra web).
- **Projection:** a mesma `RemoteConversationProjection` com `actions[]` mais ricas (escolher item,
  confirmar disponibilidade, pagar via link PIX, confirmar pedido). Cada passo = uma `Action`.
- **Presentation:** cada `Action` vira um botão/resposta-rápida do WhatsApp (ManyChat); a resposta do
  cliente vira `Intent` → `remote_mutations` aplica a `Mutation` → nova Projection → próxima mensagem.
- **Comando:** `remote_mutations.run_idempotent_mutation` (commit de checkout, add/remove linha, etc.).
- **Pagamento:** PIX-first via link (payman); o webhook é o caminho confiável de retorno (PCI SAQ A) —
  a confirmação otimista (`ChannelConfig.confirmation`) fecha o pedido quando pago.
- **Barata SE o contrato for uniforme:** como `conversation`+`remote_mutations`+`Action` já existem e a
  Projection é surface-agnostic, a Rodada 2 é **render + roteamento**, não um subsistema novo.

## 3. #4 (agente IA autônomo / ACP) — opcionalidade grátis, não feature
- **Não priorizar.** Mas como o contrato de comando é uniforme e idempotente (`Projection` + `Action` +
  `remote_mutations`, auth por handle/contato), um **agente externo autônomo** seria só **mais um cliente
  do contrato**. Ganhamos a opcionalidade de graça — desenhar a Rodada 2 sem fechar essa porta (não
  inventar estado/sessão que só um humano-no-loop conseguiria preencher).

## 4. Cross-cutting (config-driven, não hardcoded)
- **Copy:** 100% `OmotenashiCopy` (key/moment/audience) — toda mensagem do bot é editável no Admin.
- **Identidade/auth:** Guestman (`IdentifierService.find_or_create_customer`, `ManychatService.sync_subscriber`)
  + doorman (`AccessLink`, OTP). `normalize_phone` (E.164, repara bug ManyChat).
- **Consentimento:** Guestman `ConsentService` (opt-in por canal, LGPD) — gate pré-envio.
- **Comportamento:** `ChannelConfig` do canal conversacional (confirmation/payment/stock scope).
- **Notificações:** `NotificationTemplate` por evento; cadeia phone-first (ManyChat→sms→email).

## 5. O que o Agentic NÃO faz (anti-frankenstein)
- **Não tem UI própria** nem fluxo de tela — renderiza Projection como mensagem.
- **Não calcula** preço/disponibilidade/elegibilidade (consome a Projection).
- **Não cria lifecycle paralelo** — `remote_mutations` usa os services canônicos (commit/cancel/etc.).
- **Não fala com Meta Cloud API direta** — WhatsApp via ManyChat ([[feedback_whatsapp_via_manychat]]).
- **Não hardcoda copy** — `OmotenashiCopy`.
- **Não tem "regra de bot"** — transaciona como cliente autenticado, mesmas permissões.

## 6. Alavancas do Core que o Agentic consome (referência)
- Conversa: `conversation.build_order_conversation` → `RemoteConversationProjection` (Projection + Actions).
- Comando: `remote_mutations.run_idempotent_mutation` (idempotente, services canônicos).
- Ponte sem-login: doorman `AccessLink` (`AccessLinkService.create_token/exchange/send_access_link`,
  `PRESERVE_SESSION_KEYS`).
- Identidade/CRM: Guestman (`find_or_create_customer`, `ManychatService.sync_subscriber`, `ConsentService`).
- Pagamento: payman (PIX-first via link); webhook como retorno confiável.
- Config/copy: `OmotenashiCopy`, `ChannelConfig`, `NotificationTemplate`.

## 7. Aberto (decidir na implementação / com Pablo)
- Catálogo de `Action`s da Rodada 2 (quais passos viram resposta-rápida vs quando cair pra web — o
  trilho binário na prática).
- Mapeamento dos fluxos ManyChat ↔ endpoints de Projection (quais gatilhos, quais menus).
- Limite de "resolve tudo no chat" (peso/customização da padaria pode exigir web) — calibrar com Nelson.
