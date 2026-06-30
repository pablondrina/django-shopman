# STATUS — Go-live credenciais / WhatsApp / SMS-OTP (retomada)

> Onde parei (2026-06-30) e os passos EXATOS pra concluir. Frente isolada no worktree
> `.claude/worktrees/go-live-sms` (branch `feat/go-live-sms-whatsapp`, venv próprio).
> ⚠️ A pasta principal do repo fica sendo trocada de branch por outro agente — **trabalhar
> só neste worktree**. Detalhe vivo na memória `feedback_whatsapp_via_manychat`.

## ✅ Pronto e commitado (código testado, Core intocado)
- **Pagamentos staging**: Stripe + Efi sandbox **verificados ao vivo** (PIX cob real + Stripe
  Checkout real); webhooks fail-closed; reconciliações resolvidas. Endpoint Stripe morto apagado.
- **SMS OTP**: adapters `otp_sms_comtele` (ativo) + `otp_sms_twilio` (fallback) + `_sms` helpers;
  cadeia OTP `["sms","email"]`. 8 testes.
- **WhatsApp transacional**: adapter Meta-direto (spike) + **pacote de 12 templates Meta**
  blindado p/ aprovação → `docs/reference/whatsapp-templates-meta.md`.
- **Teleporte** (despacho manual TaOn): `manage.py teleporte` + serviço + testes.
- **Docs**: GO-LIVE-CREDENTIALS-MATRIX, go-live-preflight, ativar-focus-nfe,
  DELIVERY-EXTERNAL-LOGISTICS-PLAN, WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN.
- `.env.example` sincronizado (admin, domínios, cert EFI, iFood, Maps, email, SMS).

## ⛔ Pendências (com passos de retomada)

### 1. SMS OTP — bloqueado na Comtele (401)
- Chave `1bf12b60-0fa9-433b-a294-932266ca27bb` já no `.env` do worktree. Telefone teste: `5543984049009`.
- Comtele devolve **HTTP 401 "chave inválida / não pode efetuar requisição à API"** — provado via
  adapter E `curl` (header `auth-key` exato) → é **acesso à API/chave na Comtele, NÃO nosso código**.
- **Pablo resolve com a Comtele**: confirmar a chave em *API → Chave de API*, ou abrir ticket
  "habilitar acesso à API REST `/api/v2/send`". Validar com:
  ```bash
  curl -s -X POST https://sms.comtele.com.br/api/v2/send \
    -H 'auth-key: SUA_CHAVE' -H 'content-type: application/json' \
    -d '{"Receivers":"5543984049009","Content":"teste 482913"}'
  ```
- **Quando `"Success":true`** → re-disparar daqui (1 comando, no worktree):
  ```bash
  cd .claude/worktrees/go-live-sms && .venv/bin/python -c "import django,os;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');django.setup();from shopman.shop.adapters.otp_sms_comtele import ComteleSMSSender;print(ComteleSMSSender().send_code('5543984049009','482913','sms'))"
  ```

### 2. WhatsApp — notificações de pedido (não bloqueado pela Comtele)
- Os 11 templates **Utility** são suportados no ManyChat. Pablo: criar + submeter à Meta
  (copiar de `docs/reference/whatsapp-templates-meta.md`) → criar Flows → me passar os **flow
  namespaces** → eu preencho `MANYCHAT_FLOW_MAP`.
- ⚠️ OTP (Authentication) **NÃO** dá no ManyChat (só Marketing/Utility) — por isso OTP vai por SMS.

### 3. Focus NFe (fiscal) — bloqueado no Pablo
- Reativar conta Focus → pegar **token de homologação** → me passar (CNPJ vem de `Shop.document`).
  Contador OK; params aplicados. Runbook: `docs/runbooks/ativar-focus-nfe.md`.

### 4. Antes do alpha (gate)
- Ver `docs/runbooks/go-live-preflight.md`: chaves LIVE, remover `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS`,
  **canário-de-um** (Pablo faz 1 compra real PIX+cartão + nota + 1 estorno antes de convidar amigos),
  Sentry, cupom kill-switch, deploy do código novo.

## 🔀 Reconciliar branches (Pablo)
Trabalho de go-live duplicado, **conteúdo idêntico**: `main` (`7e4ff29f`, merge desta sessão) e
`feat/go-live-sms-whatsapp` (`c5dccb52`, worktree). Decidir qual mantém; casam sem conflito.

## ⏭️ Adiado (sessão separada)
- Pedido inbound por WhatsApp (ManyChat conversacional, Arc 2/3).
- Auto-fill do teleporte (URL/campos do TaOn).
