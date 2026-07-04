# Plano — PIN de operador autoatendimento

> Objetivo: cada operador **define/troca o próprio PIN**; o **gerente provisiona/reseta**
> com um PIN temporário + "trocar no 1º uso". Hoje o PIN só se define via `seed` (1234) ou
> `set_operator_pin` (CLI/admin) — não há autoatendimento. A base (`PinCredential`) já tem
> `set_pin`/`verify`/`set_for`/`unlock`/lockout/`validate_raw`; falta o seam + UI + 1 flag.

## Modelo de segurança (invariantes)
- **Trocar o próprio PIN:** prova o **PIN atual** (`verify`) e define o novo (policy `DOORMAN.PIN_*`).
  Gateado pela sessão de dispositivo (staff) — você troca o PIN do `request.user`.
- **Gerente reseta:** emite um **PIN temporário** para um operador e marca `must_change=True`
  (gateado por permissão de gerente). O operador é **forçado a trocar** no próximo unlock.
- **Lockout** do `PinCredential` já barra brute-force (attempts + `PIN_LOCKOUT_MINUTES`).
- Nunca revelar o PIN (só digest HMAC, já é assim). Reset só mostra o temp uma vez ao gerente.

## Backend
**doorman** (`PinCredential`):
- Novo campo `must_change: bool = False` (migração — pré-go-live, sem expand-contract).
- `set_pin()` zera `must_change` (uma troca real remove a exigência).
- `set_for(user, pin, *, must_change=False)` aceita o flag (reset do gerente passa `True`).

**backstage/api** (`/operator/...`):
- `POST /operator/pin/change` — body `{current_pin, new_pin}`. `verify(current)` no
  `PinCredential` de `request.user`; se ok, `set_pin(new_pin)`. Erros: PIN atual errado → 400;
  travado → 423/400 com copy; policy inválida → 400 com a regra.
- `POST /operator/pin/reset` — body `{username|user_id, temp_pin?}`. Gateado por permissão de
  **gerente** (ex.: `perform_closing` ou uma perm dedicada `manage_operators`). `set_for(target,
  temp, must_change=True)`; retorna o `temp` (ou um gerado) **uma vez**.
- `operator/session` (existente) passa a expor `pin_must_change` do operador ativo → o front força a troca.

## Frontend (apps operador + gestor)
- **Lock screen** (`useOperatorLock`, copiado nos 4 apps operador): affordance **"Trocar PIN"**
  → PIN atual + novo + confirmar. E, se `pin_must_change`, **força** a troca antes de liberar a tela.
- **Gestor** (opcional, WP3): tela de operadores → **"Resetar PIN"** (gera temp) para o gerente.

## WPs
- **WP1 (backend):** campo `must_change` + `set_pin`/`set_for` + 2 endpoints + `pin_must_change`
  na sessão. Testes: troca com current ok; current errado → 400; lockout; reset por gerente +
  must_change; policy (min length / só dígitos). *(test-first)*
- **WP2 (frontend — troca):** "Trocar PIN" no lock screen dos 4 apps + fluxo forçado no must_change.
- **WP3 (frontend — gerente):** reset de PIN no gestor (gera temp, mostra uma vez).

## Fora de escopo (por ora)
- Recuperação sem gerente (esqueci o PIN e não tem gerente) — decisão de produto; hoje o reset do
  gerente cobre. SMS/OTP para reset é possível depois (o doorman já faz OTP), mas é outro WP.
