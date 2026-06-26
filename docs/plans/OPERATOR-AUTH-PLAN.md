# OPERATOR-AUTH-PLAN — Login único + PIN/crachá para os apps de operador (Opção A)

> Fecha o gap de auth cross-subdomínio dos apps de operador (ver memória
> `project_operator_apps_crosssubdomain_auth_gap`). Decisão do Pablo: **Opção A —
> sessão Django escopada a um domínio-pai próprio da zona de operador**, reusando
> 100% auth/grupos/permissões do Django + a camada de PIN (PinCredential) que já
> existe. Constrói sobre a iniciativa [OPERATOR-APPS-PLAN](OPERATOR-APPS-PLAN.md)
> (Fases 0–4 entregues).

## 🟢 ESTADO ATUAL + PRÓXIMAS TAREFAS (handoff, 2026-06-26)

**OPÇÃO C ESTÁ NO AR E VERIFICADA** no staging (`*.boulangerie.com.br`). Login único
cross-subdomínio + autorização por operador ativo (PIN ou crachá) + tela de trava nas 4
surfaces, tudo deployado e verificado AO VIVO. WP-AUTH-1/2a/2b/2c ✅, WP-AUTH-4 Passo 1+2 ✅.
Domínio DO `40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`, contexto doctl `shopman-staging-deploy`.
PIN do pablo no staging = `1234`, crachá = `abcdef0123456789abcdef01` (re-setados pelo job
bootstrap-staging em todo deploy). E-mail Google Workspace migrado p/ o DO sem queda.

**PRÓXIMAS TAREFAS (ordem):**
1. **Verificar o fix do botão de login** (deploy `9238c2bc`, build-env `NUXT_PUBLIC_DJANGO_
   BASE_URL=https://api.boulangerie.com.br` nos 4 apps de operador). Quando ACTIVE: navegar
   `pos.boulangerie.com.br` (sem logar), clicar "Entrar no gestor" → deve ir p/
   `api.boulangerie.com.br/admin/login/` (não mais `127.0.0.1:8000`). Conferir idem nas
   outras surfaces (overlay OperatorLogin → botão Entrar). **Bug tinha 2 camadas:** link
   relativo (corrigido) + URL pública não-bakeada no client (RUN_TIME não existe no build →
   corrigido com env de build).
2. **Pendência #2 — remover hosts nelson de operador defuntos** (`gestor./kds./pos./
   fournil.staging.nelsonboulangerie.com.br`). Transform pronto: `/tmp/remove_nelson_operator.py`
   (re-fetch spec → roda → `apps update`). PRESERVA loja (apex/api/admin nelson) + hosts
   boulangerie + EV[...]. É spec-edit + deploy.
3. **Pendência #4 — QA visual da tela de trava** (precisa do Pablo): Pablo loga no browser
   conectado via o botão "Entrar" (eu não posso digitar senha) → eu navego + screenshot do
   overlay de PIN/crachá. Chip spawnado.
4. **Pendência #3 — browser-QA omotenashi autenticado dos apps de operador** (follow-up
   maior): a matriz já tem os checks (`operator_links` + `_orders/_kds/_production_check`);
   falta o gate navegar autenticado (infra: subir os apps + sessão no headless).
5. **Limpeza futura:** nav do Admin já aponta boulangerie; remover refs a NUXT_POS_LOGIN_NEXT_PATH
   se sobrarem; avaliar hub "Entrar" dedicado (em vez de cair no /admin/).

**Gotchas de deploy:** AUTODEPLOY OFF; `apps update --spec --update-sources` p/ mudança de
spec, `apps create-deployment` p/ só rebuildar o main; preservar os 12 secrets `EV[...]`;
cert TLS de host novo provisiona assíncrono (000 no resolver público por negative-cache —
testar via `curl --resolve <host>:443:<app-ip>`).

---

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

**Domínio escolhido (Pablo, 2026-06-25): `boulangerie.com.br`** (já registrado; eTLD+1
distinto de `nelsonboulangerie.com.br` → isolamento físico do cookie). **Sem infixo
`staging`** — é um domínio novo, dedicado a operador, zero clientes; quando produção chegar,
usa-se outro domínio (ex.: `nelson.app.br`) ou move-se, barato (host = 1 valor no spec/env).
Zona DNS já criada no DigitalOcean; falta só delegar os NS no Registro.br (ação do Pablo).

Layout:

```
LOJA (cliente) — inalterada:
  nelsonboulangerie.com.br            Loja (Nuxt)      sessão cliente: host-only
  api.staging.nelsonboulangerie.com.br  API/BFF (atual)

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

