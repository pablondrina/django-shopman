# Análise crítica do Django-Shopman (estado atual do repositório)

## Escopo e critério desta revisão

Esta revisão foi refeita do zero, com base prioritária no código do repositório atual, não em README ou docs.
O foco foi:

- qualidade e coerência do código;
- consistência entre camadas;
- riscos reais de operação;
- maturidade para uso em produção;
- pontos fortes arquiteturais que merecem ser preservados.

Arquivos-base inspecionados nesta rodada incluíram, entre outros:

- `packages/omniman/shopman/omniman/models/order.py`
- `packages/omniman/shopman/omniman/models/session.py`
- `packages/omniman/shopman/omniman/models/channel.py`
- `packages/omniman/shopman/omniman/services/modify.py`
- `packages/omniman/shopman/omniman/services/commit.py`
- `packages/omniman/shopman/omniman/management/commands/process_directives.py`
- `packages/stockman/shopman/stockman/models/quant.py`
- `packages/craftsman/shopman/craftsman/services/execution.py`
- `packages/guestman/shopman/guestman/contrib/loyalty/service.py`
- `packages/doorman/shopman/doorman/services/verification.py`
- `packages/payman/shopman/payman/service.py`
- `framework/shopman/flows.py`
- `framework/shopman/setup.py`
- `framework/shopman/services/payment.py`
- `framework/shopman/services/stock.py`
- `framework/shopman/services/availability.py`
- `framework/shopman/adapters/__init__.py`
- `framework/shopman/adapters/payment_mock.py`
- `framework/shopman/adapters/payment_stripe.py`
- `framework/shopman/adapters/payment_efi.py`
- `framework/shopman/adapters/stock.py`
- `framework/shopman/web/views/checkout.py`
- `framework/shopman/web/views/pedidos.py`
- `framework/project/settings.py`
- `Makefile`
- `framework/shopman/tests/test_concurrent_checkout.py`

## Veredito executivo

O repositório atual tem uma base arquitetural forte e incomum para um projeto novo.
Há clareza de domínio, boa separação por bounded context, uso consistente de transações e row locks em vários pontos importantes, e um esforço visível de transformar regras operacionais reais em estruturas de software reutilizáveis.

Ao mesmo tempo, o projeto ainda apresenta alguns desalinhamentos internos sérios entre contratos, especialmente na integração entre framework e adapters, e em partes da orquestração de estoque e configuração de canais. Esses pontos não são apenas imperfeições de design: alguns parecem capazes de quebrar fluxos reais, principalmente pagamento digital e reserva de estoque.

Minha leitura isenta é:

- o núcleo conceitual é bom;
- vários subdomínios isolados estão bem pensados;
- o framework orquestrador ainda tem zonas de drift entre intenção e implementação.

Hoje, eu classificaria o projeto assim:

- forte como arquitetura-base e laboratório de domínio;
- promissor como suite modular;
- ainda exigindo correções concretas antes de ser considerado confiável em produção para fluxos sensíveis.

## O que está forte no código

### 1. Separação de domínios é real, não apenas cosmética

A divisão entre `offerman`, `stockman`, `craftsman`, `omniman`, `guestman`, `doorman` e `payman` não parece um monorepo fatiado à força. Ela aparece no código como separação de responsabilidades de fato.

Exemplos:

- `offerman` concentra catálogo e preço-base;
- `stockman` concentra saldo, hold e movimento;
- `craftsman` concentra produção e work orders;
- `omniman` concentra sessão mutável, pedido selado, diretivas e canais;
- `guestman` concentra cliente e loyalty;
- `doorman` concentra autenticação OTP;
- `payman` concentra lifecycle de intenção/transação de pagamento.

Isso é um dos melhores aspectos do repositório atual.

### 2. Há maturidade transacional em vários pontos críticos

O projeto usa `transaction.atomic()` e `select_for_update()` em lugares relevantes, e isso não parece acidental.

Exemplos fortes:

- `CommitService._do_commit()` em `packages/omniman/.../services/commit.py`
- `Order.transition_status()` em `packages/omniman/.../models/order.py`
- `PaymentService` em `packages/payman/shopman/payman/service.py`
- `LoyaltyService._get_active_account_for_update()` em `packages/guestman/.../loyalty/service.py`
- `CraftExecution.close()` e `void()` em `packages/craftsman/.../services/execution.py`

