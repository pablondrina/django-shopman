# Análise crítica do Django-Shopman — estado atual do repositório

## Escopo

Esta revisão foi refeita com foco no código efetivo do repositório atualizado, não em README ou documentação como base principal de julgamento.

A inspeção concentrou-se em módulos que definem o comportamento real do sistema:

- núcleo de pedidos (`omniman`)
- estoque e disponibilidade (`stockman` + `framework/shopman/services/stock.py` e `availability.py`)
- pagamentos (`payman` + adapters + orchestration service)
- flows e bootstrap do framework
- checkout storefront
- worker de diretivas
- serviços transacionais representativos como loyalty e crafting
- settings e defaults de operação

## Síntese executiva

O projeto está melhor e mais coerente do que nas revisões anteriores. Algumas fragilidades importantes realmente foram corrigidas no código:

1. o contrato da camada de pagamento foi explicitado com DTOs (`PaymentIntent`, `PaymentResult`);
2. a adoção de holds de sessão passou a considerar quantidade, não apenas SKU;
3. o `Channel` agora separa melhor o nome do flow (`channel.flow`) da configuração do flow (`config["flow"]`).

Isso é relevante porque mostra evolução real, não apenas narrativa.

Ainda assim, o repositório continua com alguns drift internos importantes, especialmente no encontro entre:

- modelagem declarada de canal/configuração;
- leitura efetiva dessa configuração no kernel do pedido;
- garantias reais de concorrência e idempotência em partes do framework.

Minha leitura atual, tentando ser estritamente isenta, é:

- o projeto tem boa base arquitetural e excelente potencial;
- vários subdomínios isolados já estão em nível bom ou muito bom;
- o framework orquestrador ainda contém pontos em que a implementação ficou meio passo atrás da arquitetura.

Hoje eu o classificaria assim:

- forte como suíte modular e base de domínio
- promissor para operação real
- ainda não totalmente confiável para fluxos críticos sem alguns acertos adicionais

## Melhoras concretas observadas em relação às versões anteriores

### 1. Contrato de pagamento finalmente ficou explícito

A inclusão de `framework/shopman/adapters/payment_types.py` foi uma boa decisão.

Agora existe um contrato canônico com:

- `PaymentIntent`
- `PaymentResult`

E `framework/shopman/services/payment.py` foi atualizado para consumir esse contrato por atributo, de forma consistente com a nova abstração.

Além disso, os adapters `payment_mock.py`, `payment_stripe.py` e `payment_efi.py` aderem ao formato novo, ao menos nos pontos principais.

Isso corrige um dos problemas mais sérios que existiam antes.

### 2. Adoção de holds melhorou de verdade

`framework/shopman/services/stock.py` agora não faz mais adoção “um hold por SKU e pronto”.

A nova lógica:

- indexa holds por `(hold_id, qty)`;
- consome múltiplos holds até cobrir a quantidade necessária;
- cria hold complementar só para o saldo não coberto.

Essa correção é real e importante.

### 3. O conflito entre nome do flow e config do flow foi parcialmente resolvido

`packages/omniman/.../models/channel.py` agora tem um campo `flow` próprio, e `framework/shopman/flows.py` usa `channel.flow` para resolver a classe do flow.

Isso reduz bastante a ambiguidade que existia antes.

## O que continua forte no código

### 1. A separação em pacotes continua sendo uma força real

A divisão entre:

- `offerman`
- `stockman`
- `craftsman`
- `omniman`
- `guestman`
- `doorman`
- `payman`

não parece cosmética.

Cada pacote mantém um centro de gravidade relativamente claro, e isso continua sendo um dos maiores méritos do projeto.

### 2. A disciplina transacional segue acima da média

O uso de `transaction.atomic()` e `select_for_update()` em pontos certos continua sendo um diferencial.

Exemplos bons:

- `CommitService`
- `PaymentService`
- `LoyaltyService`
- `CraftExecution.close()` / `void()`
- worker de diretivas com `skip_locked`

### 3. O worker de diretivas continua bem desenhado

