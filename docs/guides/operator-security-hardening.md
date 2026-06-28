# Hardening de acesso do operador (pré-produção)

> Endurecimento de acesso às superfícies de operador (Admin Django + apps Nuxt
> de operador) antes do go-live. Cobre 2FA do admin e restrição por IP no
> ingress. Faz parte do Lote C do
> [GO-LIVE-READINESS-PLAN](../plans/GO-LIVE-READINESS-PLAN.md).

---

## 1. 2FA (TOTP) no Admin

O gate já existe e é testado (`shopman/backstage/tests/test_admin_2fa.py`, 8
testes verdes):

- `django_otp` + `otp_totp` instalados.
- [`AdminTwoFactorMiddleware`](../../shopman/backstage/middleware_2fa.py) — força
  verificação OTP em `/admin/` para usuário staff autenticado. **No-op enquanto
  `SHOPMAN_ADMIN_REQUIRE_2FA` está desligado**, para não trancar ninguém antes do
  enrollment.
- View `admin_2fa_verify` ([`views/two_factor.py`](../../shopman/backstage/views/two_factor.py)).
- Comando de enrollment `setup_admin_totp` (cria TOTPDevice confirmado + imprime
  `otpauth://` e QR ASCII).

### Procedimento de ativação (ordem importa)

A ordem é crítica: **enrolar todos antes de ligar a flag**, senão o gate tranca
quem ainda não tem device.

1. Para **cada** superuser/staff com acesso ao admin:
   ```bash
   python manage.py setup_admin_totp <username>
   # escanear o QR / colar o otpauth:// num app autenticador (Google Auth, 1Password, etc.)
   ```
   Em produção, rodar no console/release job do ambiente real (não local).
2. Confirmar que todos têm device confirmado.
3. Só então ligar o gate:
   ```
   SHOPMAN_ADMIN_REQUIRE_2FA=true
   ```
   (env do deployment — DigitalOcean App Platform / `.env` self-hosted).
4. Validar: logar no admin → deve redirecionar para `admin_2fa_verify` e exigir
   o código TOTP. Sem device confirmado + flag ligada = bloqueio (esperado).

### Recuperação (operador perdeu o device)

Outro superuser roda `setup_admin_totp <username> --force` para emitir novo
device. Se ninguém mais tem acesso, desligar a flag temporariamente via env do
deployment, reenrolar e religar.

---

## 2. IP allowlist no ingress (não no app)

**Decisão (2026-06-26): restrição por IP é responsabilidade do _ingress_, não de
um middleware app-level.** Fecha o TODO de
[`config/settings.py`](../../config/settings.py) (`# combinar com IP allowlist no
ingress do admin`).

### Por quê ingress e não middleware

Um middleware Django teria que confiar em `X-Forwarded-For` para descobrir o IP
real atrás do proxy da App Platform. `X-Forwarded-For` é forjável se a cadeia de
proxy confiáveis não for travada com exatidão — vira falsa sensação de segurança.
Filtrar antes de chegar na app é mais simples e mais robusto.

### Abordagem recomendada — Cloudflare na frente

A DigitalOcean App Platform sozinha não faz allowlist de IP por rota de forma
limpa. O caminho correto é colocar **Cloudflare** na frente dos subdomínios de
operador e restringir lá:

- **Cloudflare Access** (Zero Trust) nas zonas `admin.`, `pos.`, `kds.`,
  `gestor.`, `fournil.`: política que só libera as faixas de IP da padaria/equipe
  (e, opcionalmente, identidade Google Workspace — já em uso no domínio).
- Ou, mais simples, **WAF / IP Access Rules** do Cloudflare bloqueando tudo que
  não está na allowlist para esses hostnames.
- A loja do cliente (apex) e a `api.` que ela consome **não** entram na
  allowlist — são públicas.

### Faixas de IP

Pendente do Pablo: as faixas de IP fixas da operação (loja física, casa,
VPN da equipe). Sem IP fixo, preferir Cloudflare Access por identidade
(Google Workspace) em vez de allowlist de IP.

### Fallback honesto (só se não houver ingress configurável)

Se em algum momento não der para usar ingress, um middleware app-level é
aceitável **apenas** lendo o IP da cadeia de proxy confiável conhecida da App
Platform (nunca o `X-Forwarded-For` cru), com a lista de proxies travada. Isso é
fallback, não o alvo.

---

## Checklist de go-live (operador)

- [ ] Todos os superusers/staff com TOTP device confirmado.
- [ ] `SHOPMAN_ADMIN_REQUIRE_2FA=true` no ambiente real.
- [ ] Superusers triviais de staging (`admin/admin`) **removidos** em prod
      (prod usa `bootstrap_admin` env-driven — ver [OPERATOR-AUTH-PLAN](../plans/completed/OPERATOR-AUTH-PLAN.md)).
- [ ] Cloudflare Access/WAF restringindo `admin.`/`pos.`/`kds.`/`gestor.`/`fournil.`.
- [ ] `SESSION_COOKIE_DOMAIN` de produção configurado (auth cross-subdomínio).

---

## Referências

- [GO-LIVE-READINESS-PLAN](../plans/GO-LIVE-READINESS-PLAN.md) — Lote C
- [OPERATOR-AUTH-PLAN](../plans/completed/OPERATOR-AUTH-PLAN.md) — auth cross-subdomínio (Opção C)
- [`middleware_2fa.py`](../../shopman/backstage/middleware_2fa.py) · [`setup_admin_totp`](../../shopman/backstage/management/commands/setup_admin_totp.py)