### 3. `stockman` está entre as partes mais elegantes

O modelo `Quant` é bom. A ideia de um cache `_quantity` indexado por coordenada espaço-temporal (`position`, `target_date`, `batch`) é forte, prática e coerente com a operação de produção/estoque.

### 4. `doorman` está bem mais sólido do que a média de sistemas OTP caseiros

`packages/doorman/.../services/verification.py` e o sistema de Gates mostram boa disciplina:

- normalização de phone;
- cooldown;
- rate limit por target;
- rate limit por IP;
- HMAC para código;
- restauração de chaves de sessão após login.

### 5. O worker de diretivas ficou operacionalmente bom

`packages/omniman/.../management/commands/process_directives.py` está bom.

Pontos positivos:

- `select_for_update(skip_locked=True)`;
- marcação explícita de `running`;
- backoff exponencial;
- reaper para diretivas presas em `running`;
- `max_attempts` configurável;
- watch mode simples e operacional.

## Os problemas mais importantes encontrados no código

### 1. O contrato entre `framework/shopman/services/payment.py` e os adapters de pagamento está inconsistente
**Gravidade: crítica**

Este é o problema mais sério que encontrei.

#### O que o service espera

Em `framework/shopman/services/payment.py`, o framework trata o retorno dos adapters como objeto com atributos:

- `intent.intent_id`
- `intent.status`
- `intent.client_secret`
- `intent.expires_at`
- `intent.metadata`

Também trata resultados de captura/refund como objetos:

- `result.success`
- `result.transaction_id`

#### O que os adapters retornam

Os adapters atuais em:

- `framework/shopman/adapters/payment_mock.py`
- `framework/shopman/adapters/payment_stripe.py`
- `framework/shopman/adapters/payment_efi.py`

retornam dicts, não objetos. Além disso, usam assinatura de `create_intent()` incompatível com a chamada do framework.

Exemplo de incompatibilidade:

- o service chama `adapter.create_intent(amount_q=..., currency="BRL", reference=order.ref, metadata=...)`
- o adapter Stripe define `create_intent(order_ref: str, amount_q: int, method: str = "card", **config)`
- o adapter mock define `create_intent(order_ref: str, amount_q: int, method: str = "pix", **config)`

Ou seja: o framework passa `reference`, enquanto os adapters esperam `order_ref`.

#### Consequência prática

Pelo código atual, a integração de pagamento digital parece quebrável ou já quebrada em runtime, especialmente no fluxo `flows.py -> payment.initiate()`.

Mesmo quando a função rodar, há mais inconsistência depois:

- `services/payment.py` espera `intent.intent_id`;
- os adapters devolvem `intent_ref`.

Este ponto, sozinho, impede que eu considere a camada de pagamento do framework confiável.

### 2. A configuração de canal está internamente incoerente entre schema declarado e consumo em runtime
**Gravidade: alta**

`packages/omniman/.../models/channel.py` declara `config` com chaves reconhecidas como:

- `confirmation`
- `payment`
- `stock`
- `pipeline`
- `notifications`
- `rules`
- `flow`

Mas em `framework/shopman/flows.py`, o consumo não segue esse contrato de forma consistente.

Exemplos:

`BaseFlow.handle_confirmation()` lê:

- `confirmation_mode`
- `confirmation_timeout`

como se fossem chaves top-level.

Só que o schema do `Channel` indica `confirmation` como subobjeto.

Além disso, `get_flow(order)` usa:

- `config.get("flow", "base")`

como se `flow` fosse uma string com nome de fluxo.

Mas o próprio `Channel` descreve `flow` como estrutura com:

- `transitions`
- `terminal_statuses`
- `auto_transitions`
- `auto_sync_fulfillment`

Isso indica drift de contrato entre modelo e consumidores.

### 3. A adoção de holds de sessão para pedido pode sub-reservar estoque
**Gravidade: alta**

`framework/shopman/services/stock.py` descreve a estratégia de adoção de holds criados no cart antes do commit. A ideia é boa. A implementação, porém, me parece perigosa.

