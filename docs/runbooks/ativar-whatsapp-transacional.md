# Runbook — Ativar WhatsApp transacional (notificações de pedido)

> Liga as notificações de pedido por WhatsApp. **A engenharia está 100% pré-ligada**:
> eventos já disparam, adapters registrados, fallback texto→SMS→email funcionando. Só
> faltam os dados que vivem na Meta/ManyChat. Desde 2026-06-30 o mapa é **env-driven**
> (configura no DigitalOcean, sem editar código nem fazer deploy).

## Como o sistema decide o canal

`ChannelConfig.notifications`: backend primário `manychat` (WhatsApp) → fallback `sms` →
`email`. Cada evento de pedido chama `notify(event, recipient, context)`; o adapter
ManyChat usa o **flow** mapeado se houver, senão manda **texto** (dentro da janela 24h).

## Caminho A — ManyChat (canal primário hoje)

1. **Submeter os 11 templates Utility** (+ 1 Authentication p/ OTP) à Meta, copiando de
   [`docs/reference/whatsapp-templates-meta.md`](../reference/whatsapp-templates-meta.md).
   Aguardar aprovação (~24-48h).
2. **Criar um Flow no ManyChat para cada template aprovado** e capturar o **flow namespace**
   (ex.: `content20250401120000_123456`).
3. **Mapear evento → namespace** no env do DigitalOcean (App-Level Env, sem deploy):
   ```
   MANYCHAT_FLOW_MAP={"order_confirmed":"content..._1","order_preparing":"content..._2","order_ready_pickup":"content..._3","order_ready_delivery":"content..._4","order_dispatched":"content..._5","order_delivered":"content..._6","order_cancelled":"content..._7","payment_requested":"content..._8","payment_confirmed":"content..._9","payment_reminder":"content..._10","payment_expired":"content..._11"}
   ```
   JSON inválido/ausente → cai no envio de texto direto (não quebra).

## Caminho B — Meta Cloud API direto (alternativa, sem ManyChat)

Adapter `notification_whatsapp` (já implementado, inerte até credenciais). Decisão
ManyChat-vs-direto: [`WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN`](../plans/WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN.md).

```
WHATSAPP_PHONE_NUMBER_ID=<Meta Business Manager>
WHATSAPP_ACCESS_TOKEN=<Meta Business Manager>
WHATSAPP_TEMPLATES={"order_confirmed":{"name":"pedido_confirmado","body":["customer_name","order_ref","total"]}, ...}
```

## Eventos disponíveis (mapear todos ou só os que quiser)

`order_confirmed`, `order_preparing`, `order_ready_pickup`, `order_ready_delivery`,
`order_dispatched`, `order_delivered`, `order_cancelled`, `payment_requested`,
`payment_confirmed`, `payment_reminder`, `payment_expired`.

> OTP (login) **não** vai por WhatsApp (ManyChat não tem categoria Authentication) — vai
> por SMS (Comtele). Ver [`ativar-focus-nfe`](ativar-focus-nfe.md) e a frente SMS.

## O que falta (resumo — tudo do Pablo)
1. Submeter/aprovar templates na Meta.
2. Criar flows no ManyChat → pegar namespaces.
3. Setar `MANYCHAT_FLOW_MAP` (JSON) no DigitalOcean.

Nenhuma mudança de código pendente.
