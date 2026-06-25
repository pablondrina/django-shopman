# OPERATOR-AUTH-PLAN — Login único + PIN/crachá para os apps de operador (Opção A)

> Fecha o gap de auth cross-subdomínio dos apps de operador (ver memória
> `project_operator_apps_crosssubdomain_auth_gap`). Decisão do Pablo: **Opção A —
> sessão Django escopada a um domínio-pai próprio da zona de operador**, reusando
> 100% auth/grupos/permissões do Django + a camada de PIN (PinCredential) que já
> existe. Constrói sobre a iniciativa [OPERATOR-APPS-PLAN](OPERATOR-APPS-PLAN.md)
> (Fases 0–4 entregues).

## Modelo (duas camadas, reusa Django)

- **Camada 1 — estação logada (sessão Django).** Operador loga **1×** no hub da zona
  de operador → cookie de sessão válido em todos os subdomínios dessa zona. Os grupos/
  permissões do Django (`operate_pos`/`operate_kds`/`operate_production`/`manage_orders`)
  decidem quem abre qual app — o gate `HasBackstagePermission` já entrega isso (403 sem
  perm, 200 com). **Nada de login por app.**
- **Camada 2 — quem opera agora (PIN/crachá).** `PinCredential` (doorman) + `set_active_
  operator` (grava na sessão). Troca de operador no turno sem re-login. **Já existe**, hoje
  fiado só no POS → generalizar pros 4 apps.

## Decisão de domínio (zona de operador isolada da loja)

A loja do cliente fica em `nelsonboulangerie.com.br` (SEO/marca). A zona de operador vai
para um **domínio registrável SEPARADO**, para o cookie de sessão ser fisicamente incapaz
de chegar à loja pública. String do domínio vive num único lugar (settings/env/spec) —
trocar depois é barato.

- **Agora (custo zero):** `boulangerie.com.br` (já à disposição; eTLD+1 distinto de
  `nelsonboulangerie.com.br`).
- **Ideal de longo prazo (opcional):** registrar `nelson.app.br` (`.app.br` = categoria de
  app no Registro.br; hosts curtos e claros). Migração futura = trocar 1 valor + DNS.

Layout (exemplo com `boulangerie.com.br`):

```
LOJA (cliente) — inalterada:
  nelsonboulangerie.com.br            Loja (Nuxt)      sessão cliente: host-only
  api.nelsonboulangerie.com.br        API/BFF

OPERADOR — zona isolada, sessão = .boulangerie.com.br:
  boulangerie.com.br                  Entrar (login 1×) + hub
  gestor.boulangerie.com.br           Pedidos          (manage_orders)
  kds.boulangerie.com.br              KDS              (operate_kds)
  pos.boulangerie.com.br              PDV              (operate_pos)
  fournil.boulangerie.com.br          Produção         (operate_production)
  api.boulangerie.com.br              alias da MESMA API (Host distinto p/ o middleware)
```

## Achados que fundamentam o plano

- **O cliente usa sessão Django** (`shop/services/auth.py` → `trusted_device_login`/
  `verify_for_login` chamam `django.contrib.auth.login`). Logo `SESSION_COOKIE_DOMAIN`
  **global** quebraria o login do cliente. → **middleware por-host é obrigatório.**
- **O proxy Nuxt reescreve o Host** para um único `api.` (NUXT_DJANGO_BASE_URL). Então o
  Django não distingue a origem pelo seu próprio Host se todos apontarem pro mesmo api. →
  a zona de operador proxia para um **alias de API próprio** (`api.boulangerie.com.br`,
  mesmo Django), e o middleware escopa o cookie só quando `request.get_host()` é o host de
  operador.
- **PIN já é Django-nativo:** `PinCredential` (OneToOne com User, HMAC, lockout) +
  `verify_operator_pin` + `set_active_operator`. Generalizar do POS é wiring, não modelo novo.
- **`HasBackstagePermission`** já implementa "tem permissão → tem acesso" por app. Zero
  código de autorização novo.

---

## WP-AUTH-1 · Escopo de cookie por host (o núcleo) · ⏳

**Backend, sem deploy ainda. Não tocar o auth do cliente.**

1. Middleware `OperatorSessionDomainMiddleware` (após `SessionMiddleware`): no response, se
   `request.get_host()` pertence à zona de operador (`settings.SHOPMAN_OPERATOR_API_HOST` ou
   sufixo `settings.SHOPMAN_OPERATOR_COOKIE_DOMAIN`), reescreve `domain` dos cookies
   `sessionid` e `csrftoken` para `settings.SHOPMAN_OPERATOR_COOKIE_DOMAIN`
   (ex.: `.boulangerie.com.br`). Caso contrário, não mexe (cliente segue host-only).