`_load_session_holds()` indexa holds por SKU. Depois `_pop_matching_hold()` pega um único `hold_id` por SKU, sem casar quantidade.

Se o cliente adiciona o mesmo SKU em mais de um passo, ajusta carrinho várias vezes ou consolida linhas antes do commit, o pedido final pode exigir uma quantidade maior do que a quantidade coberta pelo único hold adotado.

Depois, `stock.fulfill(order)` cumpre o hold real, não a intenção agregada.

### 4. `Order.emit_event()` pode ter condição de corrida na sequência de eventos
**Gravidade: média/alta**

Em `packages/omniman/.../models/order.py`, `emit_event()` calcula `MAX(seq)` e depois faz `+ 1` antes de criar `OrderEvent`.

Sem uma trava explícita no conjunto de eventos do pedido, duas emissões concorrentes podem ler o mesmo `MAX(seq)` e tentar gravar o mesmo próximo valor.

Há `UniqueConstraint(order, seq)`, o que protege a integridade final, mas isso significa que a concorrência pode se manifestar como erro operacional.

### 5. O serviço de disponibilidade assume estoque infinito para SKU não rastreado
**Gravidade: média**

Em `framework/shopman/services/availability.py`, se o SKU não está pausado e não existem posições/estoque no subsistema, o código trata o item como:

- `ok=True`
- `available_qty=999999`
- `untracked=True`

Entendo a intenção: manter compatibilidade para itens fora do subsistema de estoque.

Mas em produção isso também pode mascarar:

- produto que deveria estar no estoque mas não foi parametrizado;
- falha de integração;
- catálogo incompleto no subsistema de inventário.

### 6. O checkout perde precisão fracionária ao validar estoque
**Gravidade: média**

Em `framework/shopman/web/views/checkout.py`, `_check_cart_stock()` faz:

- `qty = int(Decimal(str(item.get("qty", 0))))`

Isso trunca quantidade fracionária.

Se a sessão suporta `Decimal` para qty, então o checkout está validando estoque com menos precisão do que o modelo de domínio suporta.

### 7. O projeto ainda usa graceful degradation em pontos onde talvez devesse falhar de forma mais dura
**Gravidade: média**

Há vários pontos onde o sistema captura exceções amplas e segue em frente.

Exemplos:

- `framework/shopman/flows.py` em `dispatch()`
- `framework/shopman/web/views/checkout.py` em defaults, loyalty e fallback de pagamento
- `packages/craftsman/.../services/execution.py` em `_call_inventory_on_close()` e `_call_inventory_on_void()`
- `framework/shopman/setup.py` na carga de handlers e backends

Isso não é necessariamente um defeito em si. Em alguns casos, é escolha correta.
O problema é que o uso dessa estratégia ainda parece amplo demais para falhas estruturais.

### 8. `setup.py` ainda carrega alguns defaults com cheiro de ambiente de teste
**Gravidade: média**

Em `framework/shopman/setup.py`, os fallbacks de backend fiscal/contábil usam:

- `shopman.tests._mocks.fiscal_mock`
- `shopman.tests._mocks.accounting_mock`

Funciona em ambiente de desenvolvimento, mas como default de runtime não é uma escolha elegante.

## Leitura por pacote

### Offerman
**Avaliação: boa base de catálogo**

Pontos positivos:

- `Product` é rico sem ser caótico;
- `reference_cost_q` foi corretamente externalizado para backend;
- `HistoricalRecords` é útil;
- `availability_policy` é bom gancho de expansão.

### Stockman
**Avaliação: uma das melhores partes do projeto**

Pontos positivos:

- `Quant` é bom;
- modelo de hold/move/quant é coerente;
- o domínio de estoque tem desenho forte.

Ponto de atenção:
o problema maior não está no core de estoque, mas na maneira como o framework adota e consome os holds.

### Craftsman
**Avaliação: forte no domínio, moderado na fronteira com integrações**

Pontos positivos:

- `WorkOrder` e `CraftExecution` mostram domínio real;
- snapshot de BOM no plan-time é boa decisão;
- locking e idempotência estão acima da média.