## Modelo de autorização — Opção C (Pablo, 2026-06-25)

**Tudo compartilhado; as permissões são forçadas por operador via PIN/crachá.** O device
tem uma sessão Django (confiança de estação, login 1× na zona de operador). O **operador
ativo** — estabelecido por PIN ou crachá — é a identidade contra a qual a **autorização de
cada ação** é checada e a quem a ação é atribuída. Sem operador ativo (travado) → ações
bloqueadas. O crachá é um token de POSSE (código de barras), alternativa ao PIN.

## WP-AUTH-1 · Escopo de cookie por host (o núcleo da sessão) · ✅ CONCLUÍDO

> Feito (commit `ac7af659`, merge no main): `OperatorSessionDomainMiddleware` reescreve o
> Domain de sessionid/csrftoken p/ `SHOPMAN_OPERATOR_COOKIE_DOMAIN` só no host de operador;
> feature-gated (vazio=no-op); cliente intocado (achado: o cliente TAMBÉM usa sessão Django).
> 5 testes; storefront-auth 18 + 2FA 8 + framework verdes.

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

## WP-AUTH-2 · PIN/crachá + autorização pelo operador ativo (Opção C)

### WP-AUTH-2a · Crachá + resolução de operador genérica · ✅ CONCLUÍDO

> Feito (commit, branch `feat/operator-auth`): `PinCredential.badge_hash` (doorman; HMAC,
> único; `issue_badge`/`resolve_by_badge`; migração `0003`) — crachá como alternativa de
> posse ao PIN. `operator.py`: `resolve_operator_by_badge` + `verify_operator_pin`/
> `eligible_operators` parametrizados por permissão (default `operate_pos` preservado;
> `perm=None`=identidade-só). Session key → `active_operator`. operator-pin 17 + doorman 266.

### WP-AUTH-2b · Autorizar ações contra o operador ativo (gated) · ✅ CONCLUÍDO

> Feito (commits `31420454` etc., main): gate + endpoints + atribuição, gated por
> `SHOPMAN_REQUIRE_ACTIVE_OPERATOR` (default OFF). **Gate** (`HasBackstagePermission`):
> flag ON → checa a perm contra o operador ativo (não a sessão do device), 403 travado/
> sem-acesso, guarda `request.active_operator_user`; 6 testes blindando o no-bypass.
> **Endpoints** `operator/session|eligible|unlock|lock/` (gated só pela sessão do device;
> unlock por PIN ou crachá; perm-whitelist restringe quem destrava); `_actor`/`_username`
> usam o operador ativo. 5 testes de contrato incl. fluxo ponta-a-ponta. backstage 564 +
> make admin 247 + lint verdes. Follow-up: migrar o surface do POS dos endpoints
> `pos/operator/*` p/ os genéricos (no WP-AUTH-2c).

1. `HasBackstagePermission` ganha o ramo Opção C (flag ON): exige sessão staff (device) +
   **operador ativo** na sessão; carrega o User do operador e checa `required_permission`
   contra ELE (não o usuário da sessão); guarda `request.active_operator_user`. Sem operador
   → 403 `operator_locked`; sem permissão → 403 `operator_forbidden`. Flag OFF → ramo atual.
2. Endpoints genéricos (gated só pela sessão do device, NÃO pelo operador ativo — senão
   chicken-egg): `GET operator/session/` (estado: device, travado?, operador, flag),
   `GET operator/eligible/` (lista p/ o seletor, filtrada pela perm da surface),
   `POST operator/unlock/` (`{operator_id, pin}` OU `{badge}` → `set_active_operator`),
   `POST operator/lock/`. Migrar `POSOperator*` para reusar a base (zero-residuals).
3. Actor/atribuição: `_actor`/`_production_actor`/`_actor_pos` usam `active_operator_user`
   quando presente.
