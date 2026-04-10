# Análise crítica do Django-Shopman — revisão reconsiderada

## Escopo

Esta versão revisa a análise anterior com base no estado atual do código do repositório.

O objetivo aqui não é apenas repetir o parecer anterior, mas recalibrar o peso dos achados após nova leitura cruzada dos módulos centrais.

A base da revisão continua sendo o código executável, especialmente:

- `packages/omniman/shopman/omniman/models/order.py`
- `packages/omniman/shopman/omniman/services/commit.py`
- `packages/omniman/shopman/omniman/models/channel.py`
- `framework/shopman/config.py`
- `framework/shopman/flows.py`
- `framework/shopman/services/payment.py`
- `framework/shopman/services/stock.py`
- `framework/shopman/services/availability.py`
- `framework/shopman/handlers/notification.py`
- `framework/shopman/webhooks/stripe.py`
- `framework/shopman/webhooks/efi.py`
- `framework/shopman/web/views/checkout.py`
- `framework/shopman/apps.py`
- `framework/shopman/setup.py`
- `framework/shopman/tests/test_concurrent_checkout.py`

---

## O que eu revisaria da análise anterior

Depois de reconsiderar o código atual, eu faria um ajuste importante no tom da avaliação:

- eu fui severo demais em alguns pontos que já foram efetivamente corrigidos;
- ao mesmo tempo, deixei passar alguns desalinhamentos mais concretos no runtime.

Em outras palavras:

> o Django-Shopman atual está melhor do que a análise anterior fazia parecer, mas os problemas que restam estão mais concentrados no alinhamento interno do kernel e do runtime do que em falhas grosseiras de arquitetura.

---

## Pontos que melhoraram de verdade

### 1. A camada de pagamento está substancialmente melhor

A antiga fragilidade do contrato entre orchestration service e adapters foi tratada de forma correta com a introdução de DTOs explícitos:

- `PaymentIntent`
- `PaymentResult`

Agora existe um contrato canônico entre `framework/shopman/services/payment.py` e os adapters `payment_mock.py`, `payment_stripe.py` e `payment_efi.py`.

Isso melhora muito a previsibilidade da integração e reduz o drift que antes existia entre service e adapters.

### 2. A lógica de adoção de holds evoluiu de forma material

A adoção de holds em `framework/shopman/services/stock.py` não é mais o modelo simplista de “um hold por SKU”.

A implementação agora:

- indexa holds por `(hold_id, qty)`;
- consome múltiplos holds até cobrir a quantidade requerida;
- cria hold complementar só para o saldo faltante.

Essa mudança resolve um problema real de sangria entre carrinho, sessão e pedido selado.

### 3. A separação entre flow nominal e flow configurável ficou melhor

`Channel` agora tem um campo `flow` explícito, e `framework/shopman/flows.py` passou a resolver a classe de flow por `channel.flow`.

Isso melhora bastante a distinção entre:

- nome do flow em runtime;
- e customizações estruturais do flow em `config`.

---

## O que continua forte no projeto

### 1. A arquitetura modular continua sendo um dos maiores méritos

A separação entre `offerman`, `stockman`, `craftsman`, `omniman`, `guestman`, `doorman` e `payman` continua sólida.

Não parece uma divisão artificial. Os pacotes carregam responsabilidades reais e relativamente bem delimitadas.

### 2. A disciplina transacional está acima da média

O uso de `transaction.atomic()` e `select_for_update()` em serviços importantes continua sendo um dos pontos mais fortes do projeto.

Isso aparece de forma convincente em:

- commit
- loyalty
- payment core
- work orders
- worker de diretivas

### 3. O worker de diretivas permanece uma peça madura

`process_directives.py` continua sendo um dos componentes mais operacionais do sistema.

Pontos positivos:

- `skip_locked`
- reaper para stuck directives
- retry com backoff
- separação razoável entre aquisição e processamento

### 4. Guestman, Doorman e Craftsman seguem entre os módulos mais confiáveis

Esses módulos continuam passando a impressão de domínio bem internalizado, com pouco ruído estrutural.

---

## O que eu destacaria mais agora

### 1. O kernel do pedido ainda parece meio passo atrás do `ChannelConfig`
**Gravidade: alta**

Este é, hoje, o ponto estrutural que eu considero mais importante.

Em `Order`, os métodos que resolvem transições e terminalidade ainda leem `channel.config["order_flow"]`.

Mas o sistema já evoluiu para um contrato em que:

- `channel.flow` define a classe do flow;
- `config["flow"]` deveria concentrar a customização do fluxo.

Isso sugere que a nova abstração de configuração ainda não chegou por completo ao núcleo do pedido.

### 2. O `CommitService` ainda opera parcialmente fora da configuração tipada
**Gravidade: alta**

A checagem de `required_checks_on_commit` ainda é lida diretamente do JSON cru do canal, e não da camada tipada/cascável de `ChannelConfig`.

Isso mantém duas linguagens de configuração coexistindo:

