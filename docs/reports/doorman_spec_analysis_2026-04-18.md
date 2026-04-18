# Doorman - analise critica orientada a SPEC

Escopo estrito: `packages/doorman/shopman/doorman`

Metodo: leitura do codigo do pacote, dos testes do proprio pacote e das dependencias estritamente necessarias para entender contratos publicos e transicoes. Esta analise nao executa a suite; ela extrai a spec percebida do codigo e aponta drift entre promessa e implementacao.

## Leitura executiva

`doorman` nao e um "helper de login". Ele ja e um sub-sistema de autenticacao com:

- OTP por telefone/email.
- magic links / access links.
- trusted device para skip-OTP.
- bridge para `django.contrib.auth.User`.
- middleware para `request.customer`.
- API JSON e views HTML.
- sender abstraction e adapter abstraction.

O desenho e bom na intencao: tokens e codigos sao armazenados como HMAC, ha rate limit, cooldown, cookie HttpOnly para device trust, safe redirect, e um boundary de `AuthCustomerInfo` via protocolo. Isso e acima da media para um projeto novo.

O problema central e que o pacote promete agnosticidade, core enxuto e separacao de responsabilidades, mas ainda carrega dependencias fortes e alguns contratos "mentidos" pelo proprio codigo: o OTP login chama AccessLink internamente so para reaproveitar o fluxo de session/login; a camada de erro perde granularidade; a protecao concorrente e boa em intencao mas ainda nao e forte o bastante; e a UI/UX ainda e funcional, nao omotenashi-first nem WhatsApp-first de verdade.

## Specs extraidas por entidade

### `AccessLink`

Arquivo-chave: [`packages/doorman/shopman/doorman/models/access_link.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/models/access_link.py:46>)

- Token de troca web vindo de chat, email ou API.
- O banco nunca guarda plaintext; guarda `token_hash` HMAC-SHA256.
- O bruto so existe no momento da criacao e deve ser entregue ao cliente uma unica vez.
- O lifecycle e `created_at`, `expires_at`, `used_at`.
- `audience` limita escopo: `web_checkout`, `web_account`, `web_support`, `web_general`.
- `source` identifica a origem: `manychat`, `internal`, `api`.
- `user` e o resultado da troca com session Django.
- `is_valid` significa "nao usado e nao expirado".
- `mark_used(user)` escreve `used_at` e `user`.
- `get_by_token(raw)` consulta por HMAC, nunca por plaintext.

Contrato implicito:

- Um access link deveria ser single-use, mas `Gates.access_link_validity()` permite reuso por `60s` para tolerar prefetch de browser. Isso e uma escolha de UX, mas reduz a dureza do single-use sob ataque/replay.

### `VerificationCode`

Arquivo-chave: [`packages/doorman/shopman/doorman/models/verification_code.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/models/verification_code.py:64>)

- OTP de 6 digitos, sempre armazenado como HMAC.
- `target_value` e o endereco de login, aceitando telefone E.164 ou email.
- `purpose` separa `login` de `verify_contact`.
- `status` percorre `pending`, `sent`, `verified`, `expired`, `failed`.
- `delivery_method` pode ser `whatsapp`, `sms`, `email`.
- `attempts` e `max_attempts` limitam brute force.
- `verify(raw_code)` e o entrypoint canonico: checa validade e HMAC em conjunto.
- `record_attempt()` faz incremento atomico por `F()`.
- `mark_sent()`, `mark_verified(customer_id)`, `mark_expired()` fecham o ciclo.

Nuance importante:

- `code_hash` tem default `generate_code()`, mas esse helper devolve apenas o digest, nao o raw code. Para fluxo real, o pacote usa `generate_raw_code()` manualmente no service. Isso e um contrato confuso para integradores.

### `TrustedDevice`

Arquivo-chave: [`packages/doorman/shopman/doorman/models/device_trust.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/models/device_trust.py:44>)

- Dispositivo confiavel e um token aleatorio guardado como HMAC.
- Cookie bruto vive no browser como HttpOnly.
- TTL default de 30 dias.
- Pode ser revogado individualmente ou por cliente.
- `label` e derivado do user-agent para melhorar UX.
- `verify_token(raw)` retorna o device e atualiza `last_used_at`.
- `cleanup_expired(days)` remove registros antigos.

Leitura funcional:

- Esse modelo e consistente com um skip-OTP pragmatico. Falta, porem, um binding mais forte ao contexto de risco, porque o token do cookie sozinho e suficiente para trust.

### `CustomerUser`

Arquivo-chave: [`packages/doorman/shopman/doorman/models/customer_user.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/models/customer_user.py:10>)

