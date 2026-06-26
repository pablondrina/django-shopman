# MANYCHAT-CONVERSACIONAL-PLAN — Pedido por WhatsApp conversacional

> Fechar o fluxo **ManyChat → session → confirmação** (cliente faz pedido por
> conversa no WhatsApp). Frente **v1** (🆕, Onda 1 · canais externos) do
> [PRODUCT-V1-SCOPE-BACKLOG](PRODUCT-V1-SCOPE-BACKLOG.md). WhatsApp é **sempre via
> ManyChat** ([ADR-009](../decisions/adr-009-whatsapp-via-manychat.md)), nunca Meta
> Cloud API direta.

**Status**: 🟡 Plano proposto (2026-06-26) — groundwork; aguarda revisão do Pablo +
credenciais ManyChat (bloqueio). É "reimplementar", não "do zero".

---

## Achado-chave: a maior parte já existe

A pesquisa reversa mostrou que o fluxo está ~70% pronto — o gap é o **inbound de
pedido**. Reusar:

| Peça | Estado | Onde |
|---|---|---|
| Notificação outbound (sistema→WhatsApp) | ✅ funciona | [`shopman/shop/adapters/notification_manychat.py`](../../shopman/shop/adapters/notification_manychat.py) |
| Sync de contato (subscriber→Customer/ContactPoint) | ✅ | `packages/guestman/.../contrib/manychat/service.py` |
| Resolver subscriber (cliente→id ManyChat) | ✅ | `.../contrib/manychat/resolver.py` |
| Projection conversacional (`RemoteConversationProjection`) | ✅ | [`shopman/shop/services/conversation.py`](../../shopman/shop/services/conversation.py) |
| AccessLink (chat→web magic link), source=MANYCHAT | ✅ ~95% | `packages/doorman/.../models/access_link.py` |
| Webhook handler (HMAC + replay) | ⚠️ existe, **não registrado** | `.../contrib/manychat/views.py` + `urls.py` |
| Criação de pedido headless (session→commit) | ✅ | [`shopman/shop/services/sessions.py`](../../shopman/shop/services/sessions.py) |

## Gaps reais (o que construir)

1. **Webhook não registrado**: `contrib/manychat/urls.py` existe mas **não é
   incluído** em `config/urls.py` → nunca é alcançado. (Ativar é passo 1 — mas
   só junto com o resto, para não expor endpoint meia-boca.)
2. **Endpoint de intenção de pedido**: receber `{subscriber_id, items:[{sku,qty}],
   fulfillment, address?, phone}` → criar Session (`create_session` +
   `modify_session`) → retornar projection conversacional
   (`build_order_conversation`).
3. **Endpoint de confirmação**: `{session_key, idempotency_key}` →
   `commit_session()` → Order; lifecycle dispara handlers (notificação, etc.).
4. **Status/polling**: ManyChat não tem SSE → GET status que retorna a projection
   conversacional atualizada (tracking/pagamento/ações), ou notificação outbound
   automática (já existe via lifecycle).

---

## Arcos propostos

- **Arc 1 · Ativar webhook com segurança** — registrar `contrib/manychat/urls.py`
  em `config/urls.py`; cobrir HMAC (`MANYCHAT_WEBHOOK_SECRET`) + replay por teste;
  validar `DOORMAN.ACCESS_LINK_API_KEY`. **Não mergear sem os testes de assinatura.**
- **Arc 2 · Intenção de pedido (cart)** — endpoint inbound que monta a Session a
  partir da intenção do bot, reusando `sessions.py` e a projection conversacional.
  Identidade via `ManychatSubscriberResolver` + ContactPoint WHATSAPP. Itens
  validados contra catálogo (preço/stock do Core — bot nunca decide preço, ADR-009).
- **Arc 3 · Confirmação + idempotência** — endpoint confirm → `commit_session`
  com `idempotency_key` (retry seguro); retorna Order + projection. Lifecycle já
  cuida de notificação/pagamento.
- **Arc 4 · Status + pagamento** — GET status (projection) + fluxo PIX
  (link/QR via payman) entregue na conversa; reusa adapters existentes.
- **Arc 5 · Smoke + runbook** — smoke conversacional (cruza com
  `gateways.sandbox` do go-live: ManyChat está `blocked_by_credentials`) +
  runbook (webhook falhando, pedido preso, AccessLink expirado).

## Invariantes (ADR-009)

- **ManyChat coleta intenção; o Core decide** preço/stock/disponibilidade/pagamento.
  O bot nunca reimplementa regra.
- Webhook **sempre** valida HMAC + replay. Endpoint inbound autenticado
  (`ACCESS_LINK_API_KEY`/secret).
- Reusar `commit_session`/`build_order_conversation` — não criar fluxo paralelo
  de pedido.
- Idempotência obrigatória no confirm (ret entrega dupla do bot).

## Bloqueios no Pablo

- Credenciais: `MANYCHAT_API_TOKEN`, `MANYCHAT_WEBHOOK_SECRET`,
  `DOORMAN.ACCESS_LINK_API_KEY` (hoje ausentes — o smoke de gateways marca
  ManyChat `blocked_by_credentials`).
- Desenho dos fluxos visuais no editor ManyChat (parte caixa-preta, fora do repo).
- Confirmar contrato exato do payload que o ManyChat envia (campos do flow).

## Referências

- [ADR-009 — WhatsApp via ManyChat](../decisions/adr-009-whatsapp-via-manychat.md)
- [manychat-conversation-projection.md](../reference/manychat-conversation-projection.md)
- [REMOTE-MULTISURFACE-PLAN](REMOTE-MULTISURFACE-PLAN.md) · [GO-LIVE-READINESS-PLAN](GO-LIVE-READINESS-PLAN.md)
