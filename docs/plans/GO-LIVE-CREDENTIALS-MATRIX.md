# GO-LIVE-CREDENTIALS-MATRIX — Credenciais e webhooks por fase de lançamento

> Referência operacional de **qual credencial/segredo precisa estar viva em cada fase**
> do lançamento progressivo da Nelson, e **o que flipa de sandbox para produção** em
> cada salto. Complementa — não duplica — o [GO-LIVE-READINESS-PLAN](GO-LIVE-READINESS-PLAN.md)
> (que cobre os 7 critérios, migrations e runbooks) e o checklist de bloqueios do Pablo.
>
> **Última auditoria de código**: 2026-06-29. As integrações têm **adapter + webhook reais
> e um gate de boot** (`SHOPMAN_E001..E010` em [`shopman/shop/checks.py`](../../shopman/shop/checks.py))
> que recusa subir em produção sem as credenciais. O que falta é majoritariamente **obter e
> plugar as credenciais**, não escrever código.

---

## 1. Modelo de fases (decisão Pablo, 2026-06-29)

| Fase | Público | Pedido vale? | Dinheiro real? | Nota fiscal? |
|---|---|---|---|---|
| **staging** | funcionários + família | ❌ teste | ❌ sandbox | ❌ homologação |
| **alpha** | amigos convidados (cupom ~50%) | ✅ **real** | ✅ **real** | ✅ **real** |
| **beta** | ~10 clientes próximos (cupom ~30%) | ✅ real | ✅ real | ✅ real |
| **soft** | público discreto, ~1 mês | ✅ real | ✅ real | ✅ real |
| **oficial** | lançamento marcado | ✅ real | ✅ real | ✅ real |

> ⚠️ **O verdadeiro go-live técnico é staging → alpha.** É o único salto em que sandbox vira
> produção em pagamento **e** fiscal **e** estorno ao mesmo tempo. Beta/soft/oficial são
> ganho de volume sobre a mesma configuração de produção do alpha. Trate o alpha como
> "tudo de verdade pela primeira vez".

---

## 2. Matriz de credenciais por integração × fase

Legenda: `sandbox` = chave de teste · `LIVE` = chave de produção · `—` = não precisa nesta fase
· `✅` = igual à fase anterior.

| Integração | Variáveis | staging | alpha → oficial |
|---|---|---|---|
| **Django core** | `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | secrets de staging | **LIVE** (domínio prod) |
| **DB / cache** | `DATABASE_URL` (Postgres), `REDIS_URL` | staging | **LIVE** (prod gerenciado) |
| **Domínio/cookie** | `SHOPMAN_DOMAIN`, `SHOPMAN_OPERATOR_COOKIE_DOMAIN`, `AUTH_DEFAULT_DOMAIN` | zona staging | **zona prod** (`.boulangerie.com.br`) |
| **Admin** | `SHOPMAN_ADMIN_USERNAME/EMAIL/PASSWORD`, `SHOPMAN_ADMIN_REQUIRE_2FA` | bootstrap (2FA opcional) | **bootstrap + 2FA on** |
| **Stripe** (cartão) | `STRIPE_PUBLISHABLE_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | `pk_test_`/`sk_test_` | **`pk_live_`/`sk_live_`** + webhook secret de prod |
| **Efi** (PIX) | `EFI_CLIENT_ID/SECRET`, `EFI_CERTIFICATE_*`, `EFI_PIX_KEY`, `EFI_WEBHOOK_TOKEN`, `EFI_SANDBOX` | `EFI_SANDBOX=true` | **`EFI_SANDBOX=false`** + cert + PIX key de prod |
| **Focus NFe** (fiscal) | `SHOPMAN_FISCAL_ADAPTER`, `FOCUS_NFE_TOKEN`, `FOCUS_NFE_ENVIRONMENT`, `FOCUS_NFE_CNPJ_EMITENTE`, série/CFOP | `homologacao` | **`producao`** + token prod + **validação do contador** |
| **ManyChat** (WhatsApp) | `MANYCHAT_API_TOKEN`, `MANYCHAT_WEBHOOK_SECRET`, `MANYCHAT_OTP_FLOW_NS` | conta teste | **conta LIVE** |
| **iFood** (se canal ativo) | `IFOOD_WEBHOOK_TOKEN`, `IFOOD_MERCHANT_ID`, (catálogo: `IFOOD_CATALOG_API_*`) | sandbox | **LIVE** merchant |
| **Doorman** (magic links) | `DOORMAN_ACCESS_LINK_API_KEY` | staging | **LIVE** |
| **Email** (fallback OTP) | `EMAIL_HOST/PORT/USER/PASSWORD`, `DEFAULT_FROM_EMAIL` | SMTP staging | **SMTP prod** |
| **Maps** (UI endereço) | `GOOGLE_MAPS_API_KEY` | opcional | LIVE (restrita por domínio) |

Inventário completo de variáveis comentadas: [`.env.example`](../../.env.example).

### Toggles sandbox → produção (o que muda no salto staging → alpha)

| Toggle | Sandbox | Produção |
|---|---|---|
| `SHOPMAN_ENVIRONMENT` | `staging` | `production` |
| `DJANGO_DEBUG` | `false` (staging já é não-DEBUG) | `false` |
| `EFI_SANDBOX` | `true` (host `pix-h.api.efipay`) | `false` (host `pix.api.efipay`) |
| Chave Stripe | prefixo `_test_` | prefixo `_live_` |
| `FOCUS_NFE_ENVIRONMENT` | `homologacao` | `producao` |
| `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS` | `true` só se sem sandbox real | **ausente** (mock = erro `SHOPMAN_E003`) |
| `SHOPMAN_EXPOSE_DEBUG_OTP` | permitido em staging (`W007`) | **ausente** (erro `E010`) |