- a formal;
- e a ad hoc.

Num sistema que está claramente tentando consolidar configuração em uma abstração única, isso é um desalinhamento importante.

### 3. A camada de notificação parece consumir a fonte errada para itens do pedido
**Gravidade: alta**

No commit, os itens são selados em `order.snapshot["items"]`.

Mas `NotificationSendHandler` monta contexto com `order.data.get("items", [])`.

Isso sugere que a notificação pode sair sem a lista real de itens do pedido, ou com contexto incompleto.

Esse é um problema de runtime mais concreto do que várias críticas arquiteturais abstratas.

### 4. O vocabulário de auto-transition por pagamento parece ter drift de naming
**Gravidade: média/alta**

Nos webhooks Stripe e EFI, a chave lida em `auto_transitions` é `on_payment_confirm`.

Já o restante do sistema usa fortemente vocabulário como `on_payment_confirmed` ou `on_paid`.

Não é prova definitiva de bug, porque `auto_transitions` é um mapa livre, mas o sinal de drift é forte o suficiente para merecer atenção.

### 5. `Order.emit_event()` continua com fragilidade concorrente
**Gravidade: média/alta**

A sequência de eventos do pedido ainda é calculada como `MAX(seq) + 1` sem lock explícito do stream de eventos.

A unique constraint reduz dano, mas não elimina a possibilidade de disputa em concorrência real.

### 6. O checkout ainda simplifica qty fracionária
**Gravidade: média**

A validação de estoque no checkout continua reduzindo qty a `int(...)`.

Isso mantém a borda do sistema menos precisa que o modelo central.

### 7. O fallback `untracked = disponível` continua permissivo demais
**Gravidade: média**

Eu manteria essa crítica.

Ela tem utilidade operacional, mas ainda mascara facilmente:

- ausência de parametrização;
- integração faltante;
- item fora do subsistema sem intenção explícita.

### 8. O startup do framework continua tolerando falhas demais
**Gravidade: média**

`apps.py` e `setup.py` ainda capturam exceções amplas durante o bootstrap e seguem adiante.

Isso é confortável em dev, mas perigoso em produção porque permite sistema parcialmente montado.

### 9. Os defaults continuam dev-first em excesso
**Gravidade: média**

O projeto ainda nasce com defaults que fazem sentido para desenvolvimento rápido, mas não para confiança operacional alta:

- SQLite default
- LocMem como fallback
- mocks de runtime vindos de `tests`

---

## O que eu suavizaria da crítica anterior

Eu reduziria o peso relativo destas críticas antigas:

### Pagamento
A crítica anterior era correta para versões passadas, mas o estado atual melhorou bastante. Hoje o problema já não é “contrato quebrado”; é mais validação de integração fina e concorrência end-to-end.

### Adoção de holds
A crítica forte ao modelo antigo já não descreve bem o código atual.

### Nome do flow vs config do flow
O sistema ainda não está 100% consistente, mas já está melhor do que antes e a separação principal foi resolvida.

---

## Leitura geral atual do projeto

Hoje, olhando com mais justiça, eu diria:

- a base conceitual do Django-Shopman é boa;
- vários subdomínios já estão maduros o bastante para inspirar confiança;
- o que falta não é “reinventar o projeto”, e sim alinhar alguns pontos do núcleo para que a arquitetura e o runtime contem a mesma história.

Isso é um bom sinal.

Projetos fracos pedem reconstrução. Aqui, o que eu vejo é um projeto que pede refinamento e consolidação.

---

## Avaliação final reconsiderada

Se eu resumisse em linguagem direta:

> O Django-Shopman atual é um projeto autoral forte, com arquitetura modular convincente e vários núcleos já maduros; o principal trabalho restante está em fechar drift internos entre configuração, kernel do pedido e runtime operacional.

Em termos práticos, hoje eu avaliaria assim:

- **arquitetura de domínio:** forte
- **modularidade:** forte
- **clareza conceitual:** forte
- **maturidade de alguns subdomínios isolados:** boa a muito boa
- **consistência total do framework integrador:** intermediária
- **confiabilidade de produção sem ressalvas:** ainda não plena, mas em trajetória boa

---

## Prioridades que eu trataria agora

1. alinhar `Order` ao contrato novo de `ChannelConfig.flow`
2. mover checks de commit para dentro da camada tipada/cascável de config
3. corrigir o sourcing de itens usado por notificações
4. revisar o naming/runtime de auto-transitions por pagamento
5. endurecer `emit_event()` para concorrência real
6. remover truncamento de qty fracionária no checkout
7. reduzir tolerância excessiva no bootstrap do framework
8. tirar mocks de runtime do namespace de testes

---

## Conclusão

Minha conclusão reconsiderada é mais favorável do que a anterior.

Eu não retiraria a crítica, mas a refinaria assim:

> o Django-Shopman está melhor do que parecia na análise anterior, e os problemas que restam são mais de alinhamento fino do núcleo do que de deficiência arquitetural pesada.