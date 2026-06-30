# Runbook — Ativar WhatsApp transacional (notificações de pedido)

> Liga as notificações de pedido por WhatsApp. **A engenharia está 100% pré-ligada**:
> eventos já disparam, adapters registrados, fallback texto→SMS→email funcionando. A
> configuração do flow por evento é feita **no Admin** (sem editar código nem deploy).

## Como o sistema decide o canal

`ChannelConfig.notifications`: backend primário `manychat` (WhatsApp) → fallback `sms` →
`email`. Cada evento de pedido chama `notify(event, recipient, context)`. O adapter ManyChat:
1. usa o **flow** configurado para o evento, se houver → dispara `/sending/sendFlow`;
2. senão, envia a **mensagem de texto** (campo `body` do template) → `/sending/sendContent`.

## Onde se configura: Admin → Templates de notificação

Cada evento é um `NotificationTemplate` (Admin, editável pelo lojista). Campos:
- **mensagem** (`body`) — texto enviado quando não há flow (fallback dentro da janela 24h).
- **flow do WhatsApp (ManyChat)** (`whatsapp_flow_ns`) — namespace do flow no ManyChat
  (ex.: `content20250401120000_123456`). **Preenchido → dispara o flow aprovado.**

Precedência: o `whatsapp_flow_ns` do Admin vence o `settings.MANYCHAT_FLOW_MAP` (que fica
só como fallback de bootstrap; pode permanecer vazio).

## Passos (Pablo)

1. **Submeter os templates à Meta** (Utility + 1 Authentication p/ OTP), copiando de
   [`docs/reference/whatsapp-templates-meta.md`](../reference/whatsapp-templates-meta.md).
   Aguardar aprovação (~24-48h).
2. **Criar um Flow no ManyChat** para cada template aprovado e copiar o **namespace**.
3. **No Admin → Templates de notificação**, para cada evento, colar o namespace no campo
   **flow do WhatsApp**. (Se o evento ainda não tiver template, criar um.)

Pronto — sem deploy. Mapeie só os eventos que quiser; os demais caem no texto.

## Eventos

`order_confirmed`, `order_preparing`, `order_ready_pickup`, `order_ready_delivery`,
`order_dispatched`, `order_delivered`, `order_cancelled`, `payment_requested`,
`payment_confirmed`, `payment_reminder`, `payment_expired`.

> OTP (login) **não** vai por WhatsApp (ManyChat não tem categoria Authentication) — vai
> por SMS (Comtele).

## Alternativa — Meta Cloud API direto

Adapter `notification_whatsapp` (spike, inerte até `WHATSAPP_PHONE_NUMBER_ID` +
`WHATSAPP_ACCESS_TOKEN`). Decisão ManyChat-vs-direto:
[`WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN`](../plans/WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN.md).