- E o bridge 1:1 entre `User` do Django e `customer_id` externo.
- O relacionamento e desacoplado por UUID, nao por FK.
- `metadata` existe como suporte operacional.
- `get_customer()` resolve via resolver configurado.

Contrato real:

- O `User` Django aqui e mecanismo de sessao, nao a entidade de negocio.

### `AuthCustomerInfo` e `CustomerResolver`

Arquivo-chave: [`packages/doorman/shopman/doorman/protocols/customer.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/protocols/customer.py:8>)

- `AuthCustomerInfo` e o DTO minimo para autenticacao: `uuid`, `name`, `phone`, `email`, `is_active`.
- `CustomerResolver` precisa resolver por telefone, email e UUID, e tambem criar por telefone/email.

Forca da spec:

- Esse boundary e o ponto mais limpo do pacote. E ele que torna o pacote potencialmente standalone.

## Fluxos canonicos

### OTP login

Arquivo-chave: [`packages/doorman/shopman/doorman/services/verification.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/services/verification.py:67>)

- Normaliza o target via adapter.
- Checa permissao de login.
- Aplica rate limit por target.
- Aplica cooldown entre envios.
- Aplica rate limit por IP quando o IP existe.
- Expira codigos anteriores do mesmo target + purpose.
- Gera `raw_code` e `hmac_digest`.
- Persiste o digest e envia o raw code.
- Em caso de sucesso, marca `sent` e emite signal.
- Para verificacao, busca o codigo mais recente ainda valido.
- Se o codigo bate, resolve ou cria `customer`.
- Se houver `request`, faz login Django e preserva session keys configuradas.
- Emite `verification_code_verified`.
- Faz best-effort link do identificador verificado no Guestman.

### Access link exchange

Arquivo-chave: [`packages/doorman/shopman/doorman/services/access_link.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/services/access_link.py:83>)

- Cria token curto para um `customer`.
- Gera URL completa com `reverse("shopman_auth:access-exchange")` e token em querystring.
- Emite signal de criacao.
- Na troca, procura o token por HMAC.
- Valida gate de expiracao/uso/audience.
- Resolve customer pelo adapter.
- Gera ou recupera `User`.
- Marca token como usado.
- Faz `login()` com `ModelBackend`.
- Preserva session keys.
- Emite `customer_authenticated`.

### Device trust

Arquivo-chave: [`packages/doorman/shopman/doorman/services/device_trust.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/services/device_trust.py:37>)

- Ao confirmar OTP, o cliente pode receber cookie HttpOnly com token HMAC.
- `check_device_trust()` valida cookie + customer ownership.
- `trust_device()` cria `TrustedDevice`, seta cookie e emite signal.
- `revoke_device()` desativa device atual e limpa cookie.
- `revoke_all()` desativa todos os devices do customer.

## Invariantes e contratos que o codigo realmente sustenta

- Nenhum token principal e persistido em plaintext.
- Nenhum codigo OTP e persistido em plaintext.
- Redirect de `next` passa por filtro de host/scheme.
- `request.customer` pode ser resolvido apos o `AuthenticationMiddleware`.
- A session do Django e a unidade de login final, nao o customer externo.
- `User` local e um artefato derivado do customer, nao a fonte de verdade.
- A trocas de token e verificacao de OTP sao operacoes transacionais no service layer, mas nao sao serializadas por row lock.

## Superficies publicas

### Views HTML e JSON

Arquivos-chave:

- [`packages/doorman/shopman/doorman/views/verification_code.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/views/verification_code.py:22>)
- [`packages/doorman/shopman/doorman/views/access_link.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/views/access_link.py:24>)
- [`packages/doorman/shopman/doorman/views/access_link_request.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/views/access_link_request.py:20>)

- `VerificationCodeRequestView` aceita form e JSON.
- `VerificationCodeVerifyView` aceita form e JSON.
- `AccessLinkCreateView` e API pura, protegida opcionalmente por chave.
- `AccessLinkExchangeView` converte token em sessao.
- `AccessLinkRequestView` oferece login por email em uma pagina simples.
- `LogoutView` e POST-only.
- `DeviceListView` lista devices confiaveis.
- `DeviceRevokeView` revoga device individual.
- `HealthCheckView` faz `SELECT 1`.

### API DRF

Arquivos-chave:

- [`packages/doorman/shopman/doorman/api/views.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/api/views.py:20>)
- [`packages/doorman/shopman/doorman/api/serializers.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/api/serializers.py:6>)

- `POST /api/auth/request-code/`
- `POST /api/auth/verify-code/`
- serializers aceitam alias `phone` e `target`
- `delivery_method` e choice field, mas sem validação semantica de negocio alem do enum

### Admin

Arquivo-chave: [`packages/doorman/shopman/doorman/admin.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/admin.py:16>)

- Admin e essencialmente read-only.
- Mostra estados, mas nunca deixa editar entidades de auth.
- Isso e coerente com robustez, mas limita onboarding operacional quando o time precisa de operacao manual assistida.

## UI/UX, Omotenashi-first, Mobile-first, WhatsApp-first

Arquivos-chave:

- [`packages/doorman/shopman/doorman/templates/auth/code_request.html`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/templates/auth/code_request.html:1>)
- [`packages/doorman/shopman/doorman/templates/auth/code_verify.html`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/templates/auth/code_verify.html:1>)
- [`packages/doorman/shopman/doorman/templates/auth/access_link_request.html`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/templates/auth/access_link_request.html:1>)

- A experiencia web existe, mas e minima, sem sistema visual, sem hierarquia forte e sem narrativa de onboarding.
- Os formularios estao corretos em HTML basico, porem ainda parecem prototipo funcional, nao uma experiencia omotenashi-first.
- O pacote e phone-first, nao WhatsApp-first de verdade: o default de delivery e WhatsApp, mas a UI nao guia o usuario por esse canal nem explora o contexto conversacional.
- Mobile-first e apenas parcial: `meta viewport` existe, `inputmode` e `autocomplete` existem, mas falta layout responsivo de fato e copy orientada a contexto.

## Segurança

Pontos fortes:

- HMAC em tokens e OTP.
- `compare_digest` em verificacao.
- Cookie de device trust e HttpOnly.
- `safe_redirect_url()` evita open redirect.
- API key para criacao de access link em producao.
- Rate limit, cooldown e limite de tentativas.
- Logs tentam evitar PII em valores de sessao.

Gaps reais:

- `Gates.access_link_validity()` e `AuthService.verify_for_login()` nao usam bloqueio por linha; concorrencia pode permitir dupla validacao.
- `Gates.rate_limit()` e os outros gates sao check-then-act sem atomicidade de backend externo, logo burst concorrente pode furar o limite.
- `AccessLinkService.exchange()` trata qualquer `GateError` como `TOKEN_EXPIRED`, apagando a diferenca entre expirado, reutilizado e audience incorreta.
- `AuthService.request_code()` e as views de API transformam falhas muito diferentes em `429`, o que estraga semantica para o cliente.
- `AccessLinkService.send_access_link()` tem parametro `sender` mas nao usa, o que promete injeccao de sender que nao existe.
- `DoormanConfig.ready()` nao valida que o resolver de cliente exista em producao, embora o default `NoopCustomerResolver` falhe em runtime em varios fluxos reais.

## Concorrencia e robustez

Arquivo-chave: [`packages/doorman/shopman/doorman/services/_user_bridge.py`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/services/_user_bridge.py:22>)

- A intencao de tratar corrida na criacao de `CustomerUser` existe, via `IntegrityError` retry.
- Isso protege o link, mas nao serializa a criacao do `User` em si, entao duas requests podem criar usuarios temporarios e matar um depois.
- Os fluxos de token e OTP dependem de leitura seguida de escrita sem `select_for_update`, o que e suficiente para testes locais, nao para garantia forte sob carga concorrente.

## Agnosticidade e core enxuto

Pontos a favor:

- `AuthCustomerInfo` e `CustomerResolver` sao bons boundaries.
- `NoopCustomerResolver` permite rodar sem Guestman.
- `DefaultAuthAdapter` concentra customizacao.
- `sender` e `delivery_chain` permitem troca de canal.