4. Testes: sem sessão→403; sessão sem operador→403 locked; operador sem perm→403 forbidden;
   operador com perm→200 + atribuição correta; unlock por PIN e por crachá; flag OFF=atual.
- **Aceite:** `make test`/`make admin`/lint verdes; flag OFF não muda nada; flag ON força a
  permissão pelo operador ativo; sem brecha.

### WP-AUTH-2c · Tela de trava/destrava (PIN + crachá) nos 4 apps · ✅ CONCLUÍDO

> Feito: `OperatorLock.vue` + `useOperatorLock` + `presentation/operatorLock.ts` (puro,
> testado) em production + orders + kds (perm por surface; no KDS o overlay pula o board
> público `/retirada`); montado no `app.vue` (gated → só aparece quando `locked`). **POS
> migrado** dos endpoints `pos/operator/*` p/ os genéricos (perm=operate_pos); views/rotas
> POS-específicas removidas (zero-residual); lock screen/auto-lock do POS preservados.
> `set_operator_pin` ganhou `--badge`. vitest production 24 / orders 20 / kds 21 / POS 67 +
> backstage 565 + builds verdes. Verificado gated-OFF ao vivo (overlay invisível).

1. Composable `useOperatorLock` nas surfaces `orders-`/`kds-`/`production-uithing-nuxt`
   (POS já tem) consumindo os endpoints de 2b; tela de destrava com teclado de PIN +
   leitura de crachá (scanner = entrada de texto que termina em Enter); trava por inatividade.
2. 403 `operator_locked` → mostra a tela de destrava; `operator_forbidden` → "sem acesso".
- **Aceite:** destravar por PIN ou crachá em qualquer app; trava por idle; vitest verde.

## WP-AUTH-3 · Porta de entrada do operador + gate 403 no front · ⏳

1. **Tela "Entrar" enxuta** servida no hub da zona de operador (substitui a tela crua do
   admin Django como entrada do operador) — branda, acolhedora, pt-BR (omotenashi na porta).
   Reusa `django.contrib.auth` (login por usuário/senha; ou estender p/ PIN-first depois).
   Avaliar: página Django simples no `api.boulangerie.com.br` OU rota no app que proxia o login.
2. **Front gate:** quando a API responde 403 (sem sessão ou sem permissão), o app mostra
   "Entrar" / "Você não tem acesso a esta tela" em vez de um board vazio com erro.
3. `operatorLoginNextPath` das surfaces aponta pro hub de login da zona.
- **Aceite:** sessão expirada/sem perm → tela clara de entrada/negação; login 1× funciona.

## WP-AUTH-4 · Deploy da zona de operador + browser-QA AUTENTICADO real

### Passo 1 · Login único (cookie-scoping) · ✅ DEPLOYADO + VERIFICADO AO VIVO (2026-06-26)

> Deploy `d620e5ed`: zona `boulangerie.com.br` (hosts gestor./kds./pos./fournil./api. ALIAS
> + ingress), apps repontados p/ proxiar `api.boulangerie.com.br`, `SHOPMAN_OPERATOR_COOKIE_
> DOMAIN=.boulangerie.com.br` + `SHOPMAN_OPERATOR_API_HOST` + ALLOWED_HOSTS/CSRF + nav.
> **REQUIRE_ACTIVE_OPERATOR OFF.** **Verificado:** login em `api.boulangerie.com.br/admin` →
> cookie `Domain=.boulangerie.com.br` → autentica em fournil/gestor (200) — **login único
> cross-subdomínio**. E-mail (MX/SPF/DKIM/DMARC pré-migrados no DO; DMARC corrigido) intacto,
> sem queda. Cliente (api.staging.nelson) host-only, intacto. **GAP ORIGINAL FECHADO.**

### Passo 2 · Opção C ao vivo (require-operator) + QA · ⏳ EM EXECUÇÃO

> `SHOPMAN_REQUIRE_ACTIVE_OPERATOR=true` + bootstrap setando PIN `1234` + crachá
> `abcdef0123456789abcdef01` p/ pablo (sem lockout — pablo sempre destrava). Unlock por PIN
> verificado ao vivo (flag OFF) via proxy → 200. Falta: verificar o fluxo gated (travado→
> PIN/crachá→ação→lock) + browser-QA da tela de trava após o flag-flip deploy.

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
