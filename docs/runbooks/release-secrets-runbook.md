# Release secrets runbook

Este runbook fecha os bloqueios externos reportados por
`scripts/check_release_readiness.py`. Nao cole segredos em chat, issue, PR ou
arquivo versionado. Preencha-os direto no ambiente de staging/producao.

## 1. Onde colocar

Na DigitalOcean App Platform, coloque segredos como app-level environment
variables com `Encrypt` ligado. Variaveis dinamicas como `${APP_URL}` podem ser
`GENERAL`; chaves, tokens, certificados e webhooks devem ser `SECRET`.

Variaveis que desbloqueiam o readiness local:

```env
SHOPMAN_PREPROD_URL=https://staging.example.com
SHOPMAN_MANUAL_QA_EVIDENCE=/path/to/manual-qa.md
```

Use `docs/runbooks/manual-qa-evidence-template.md` como base. O arquivo so
passa no readiness quando a primeira linha estiver marcada como
`manual_qa_status: passed`.

## 2. Contato publico da loja

O storefront usa `Shop.phone` e `Shop.social_links` para projetar
`home.public_config.whatsapp_url`. Configure com o comando idempotente:

```bash
python manage.py configure_shop_contact \
  --phone 554333231997 \
  --email nelson@boulangerie.com.br
```

Ou use variaveis de ambiente e rode o mesmo comando sem argumentos:

```env
SHOPMAN_SHOP_PHONE=554333231997
SHOPMAN_SHOP_EMAIL=nelson@boulangerie.com.br
SHOPMAN_SHOP_WHATSAPP=https://wa.me/554333231997
```

```bash
python manage.py configure_shop_contact
```

Valide:

```bash
curl -s "$SHOPMAN_PREPROD_URL/api/v1/storefront/home/" \
  | python -m json.tool \
  | rg 'whatsapp_url|phone_display'
```

## 3. Core secrets

Obrigatorias para staging/producao fora de `DEBUG`:

```env
DJANGO_SECRET_KEY=<strong random secret>
DOORMAN_ACCESS_LINK_API_KEY=<strong random server-to-server key>
```

Use `python - <<'PY'` localmente para gerar valores quando o provedor nao gerar:

```bash
python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

## 4. EFI Pix

Obtenha na Conta Efi:

```env
EFI_SANDBOX=true
EFI_CLIENT_ID=<homologacao client id>
EFI_CLIENT_SECRET=<homologacao client secret>
EFI_CERTIFICATE_PATH=/app/secrets/efi-homologacao.p12
EFI_PIX_KEY=<chave pix de homologacao/producao>
EFI_WEBHOOK_TOKEN=<shared secret definido para o webhook>
EFI_MTLS_HEADER=HTTP_X_SSL_CLIENT_VERIFY
```

O certificado precisa existir no filesystem do container no caminho de
`EFI_CERTIFICATE_PATH`. Se o provedor de deploy nao monta arquivo secreto,
converta isso em etapa de build/runtime segura antes de habilitar `payment_efi`.
Nao commite `.p12`, `.pem` ou dumps base64 do certificado.

## 5. Stripe

Para sandbox, use chaves de test mode:

```env
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_CAPTURE_METHOD=manual
```

O `STRIPE_WEBHOOK_SECRET` e por endpoint e por ambiente. Nao reutilize o segredo
de endpoint live no endpoint test, nem o segredo impresso pelo Stripe CLI em
staging.

## 6. iFood

Para o contrato atual do Shopman:

```env
IFOOD_WEBHOOK_TOKEN=<shared token usado pelo endpoint legacy/local>
IFOOD_MERCHANT_ID=<merchant id de staging/producao>
```

Se a integracao migrar para o formato novo do Developer Portal com assinatura
`X-IFood-Signature`, alinhe o adapter antes de marcar o smoke como provado.

## 7. ManyChat e AccessLink

```env
MANYCHAT_API_TOKEN=<token outbound da API ManyChat>
MANYCHAT_WEBHOOK_SECRET=<segredo HMAC inbound>
MANYCHAT_OTP_FLOW_NS=<flow namespace do OTP, quando aplicavel>
MANYCHAT_SUBSCRIBER_RESOLVER=shopman.guestman.contrib.manychat.resolver.ManychatSubscriberResolver.resolve
DOORMAN_ACCESS_LINK_API_KEY=<mesmo segredo core acima>
```

Nao confunda:

- `MANYCHAT_API_TOKEN`: autentica chamadas Shopman -> ManyChat.
- `MANYCHAT_WEBHOOK_SECRET`: valida chamadas ManyChat -> Shopman.
- `DOORMAN_ACCESS_LINK_API_KEY`: autentica criacao server-to-server de access links.

## 8. Ativar gateways reais

Enquanto credenciais reais nao estiverem prontas, mantenha staging tecnico em
mock explicito:

```env
SHOPMAN_PIX_ADAPTER=shopman.shop.adapters.payment_mock
SHOPMAN_CARD_ADAPTER=shopman.shop.adapters.payment_mock
SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true
SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true
```

Depois que EFI/Stripe estiverem completos:

```env
SHOPMAN_PIX_ADAPTER=shopman.shop.adapters.payment_efi
SHOPMAN_CARD_ADAPTER=shopman.shop.adapters.payment_stripe
SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=false
```

## 9. Validar

Sem falhar por bloqueios externos:

```bash
python scripts/check_release_readiness.py
```

Falhando se qualquer credencial/evidencia externa ainda faltar:

```bash
python scripts/check_release_readiness.py --strict-external
```

Com argumentos diretos:

```bash
python scripts/check_release_readiness.py \
  --strict-external \
  --preprod-url "$SHOPMAN_PREPROD_URL" \
  --manual-qa-evidence "$SHOPMAN_MANUAL_QA_EVIDENCE"
```

Resultado esperado antes de trafego real: nenhum `failed` e nenhum
`blocked_external`. Se `manychat.ordering_webhook` aparecer como
`blocked_by_implementation`, o contrato ainda nao esta provado para pedidos
conversacionais inbound; use ManyChat apenas para OTP/access-link ate esse
smoke ser implementado.