O gate de boot recusa produção com chave de teste de pagamento faltando (`SHOPMAN_E009`),
webhook sem token (`E004`), ManyChat sem segredo (`E005`), Redis ausente (`E006`),
SQLite (`E007`), access-link sem chave (`E008`).

---

## 3. Gate de prontidão do **alpha** (o salto que importa)

Antes de convidar o primeiro amigo do alpha, **todos** os itens abaixo verdes:

1. **Pagamento LIVE exercido por você** ("canário de um"): faça 1–2 compras reais (PIX e
   cartão) ponta-a-ponta com chaves de produção, antes de qualquer convidado.
2. **Nota fiscal real saindo**: Focus NFe em `producao`, NFC-e emitida na compra-canário.
   **NCM/CFOP/CSOSN/PIS-COFINS já validados pelo contador ✅** (parametrização aplicada:
   CFOP 5102/5405, CSOSN 102/500, PIS-COFINS 99 — ver `docs/reference/fiscal-parametrizacao-nfce.md`).
   Resta só plugar o token Focus de produção. Não receber dinheiro real sem nota.
3. **Estorno LIVE testado**: estorne a compra-canário (Stripe refund **e** devolução PIX Efi).
   O caminho já é código pronto e testado em sandbox (`_settle_cancelled_payment` no
   [`lifecycle.py`](../../shopman/shop/lifecycle.py); `payment_stripe.refund` / `payment_efi.refund`)
   — falta exercê-lo com gateway de produção uma vez.
4. **Cupom como kill-switch**: o incentivo (~50%) é um **Coupon** desligável num clique, nunca
   preço editado no catálogo. Verificar que a NFC-e sai sobre o **valor com desconto**.
5. **Alerta de erro ligado**: observabilidade (Sentry ou equivalente) antes do alpha — com
   cliente real, você descobre bug pela tela, não pela reclamação no WhatsApp.
6. **`make release-readiness-strict` verde** (sem `blocked_external`) + `manage.py check --deploy`
   limpo com os secrets de produção.

**Critério de saída do alpha** (para liberar beta): N pedidos completam ponta-a-ponta com
nota emitida, ≥1 estorno real executado com sucesso, e zero bug P0 aberto.

---

## 4. Estado de cada frente (auditoria 2026-06-29)

| Frente | Estado no código | Falta |
|---|---|---|
| **Estorno (Stripe + Efi PIX)** | ✅ completo + testado, no lifecycle de cancelamento | só **verificar** 1× com gateway LIVE (item 3 do gate alpha) |
| **Webhook ManyChat (subscriber sync)** | ✅ **registrado** em `/api/webhooks/manychat/webhook/` (HMAC+replay, fail-closed) — 2026-06-29 | credenciais |
| **Pedido inbound por WhatsApp (conversacional)** | 🔴 endpoints intent/confirm faltam | **feature** — owner: [MANYCHAT-CONVERSACIONAL-PLAN](MANYCHAT-CONVERSACIONAL-PLAN.md) (Arc 2/3) |
| **bootstrap_admin env-driven** | ✅ existe ([`bootstrap_admin.py`](../../shopman/shop/management/commands/bootstrap_admin.py)), rejeita senha fraca, desativa seed admin | rodar com secrets prod |
| **`.env.example`** | ✅ drift de credenciais corrigido (2026-06-29) | — |
| **TaOn / Taxi Machine (logística externa)** | ❌ **não existe no código** | **decisão de escopo** — ver §5 |

---

## 5. Logística externa (TaOn / Taxi Machine) — plano separado

Decisão Pablo (2026-06-29): **planejar o adapter, construir depois**; entregar **já** o stopgap
"teleporte". Detalhe em [DELIVERY-EXTERNAL-LOGISTICS-PLAN](DELIVERY-EXTERNAL-LOGISTICS-PLAN.md).

- **Teleporte (clipboard) ✅ entregue 2026-06-29**: `manage.py teleporte ORDER-REF` copia o
  endereço estruturado do pedido para a área de transferência (o serviço não tem API; despacho
  manual sem erro de digitação). Auto-fill do form continua **bloqueado em URL/campos** (Pablo).
- **Adapter de logística**: desenhado (directive `dispatch.request` + `CourierBackend` swappable +
  webhook de status), **não construído** — só com API real. Credenciais entram nesta matriz quando
  existirem.

---

## 6. Definição de pronto

Cada fase está pronta quando suas credenciais (§2) estão plugadas, o gate de boot sobe limpo,
e — para alpha em diante — o gate de prontidão do alpha (§3) está integralmente verde.

## Referências

- [GO-LIVE-READINESS-PLAN](GO-LIVE-READINESS-PLAN.md) — 7 critérios, migrations, runbooks, bloqueios do Pablo
- [`.env.example`](../../.env.example) — inventário de todas as variáveis
- [`shopman/shop/checks.py`](../../shopman/shop/checks.py) — gate de boot `SHOPMAN_E001..E010`
- [`scripts/check_release_readiness.py`](../../scripts/check_release_readiness.py) + [`gateway_smoke.py`](../../shopman/backstage/services/gateway_smoke.py) — smoke/readiness
- [MANYCHAT-CONVERSACIONAL-PLAN](MANYCHAT-CONVERSACIONAL-PLAN.md) — canal de pedido inbound (Arc 2/3)