`packages/omniman/.../management/commands/process_directives.py` continua sendo uma das peças mais honestas e bem resolvidas do sistema.

Pontos fortes:

- aquisição com `select_for_update(skip_locked=True)`
- marcação de `running`
- reaper de stuck directives
- retry com backoff exponencial
- modo `--watch` simples, mas operacional

### 4. `guestman` e `craftsman` continuam entre os módulos mais sólidos

#### Guestman / Loyalty
`packages/guestman/.../contrib/loyalty/service.py` continua bom:

- coeso;
- transacional;
- usa lock na conta;
- simples de seguir.

#### Craftsman / Execution
`packages/craftsman/.../services/execution.py` continua forte no domínio:

- row lock em work order;
- idempotência interna;
- snapshot de BOM no plan-time;
- eventos com seq própria.

## Os problemas mais relevantes que ainda encontrei

### 1. A customização de transições por canal continua com drift no núcleo do pedido
**Gravidade: alta**

Em `packages/omniman/.../models/order.py`, os métodos `get_transitions()` e `get_terminal_statuses()` ainda leem `self.channel.config.get("order_flow", {})`.

Só que o contrato novo do sistema aponta para:

- `channel.flow` → nome da classe de Flow
- `channel.config["flow"]` → customização de transições/terminalidade

A consequência provável é que a customização declarada em `ChannelConfig.flow` não esteja realmente sendo aplicada no `Order`.

Isso afeta validação de transição, terminalidade e comportamento por canal.

### 2. `CommitService` ainda consome configuração fora do `ChannelConfig`
**Gravidade: alta**

Em `packages/omniman/.../services/commit.py`, a lógica de checks obrigatórios lê `channel.config.get("required_checks_on_commit", [])`.

Esse campo:

- não faz parte do `ChannelConfig` declarado;
- não participa claramente da cascata `channel ← shop ← defaults`;
- fica como convenção solta no JSON cru.

Isso enfraquece justamente a melhoria estrutural recente da camada de configuração.

### 3. `Order.emit_event()` continua vulnerável a corrida de sequência
**Gravidade: média/alta**

`emit_event()` continua calculando `MAX(seq)` e depois `+ 1` antes de criar `OrderEvent`, sem lock explícito sobre a sequência de eventos daquele pedido.

A constraint única protege a integridade final, mas não evita disputa concorrente pelo mesmo `seq`.

### 4. O checkout continua truncando quantidade fracionária ao validar estoque
**Gravidade: média**

Em `framework/shopman/web/views/checkout.py`, `_check_cart_stock()` ainda faz `qty = int(Decimal(str(item.get("qty", 0))))`.

Isso derruba a parte fracionária e faz a borda web operar com menos precisão do que o modelo central suporta.

### 5. A política de “SKU não rastreado = disponível infinito” continua forte demais
**Gravidade: média**

Em `framework/shopman/services/availability.py`, se o SKU não está pausado e não há posições registradas, o sistema continua retornando algo equivalente a:

- `ok=True`
- `available_qty=999999`
- `untracked=True`

Isso preserva compatibilidade, mas também mascara cadastro incompleto, integração faltante e item fora do subsistema de estoque sem intenção explícita.

### 6. O bootstrap do framework ainda mascara falhas estruturais
**Gravidade: média**

`framework/shopman/apps.py` e `framework/shopman/setup.py` ainda têm vários pontos com `except Exception` amplos durante o startup.

Isso permite que a aplicação suba parcialmente quebrada, com wiring incompleto, em vez de falhar cedo.

### 7. `setup.py` ainda usa mocks de teste como fallback de runtime
**Gravidade: média**

`framework/shopman/setup.py` ainda tenta carregar:

- `shopman.tests._mocks.fiscal_mock`
- `shopman.tests._mocks.accounting_mock`

quando não há backend configurado.

Isso mistura ambiente de testes, defaults de runtime e boot do sistema real.

### 8. A história de concorrência em captura de pagamento ainda não está tão provada quanto o teste sugere
**Gravidade: média**