Ponto de atenção:
integração com inventário via fallback não-fatal pode ser branda demais dependendo do cenário.

### Omniman
**Avaliação: coração conceitual do sistema, mas ainda com drift em contratos**

Pontos positivos:

- `Session` mutável / `Order` selado é boa separação;
- `CommitService` é forte;
- worker de diretivas está bom.

Pontos de atenção:

- schema de channel/config inconsistente;
- `emit_event()` ainda merece endurecimento;
- adoção de holds de sessão me parece incompleta.

### Guestman
**Avaliação: sólido**

Pontos positivos:

- modelo de cliente é bom;
- loyalty usa lock corretamente;
- serviço é simples e robusto.

### Doorman
**Avaliação: surpreendentemente maduro**

Pontos positivos:

- OTP, cooldown, HMAC, rate limit, preservação de sessão;
- boa leitura;
- boa coesão.

### Payman
**Avaliação: o core isolado parece bom; o problema está na integração com o framework**

Pontos positivos:

- `PaymentService` é consistente;
- transições são claras;
- uso de lock é correto.

Ponto crítico:
o framework de pagamento ao redor dele não respeita o mesmo contrato.

## Operação em produção: avaliação direta

Há sinais claros de que o código já pensa em operação:

- `process_directives` com retry, backoff e reaper;
- suporte a Redis em `settings.py`;
- CSP/HSTS/secure cookies previstos;
- testes de concorrência em `framework/shopman/tests/test_concurrent_checkout.py`;
- `skip_locked` em worker;
- uso repetido de `select_for_update()`.

Isso é bom.
Mostra que produção não está fora da cabeça do projeto.

### O que ainda me impede de chamar de production-ready

1. Pagamento  
Enquanto o contrato service ↔ adapter estiver inconsistente, eu não chamaria a operação de pagamento de confiável.

2. Estoque  
Enquanto a adoção de holds de sessão puder sub-representar reserva real, eu não chamaria a operação de estoque sensível de segura.

3. Configuração por canal  
Enquanto o contrato de `Channel.config` estiver ambíguo, a previsibilidade de comportamento por canal continua vulnerável.

4. Política de fallback  
Ainda há vários pontos em que o sistema pode continuar rodando apesar de configuração ou integração defeituosa.

5. Default operacional  
O código ainda nasce em modo local/dev-first:
- SQLite por default;
- adapters mock por default;
- alguns fallbacks permissivos.

## Conclusão franca

Minha conclusão, olhando o código atual e não a promessa do projeto, é esta:

O Django-Shopman não é um projeto raso.
Há trabalho de domínio real aqui. A modelagem de operações, estoque, produção, sessão/pedido, loyalty e auth mostra intenção séria e, em vários trechos, execução competente.

Mas o repositório ainda sofre com um problema clássico de sistemas em rápida evolução:
os subdomínios amadureceram em ritmos diferentes, e o framework integrador ainda não está totalmente alinhado com os contratos reais desses núcleos.

Em termos práticos:

- como arquitetura-base: bom;
- como suite modular em evolução: muito promissor;
- como sistema pronto para confiar cegamente em produção, sobretudo em pagamento e estoque: ainda não.

## Prioridades que eu trataria primeiro

1. Unificar o contrato dos adapters de pagamento
   - assinatura;
   - shape de retorno;
   - DTO ou dict, mas um só.

2. Corrigir a lógica de adoção de holds
   - adoção por quantidade efetiva, não por um hold arbitrário;
   - ou recriação determinística no commit.

3. Definir um schema único e executável para `Channel.config`
   - e alinhar todos os consumidores.

4. Endurecer `Order.emit_event()` para concorrência real

5. Transformar `untracked stock = infinite` em política explícita
   - não fallback universal implícito.

6. Eliminar truncamento de qty fracionária no checkout

7. Revisar onde graceful degradation é aceitável e onde deve abortar
   - principalmente em integrações estruturais.

## Nota final

Se eu fosse resumir em uma frase:

> O Django-Shopman atual tem um núcleo de software autoral forte e interessante, mas ainda precisa reduzir o drift entre camadas para que a qualidade do domínio também apareça, sem ruído, na operação real.