Pontos contra:

- `verify_for_login()` ainda importa `shopman.guestman` diretamente em `_link_verified_identifier()`, quebrando a promessa de isolamento.
- `PhoneOTPBackend` e `AccessLinkService.exchange()` usam backends hard-coded.
- `AccessLinkService` replica logica de envio de email que ja existe em `EmailSender`.
- O pacote e coeso, mas o core nao esta tao enxuto quanto a narrativa sugere.

## Distancia entre promessa e implementacao

Principais desvios:

- Promessa: OTP e access link como superficies coerentes e padronizadas. Realidade: `VerificationCodeVerifyView` cria e consome um `AccessLink` artificial apenas para reaproveitar o pipeline de login.
- Promessa: erro estruturado com `ErrorCode`. Realidade: as views HTTP/DRF frequentemente colapsam tudo em `400` ou `429`, e `TOKEN_USED` / `CODE_MAX_ATTEMPTS` quase nao aparecem.
- Promessa: agnosticidade. Realidade: o link de identificador verificado ainda depende de Guestman.
- Promessa: `sender` e `delivery_chain` flexiveis. Realidade: o caminho de access link por email ignora o parametro `sender`, e o caminho de OTP ainda tem partes fortemente acopladas a `DefaultAuthAdapter`.
- Promessa: producao segura. Realidade: `DoormanConfig.ready()` protege apenas alguns invariantes; faltam validacoes para resolver, delivery chain e consistencia do backend de login.

## Falhas fundamentais potenciais

- Reuso de access link dentro da janela de prefetch pode ser explorado como replay curto.
- Validacao concorrente sem lock pode permitir dupla autenticacao do mesmo token/codigo.
- Error mapping fraco pode quebrar integrações externas e frontends.
- Dependencia Guestman no path de melhor experiencia pode cair silenciosamente em modo degradado.
- A superficie web atual nao oferece onboarding realmente guiado, especialmente para WhatsApp-first.

## Serve como solucao standalone?

Resposta curta: parcialmente.

- Sim, para o nucleo de autenticacao de comercio, porque o boundary `CustomerResolver` permite plugar um backend proprio e o `NoopCustomerResolver` sustenta desenvolvimento e testes.
- Nao, se a exigencia for uma solucao standalone madura e agnostica sem dependencia conceitual de Guestman, porque o pacote ainda assume Guestman em um fluxo relevante e mistura onboarding/auth com conveniencias de integracao.
- Como modulo de auth/access para e-commerce, ele ja e forte. Como plataforma independente de identidade/acesso para dominios variados, ainda precisa limpar hard dependencies e endurecer concorrencia, validacao e semantica de erros.

## Correcoes prioritarias

1. Separar o login OTP do reuse artificial de `AccessLink` ou, no minimo, transformar essa dependencia em um hook explicito.
2. Mapear `ErrorCode` para status HTTP de forma deterministica em views e API.
3. Corrigir o namespace quebrado em [`packages/doorman/shopman/doorman/templates/auth/access_link_invalid.html`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/templates/auth/access_link_invalid.html:13>).
4. Validar `CUSTOMER_RESOLVER_CLASS`, `DELIVERY_CHAIN` e sender classes em startup.
5. Tornar as validacoes de token/codigo mais resistentes a corrida, idealmente com `select_for_update()` ou updates condicionais.
6. Remover ou implementar o parametro `sender` em `AccessLinkService.send_access_link()`.
7. Transformar a UX HTML em algo realmente mobile-first e contextual para login via WhatsApp/email.

## Resumo final

`doorman` tem uma base boa: HMAC, cookies seguros, session bridge, adapter/protocol, rate limit e testes de contrato. O pacote ja e util e plausivelmente adotavel.

Os principais deficits estao em tres areas: agnosticidade real, semantica de erros/contratos, e robustez sob concorrencia. A interface visual tambem ainda esta muito abaixo da ambicao de omotenashi-first / WhatsApp-first.

Em uma frase: e uma boa espinha dorsal de auth para comercio, mas ainda nao e um core totalmente enxuto, agnostico e consolidado o bastante para ser considerado plataforma independente sem algumas correcoes estruturais.
