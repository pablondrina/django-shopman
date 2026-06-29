# Runbook — Pré-flight de go-live (switches a virar antes do alpha/produção)

> Checklist concreto de "o que lembrar antes de virar a chave", consolidado durante a frente
> de credenciais (2026-06-29). Complementa o [GO-LIVE-READINESS-PLAN](../plans/GO-LIVE-READINESS-PLAN.md)
> (critérios/migrations) e a [GO-LIVE-CREDENTIALS-MATRIX](../plans/GO-LIVE-CREDENTIALS-MATRIX.md)
> (credenciais por fase + gate do alpha §3).
>
> ⚠️ Antes de checar env do staging, ler o estado real: `doctl --context shopman-staging-deploy
> apps spec get 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`.

## Estado verificado (2026-06-29)
Staging já tem **Stripe + Efi (sandbox) + ManyChat + iFood(token) + Doorman** setados e **provados ao
vivo** (cobrança PIX real ATIVA; Checkout Session Stripe real; 5/5 contratos internos; webhooks
fail-closed). Adapters reais, `DJANGO_DEBUG=false`. **Único gap de pagamento/fiscal: Focus NFe.**

## A virar ANTES DO ALPHA (pagamento real)

- [ ] **Focus NFe ligada** — `SHOPMAN_FISCAL_ADAPTER` + `FOCUS_NFE_TOKEN` (homolog→**producao**) +
      `FOCUS_NFE_ENVIRONMENT=producao`. CNPJ vem de `Shop.document` (Admin). Ver
      [ativar-focus-nfe](ativar-focus-nfe.md). *(contador OK; falta conta+token)*
- [ ] **Chaves LIVE de pagamento** (não cola no chat — env DO encriptado):
      Stripe `pk_live_`/`sk_live_` + webhook secret de prod · Efi `EFI_SANDBOX=false` + cert/creds prod.
- [ ] **Remover `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS`** do env DO (hoje `=true`; vira warning W006).
- [ ] **Confirmar `Shop.document` (CNPJ) preenchido** no ambiente real (emitente da NFC-e).
- [ ] **Decidir `STRIPE_CAPTURE_METHOD`** — staging usa `automatic`; `.env` local usa `manual`. Alinhar.
- [ ] **Apagar endpoint Stripe morto** (`we_1Sv6lG…`, ngrok antigo) — limpeza, não bloqueia.
- [ ] **Canário-de-um**: Pablo faz 1–2 compras reais (PIX+cartão) com NFC-e saindo + 1 estorno,
      ANTES de convidar qualquer amigo do alpha.
- [ ] **Alerta de erro** (Sentry ou equiv.) ligado antes do alpha.
- [ ] **Cupom de incentivo** (~50% alpha / ~30% beta) como **Coupon desligável** (kill-switch),
      nunca preço no catálogo. Conferir NFC-e sobre o valor com desconto.
- [ ] **Deploy do código novo** desta frente (webhook ManyChat registrado, teleporte, docs) — está
      em working tree, **não pushado/deployado**.

## A virar ANTES DE PRODUÇÃO/OFICIAL (hardening — Lote C + WP-GAP-07)

- [ ] **2FA**: `SHOPMAN_ADMIN_REQUIRE_2FA=true` + enrollar operadores (`setup_admin_totp`).
- [ ] **IP allowlist** no ingress (Cloudflare/WAF) — faixas de IP do Pablo.
- [ ] **`bootstrap_admin`** rodado com secrets de prod (matar `admin/admin`).
- [ ] **Domínio/cookie de prod**: `SHOPMAN_DOMAIN` / `SHOPMAN_OPERATOR_COOKIE_DOMAIN` / `AUTH_DEFAULT_DOMAIN`.
- [ ] **WP-GAP-07**: squash/reset final de migrations + `git tag go-live-v1` + rollback testado em staging.
- [ ] **iFood** (se canal ativar no v1): `IFOOD_MERCHANT_ID` + `IFOOD_CATALOG_*`.

## Deferido (sessão separada)
- **Pedido inbound por WhatsApp** (ManyChat conversacional, Arc 2/3) — [MANYCHAT-CONVERSACIONAL-PLAN](../plans/MANYCHAT-CONVERSACIONAL-PLAN.md).
- **TaOn auto-fill** do teleporte — bloqueado em URL/campos do serviço.

## Referências
- [GO-LIVE-CREDENTIALS-MATRIX](../plans/GO-LIVE-CREDENTIALS-MATRIX.md) · [GO-LIVE-READINESS-PLAN](../plans/GO-LIVE-READINESS-PLAN.md)
- [ativar-focus-nfe](ativar-focus-nfe.md) · [rollback-de-deploy](rollback-de-deploy.md)