2. Settings novos (env, default vazio → comportamento atual): `SHOPMAN_OPERATOR_COOKIE_DOMAIN`,
   `SHOPMAN_OPERATOR_API_HOST`. `SESSION_COOKIE_DOMAIN` **continua não setado globalmente.**
3. `CSRF_TRUSTED_ORIGINS` += hosts de operador (`https://*.boulangerie.com.br`). `ALLOWED_HOSTS`
   += `api.boulangerie.com.br` (o proxy reescreve Host pra esse alias na zona de operador).
4. Testes: request no host de operador → cookie com `Domain=.boulangerie.com.br`; request no
   host de cliente → cookie host-only (sem domain); login do cliente intacto.
- **Aceite:** `make test` verde; cookie escopado só na zona de operador; cliente intocado.

## WP-AUTH-2 · Generalizar PIN/crachá pros 4 apps (Camada 2) · ⏳

1. Endpoint genérico `POST /api/v1/backstage/operator/unlock/` + `.../lock/` (mover a lógica
   do `POSOperatorUnlockView` para um base reusável; gate = qualquer permissão de operador).
   `set_active_operator`/`clear_active_operator`/`verify_operator_pin` já existem.
2. (Opcional) campo `badge_code` em `PinCredential` + lookup por crachá → mesmo `verify`.
   Scan de código de barras vira só outro input.
3. Composable `useOperatorLock` nas surfaces `orders-`/`kds-`/`production-uithing-nuxt`
   (POS já tem); tela de trava/destrava (PIN ou crachá) reusando o componente do POS.
4. Testes de contrato do unlock genérico (PIN válido/ inválido/ lockout).
- **Aceite:** trocar operador por PIN/crachá em qualquer app, sem re-login; vitest + API verdes.

## WP-AUTH-3 · Porta de entrada do operador + gate 403 no front · ⏳

1. **Tela "Entrar" enxuta** servida no hub da zona de operador (substitui a tela crua do
   admin Django como entrada do operador) — branda, acolhedora, pt-BR (omotenashi na porta).
   Reusa `django.contrib.auth` (login por usuário/senha; ou estender p/ PIN-first depois).
   Avaliar: página Django simples no `api.boulangerie.com.br` OU rota no app que proxia o login.
2. **Front gate:** quando a API responde 403 (sem sessão ou sem permissão), o app mostra
   "Entrar" / "Você não tem acesso a esta tela" em vez de um board vazio com erro.
3. `operatorLoginNextPath` das surfaces aponta pro hub de login da zona.
- **Aceite:** sessão expirada/sem perm → tela clara de entrada/negação; login 1× funciona.

## WP-AUTH-4 · Deploy da zona de operador + browser-QA AUTENTICADO real · ⏳

1. DNS: criar os hosts da zona de operador (`gestor./kds./pos./fournil./api.` +
   apex) no domínio escolhido, apontando pro app DO.
2. Spec DO (aditivo, preservar `EV[...]`): domínios ALIAS dos hosts de operador; ingress
   por host → componente certo; `api.<operador>` → componente `web` (Django); envs
   `NUXT_DJANGO_BASE_URL=https://api.<operador>` nos 4 apps de operador +
   `SHOPMAN_OPERATOR_COOKIE_DOMAIN`/`SHOPMAN_OPERATOR_API_HOST` no bloco global; nav do Admin
   (`SHOPMAN_*_BASE_URL`) repointado pros novos hosts.
3. **Browser-QA AUTENTICADO** (fecha a pendência original): num browser real, **um** login
   no hub → abrir `gestor./kds./pos./fournil.` (cada um servindo board com dados reais ou
   403 se sem permissão) → PIN/crachá → operar. Auditar console limpo, acessibilidade,
   omotenashi. Restaurar/ligar os checks `_orders_/_kds_/_production_check` da matriz
   omotenashi (já existem) agora que dá pra navegar autenticado.
- **Aceite:** login 1× cobre os 4 apps na zona de operador; cliente intacto; QA autenticado
  verde; zero regressão.

---

## Fora de escopo / futuro

- **Opção C (SSO por handoff/token):** guardada para o dia em que os apps precisem ser
  abertos a **terceiros fora da rede** (franquia/parceiro) — aí o handoff por token paga o
  custo. Hoje a Opção A entrega o mesmo "login 1×" com muito menos para construir.
- **2FA do Admin** (já implementado, gated OFF) e **IP allowlist (prod)** seguem como
  pendências separadas, dependentes de ação do Pablo (enrollment / ingress de prod).

## Gates por WP

`make test`, `make admin` (sem `url` antes de PR), `make lint`, `vitest` nas surfaces
tocadas, e verificação AO VIVO após deploy. Branch própria; commit por WP; mergear no `main`
antes de cada deploy. **Não tocar o auth do cliente** (storefront/doorman). String de
domínio num único lugar (settings/env/spec).
