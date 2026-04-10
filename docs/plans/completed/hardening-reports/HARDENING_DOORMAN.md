# HARDENING_DOORMAN

## Escopo
Pacote analisado: `django-shopman/packages/doorman`

Objetivo deste hardening:
- fortalecer o Doorman como kernel de autenticação phone-first da suíte
- preservar o desacoplamento com Guestman
- reduzir ambiguidades entre OTP, access link e device trust
- elevar o nível de segurança operacional antes de tratá-lo como componente maduro de produção

---

## Veredito executivo

O Doorman já tem uma base boa:
- recorte de domínio claro
- desacoplamento razoável via `CustomerResolver` e adapter
- `User` do Django tratado como mecanismo de sessão, não como identidade principal
- OTP e device trust com hashing correto
- gates de rate limit, cooldown e validade bem pensados

Mas ainda há pontos críticos que precisam endurecimento, principalmente:
- `AccessLink.token` armazenado em plaintext
- duplicação entre service, adapter e infraestrutura de gates
- ambiguidade entre “phone-first” e “auth multi-canal”
- drift de naming (`Shopman Auth` vs `Doorman`)

---

## Classificação dos itens

### P0 — crítico
Itens que merecem correção prioritária antes de confiar no pacote como auth seguro em produção.

### P1 — alto
Itens importantes para consistência arquitetural e redução de risco operacional.

### P2 — médio
Itens de clareza, ergonomia e alinhamento conceitual.

### P3 — baixo
Polimento e limpeza.

---

## P0 — hardening crítico

### D0.1 — Não armazenar `AccessLink.token` em plaintext
**Situação atual**
- `AccessLink.token` é persistido em texto puro no banco.
- Isso contrasta com o padrão já adotado no próprio pacote:
  - `VerificationCode` usa HMAC do OTP
  - `TrustedDevice` usa HMAC do token do cookie

**Risco**
- vazamento de banco permite uso direto de tokens ainda válidos até a expiração
- inconsistência de segurança dentro do próprio bounded context

**Direção**
- migrar `AccessLink` para o mesmo padrão:
  - gerar token bruto apenas na criação
  - armazenar somente hash/HMAC
  - comparar via função de verificação
- manter apenas a versão bruta fora do banco, para entrega ao cliente

**Recomendação**
- criar helpers equivalentes aos de `VerificationCode` / `TrustedDevice`
- substituir lookup direto por `token=` por lookup via hash

---

## P1 — hardening alto

### D1.1 — Tornar explícita a política de reuso de access link
**Situação atual**
- `Gates.access_link_validity()` permite reuso por 60 segundos após `used_at`
- a justificativa é tolerar prefetch de navegador

**Leitura**
- isso pode ser decisão de design válida
- mas enfraquece a semântica de single-use estrito

**Direção**
- transformar isso em política explícita de configuração
- não deixar implícito como detalhe escondido em gate

**Recomendação**
- mover a janela para settings, por exemplo:
  - `ACCESS_LINK_REUSE_WINDOW_SECONDS`
- documentar claramente:
  - `0` = single-use estrito
  - `>0` = tolerância controlada a prefetch

---

### D1.2 — Escolher uma única superfície principal para envio de access link
**Situação atual**
- `AccessLinkService` envia email diretamente
- `DefaultAuthAdapter` também sabe enviar access link por email
- há duplicação de responsabilidade

**Risco**
- drift futuro
- templates e políticas divergentes
- dificuldade de customização consistente

**Direção**
- centralizar a entrega no adapter
- deixar o service coordenar lifecycle, não implementar política de delivery

**Recomendação**
- `AccessLinkService` deve:
  - criar token
  - delegar envio ao adapter
- o adapter deve concentrar:
  - email
  - whatsapp
  - sms
  - api/no-op
  - fallback e customizações

---

### D1.3 — Reduzir duplicidade conceitual de `GateError`
**Situação atual**
- `gates.py` tem sua própria infraestrutura de gate
- `exceptions.py` também define `GateError`/`GatingError`
- o pacote mostra mais de uma camada para o mesmo conceito

**Risco**
- confusão de import
- semântica espalhada
- crescimento de acoplamento acidental

**Direção**
- existir um único `GateError` canônico
- `gates.py` deve usar a exceção oficial do pacote

**Recomendação**
- manter `GateError` somente em `exceptions.py`
- remover duplicação conceitual em `gates.py`
- garantir import unificado em todo o pacote

---

### D1.4 — Formalizar o posicionamento “phone-first” vs “multi-canal”
**Situação atual**
- o pacote se apresenta como phone-first
- mas `VerificationCode` e adapter já antecipam email/sms/whatsapp
- a API OTP pública ainda assume `phone` explicitamente

**Leitura**
- isso não é necessariamente bug
- parece transição de escopo ainda não formalizada

**Direção**
Escolher uma das duas opções abaixo:

#### Opção A — manter estritamente phone-first
- OTP login só por telefone/WhatsApp
- email fica apenas para access link
- enums e superfícies devem refletir isso

#### Opção B — generalizar autenticação multi-canal
- request/verify por identificador genérico
- OTP por email também como fluxo de login de primeira classe
- API, adapter e normalização devem ser revistas de ponta a ponta

**Recomendação**
- no estágio atual, manter phone-first parece mais coerente
- generalização deve acontecer só quando o pacote estiver pronto para isso de forma integral

---

### D1.5 — Consolidar a política de `User` bridge como decisão arquitetural oficial
**Situação atual**
- `Customer` é a identidade principal
- `User` é criado sob demanda para sessão
- `CustomerUser` faz a ponte corretamente

**Leitura**
- isso é um acerto e deve ser preservado