`framework/shopman/tests/test_concurrent_checkout.py` continua sugerindo que “exatamente 1 capture succeeds” na corrida de captura.

Mas o teste efetivo:

- usa mock;
- não trava a linha do `Order`;
- e no final aceita `capture_count["n"] >= 1`, não `== 1`.

Isso significa que a garantia real ainda está menos demonstrada do que o nome e os comentários do teste aparentam.

## Leitura por pacote

### Offerman
**Avaliação: boa base de catálogo**

Continua bom como módulo de catálogo e produto.

### Stockman
**Avaliação: forte**

Continua sendo um dos melhores núcleos. Os problemas mais relevantes hoje não estão no core de estoque em si, mas no modo como o framework interpreta `untracked` e opera na borda do checkout.

### Craftsman
**Avaliação: forte no domínio**

Módulo bom, com bons sinais de maturidade. O ponto que ainda incomoda é a tolerância excessiva nas integrações de inventário quando elas falham.

### Omniman
**Avaliação: centro do sistema, ainda com drift interno**

Continua sendo o coração do projeto. Também continua sendo onde aparecem os problemas mais sensíveis:

- transições por canal;
- evento com sequência frágil;
- commit parcialmente fora do `ChannelConfig`.

### Guestman
**Avaliação: sólido**

Poucas críticas. Bom módulo.

### Doorman
**Avaliação: continua maduro**

Mesmo sem ter sido o foco principal desta rodada, segue parecendo uma das partes mais bem comportadas da suite.

### Payman
**Avaliação: melhorou muito**

O maior defeito anterior — contrato frouxo com os adapters — foi corrigido. Hoje o `payman` isolado está em situação bem melhor.

## Operação em produção: avaliação atual

### O que já mostra preocupação real com produção

- worker com retry/reaper
- Redis opcional
- CSP/HSTS/cookies seguros previstos
- row locks em vários serviços
- testes de concorrência para cenários importantes
- separação razoável entre gateway externo e core de pagamento

### O que ainda impede chamar de totalmente pronto para confiança alta

1. configuração de fluxo do pedido ainda não está totalmente alinhada no kernel
2. commit ainda escapa do `ChannelConfig` em um ponto importante
3. startup ainda tolera falhas estruturais demais
4. checkout ainda simplifica quantidade fracionária
5. fallback de item não rastreado continua permissivo demais
6. defaults ainda são muito dev-first
   - SQLite default
   - LocMem no cache
   - mocks como fallback em partes do wiring

## Conclusão franca

O Django-Shopman atual está em um estado mais maduro e mais coerente do que nas rodadas anteriores. Isso precisa ser dito com clareza.

As correções feitas em:

- contrato de pagamento,
- adoção de holds,
- separação `channel.flow` / `config["flow"]`

foram mudanças reais e boas.

Mas o projeto ainda mostra um padrão recorrente: a arquitetura evolui, e uma ou duas camadas do núcleo ficam parcialmente para trás.

Hoje, minha conclusão é esta:

- o projeto já tem cara de sistema sério;
- alguns subdomínios já estão bons de verdade;
- o framework principal ainda precisa de mais um ciclo de alinhamento interno para que a execução acompanhe integralmente a intenção da arquitetura.

Em uma frase:

> O Django-Shopman melhorou de forma material, mas ainda precisa fechar alguns drift do núcleo antes de merecer confiança plena em fluxos críticos de produção.

## Prioridades que eu trataria agora

1. alinhar `Order.get_transitions()` e `get_terminal_statuses()` ao `ChannelConfig.flow`
2. mover checks obrigatórios de commit para dentro do `ChannelConfig.effective()`
3. endurecer `Order.emit_event()` para concorrência real
4. remover truncamento de qty fracionária no checkout
5. transformar `untracked stock` em política explícita
6. fazer o bootstrap falhar cedo quando wiring essencial quebrar
7. tirar mocks de runtime do namespace de testes
8. fortalecer o teste de corrida de captura para provar o que ele afirma