**Direção**
- transformar essa decisão em contrato explícito do pacote
- evitar futuras derivações onde `User` passe a competir com `Customer`

**Recomendação**
- documentar de forma inequívoca:
  - Doorman autentica `Customer`
  - Django `User` é mecanismo de sessão e compatibilidade com auth framework
- manter `CustomerUser` como única ponte oficial

---

## P2 — hardening médio

### D2.1 — Melhorar mapeamento HTTP de erros na API OTP
**Situação atual**
- `RequestCodeView` responde com `429` para qualquer falha de request code relevante

**Problema**
- mistura rate limit, cooldown, falha de envio e outros casos sob uma única classe HTTP

**Direção**
- distinguir melhor:
  - `400` para input inválido
  - `429` para rate limit/cooldown
  - `503` ou `502` para falha de delivery, se aplicável
  - `404/403` para políticas de conta, quando necessário

**Recomendação**
- criar mapeamento explícito de `ErrorCode -> HTTP status`

---

### D2.2 — Revisar persistência e limpeza de `VerificationCode`
**Situação atual**
- códigos antigos são expirados e existe cleanup posterior
- isso é bom, mas o pacote tende a acumular histórico operacional sensível

**Direção**
- deixar clara a política de retenção
- separar o que é útil para auditoria do que é apenas ruído operacional

**Recomendação**
- manter cleanup periódico documentado
- considerar política específica por status:
  - pendente vencido
  - falhado
  - verificado
- considerar retenção mínima compatível com auditoria e segurança

---

### D2.3 — Revisar `AccessLinkSource` e `Audience` como enums de domínio estável
**Situação atual**
- `AccessLink` já carrega `Audience` e `Source`
- isso é bom, mas tende a crescer

**Direção**
- garantir que esses enums representem conceitos realmente estáveis
- evitar transformar o model em depósito de canais temporários

**Recomendação**
- manter enums enxutos
- novos casos muito específicos devem entrar por metadata, não por explosão de enums

---

### D2.4 — Revisar dependência formal de `shopman-guestman`
**Situação atual**
- `pyproject` declara dependência explícita de `shopman-guestman`
- ao mesmo tempo, a arquitetura interna usa resolver/adapter

**Leitura**
- isso pode ser design deliberado e aceitável
- mas reduz a força do desacoplamento em termos de distribuição

**Direção**
Escolher entre:

#### opção acoplada deliberada
- Doorman é auth oficial da suíte sobre Guestman
- dependência explícita permanece

#### opção mais plugável
- Guestman vira implementação-padrão do resolver
- dependência poderia se mover para extra/opcional

**Recomendação**
- se a meta for suíte integrada, a dependência explícita é defensável
- apenas documentar isso claramente para não vender falsa agnosticidade

---

## P3 — polimento e limpeza

### D3.1 — Corrigir drift de naming
**Situação atual**
- pacote é `Doorman`
- `__title__` ainda se apresenta como `Shopman Auth`

**Direção**
- alinhar nome do pacote, título interno e docs

**Recomendação**
- usar `Shopman Doorman`
- eliminar resquícios de naming anterior

---

### D3.2 — Revisar coesão entre `AuthService`, `AccessLinkService` e adapter
**Situação atual**
- a separação é boa, mas ainda existe certa sobreposição prática em delivery e política

**Direção**
- serviços coordenam lifecycle
- adapter centraliza customização e integração externa
- gates validam
- models mantêm invariantes locais

**Recomendação**
- documentar essas fronteiras internamente
- impedir expansão cruzada de responsabilidades

---

## Itens classificados como decisão de design, não defeito

### DD.1 — `Customer` como identidade principal e `User` como bridge
**Classificação**
- decisão correta de design
- deve ser preservada

### DD.2 — existência de `TrustedDevice`
**Classificação**
- decisão válida e útil
- melhora UX sem abandonar segurança, desde que a política seja bem documentada

### DD.3 — `CustomerResolver` + `DefaultAuthAdapter`
**Classificação**
- bom desenho
- acerto importante de desacoplamento

### DD.4 — reuso curto de access link para tolerar prefetch
**Classificação**
- não é bug automático
- é trade-off de segurança/ergonomia
- precisa ficar explícito e configurável

### DD.5 — dependência explícita de Guestman
**Classificação**
- pode ser totalmente válida se o objetivo for auth oficial da suíte
- não deve ser apresentada como agnosticidade total se não for esse o caso

---

## Roadmap sugerido

### Fase 1 — segurança essencial
- hash/HMAC para `AccessLink.token`
- explicitar/configurar janela de reuso
- consolidar `GateError`
- corrigir naming do pacote

### Fase 2 — coerência arquitetural
- centralizar delivery de access link no adapter
- definir oficialmente o escopo phone-first
- revisar mapeamento HTTP de erros
- documentar contrato `Customer` vs `User`

### Fase 3 — endurecimento operacional
- revisar políticas de retenção/cleanup
- revisar distribuição plugável vs dependência explícita de Guestman
- consolidar fronteiras entre service / adapter / gates / models

---

## Síntese final

O Doorman já é um bom núcleo de autenticação phone-first para a suíte.

Seus principais méritos hoje são:
- boa separação entre identidade e sessão
- OTP com hashing correto
- device trust bem pensado
- adapter/resolver como ponto de desacoplamento

Seus principais pontos de hardening são:
- `AccessLink` ainda abaixo do nível de rigor criptográfico do restante do pacote
- certa duplicidade entre camadas
- escopo conceitual ainda levemente ambíguo entre phone-first e auth multi-canal

Com os ajustes acima, o Doorman pode se tornar um componente forte e reutilizável da suíte Shopman.
