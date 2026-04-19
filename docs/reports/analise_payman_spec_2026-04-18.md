# Payman - análise crítica orientada a SPEC

Escopo estrito: `packages/payman/shopman/payman`

Método: leitura do código do pacote, dos testes do próprio pacote e das dependências estritamente necessárias para entender contratos públicos e transições. A suíte local do pacote passou com `118 passed, 2 skipped` na data desta análise.

## Leitura executiva

O `payman` tem um core pequeno e bem delimitado, com uma boa ideia central: `PaymentService` concentra mutações, `PaymentIntent` modela o estado do pagamento e `PaymentTransaction` registra eventos financeiros imutáveis. O pacote já demonstra robustez real em transições stateful, captura e reembolso, com locking concorrente e testes de contrato.

O principal problema não é ausência de intenção, e sim assimetria entre intenção e enforcement. A camada de serviço é disciplinada, mas a camada de modelo ainda permite bypass relevante na criação e em mutações diretas; a API é só leitura; o contrato de gateway existe como protocolo, mas está desconectado da implementação; e há conceitos críticos de pagamento que existem só parcialmente, como expiração, chargeback, idempotência, escopo de acesso e auditoria de motivos.

## Specs extraídas por entidade

### `PaymentIntent`

Arquivo-chave: [`packages/payman/shopman/payman/models/intent.py:8`](../../packages/payman/shopman/payman/models/intent.py#L8)

- A entidade é a âncora do domínio de pagamento e referencia o pedido por `order_ref` como string, sem FK.
- `ref` é o identificador externo estável, único, com geração automática `PAY-` + 12 hex uppercase quando não fornecido.
- `status` segue o ciclo `pending -> authorized -> captured -> refunded` e os desvios `pending -> failed/cancelled`, `authorized -> cancelled/failed`, com `captured -> refunded`.
- `amount_q` é inteiro positivo em moeda mínima, com constraint de banco para `> 0`.
- `method` suporta `pix`, `cash`, `card`, `external`.
- `currency` default é `BRL`, mas o código não valida semanticamente o código ISO no serviço.
- `gateway`, `gateway_id` e `gateway_data` existem como metadados de integração, porém sem enforcement forte de integridade ou unicidade.
- `authorized_at`, `captured_at` e `cancelled_at` são timestamps automáticos de transição; `failed_at` e `refunded_at` não existem.
- `expires_at` existe como limite temporal, mas a expiração só é verificada na autorização, não como estado operacional do próprio intent.
- `is_terminal` considera `failed`, `cancelled` e `refunded` como terminais.
- `transition_status()` é um helper interno para concorrência com `select_for_update`, mas a docstring promete que mutações devem passar pelo serviço.

Contrato relevante:

- `REFUNDED` não significa reembolso total; significa apenas que existe ao menos um refund.
- Capture é single-shot. Mesmo capture parcial consome o intent inteiro para novas capturas.
- A intenção declarada é "service as mutation surface", mas `save()` só bloqueia transições de status em instâncias persistidas. Criações diretas ainda podem nascer com status arbitrário válido.

### `PaymentTransaction`

Arquivo-chave: [`packages/payman/shopman/payman/models/transaction.py:5`](../../packages/payman/shopman/payman/models/transaction.py#L5)

- A transação é o registro financeiro imutável ligado ao intent por `PROTECT`.
- `type` suporta `capture`, `refund`, `chargeback`.
- `amount_q` também é constraint positivo no banco.
- `save()` bloqueia atualização após criação, e `delete()` sempre levanta erro.
- A transação é a fonte de verdade para somatórios de capture e refund.

Gap importante:

- `chargeback` existe como tipo, mas não há método de serviço nem fluxo de estado correspondente. Hoje ele é um tipo solto, não um comportamento do domínio.

### `PaymentService`

Arquivo-chave: [`packages/payman/shopman/payman/service.py:69`](../../packages/payman/shopman/payman/service.py#L69)

- É a superfície mutável oficial.
- Todas as operações de escrita usam `@transaction.atomic` e `select_for_update()` via `_get_for_update()`.
- A API pública real é maior que a narrada na docstring: além dos verbos `create_intent`, `authorize`, `capture`, `refund`, `cancel`, há `fail`, `get`, `get_by_order`, `get_active_intent`, `get_by_gateway_id`, `captured_total` e `refunded_total`.
- `create_intent()` valida apenas `amount_q > 0`; não valida `method`, `currency`, `gateway_id` ou unicidade funcional por pedido.
- `authorize()` só aceita `pending`, checa expiração e grava `authorized_at`.
- `capture()` só aceita `authorized`, calcula captura total ou parcial, proíbe excesso sobre o autorizado e grava `PaymentTransaction`.
- `refund()` aceita `captured` ou `refunded`, calcula disponível como `captured_total - refunded_total`, permite múltiplos refunds parciais e muda o status para `refunded` no primeiro refund.
- `cancel()` e `fail()` mudam o status sem registrar transação financeira; `fail()` guarda erro em `gateway_data`, `cancel()` só loga o motivo.
- `get_active_intent()` retorna o intent não terminal mais recente por `created_at`, mas não exclui expirados.

Leitura funcional:

- O core de dinheiro está bem definido: intenção, captura, estorno e cancelamento.
- O core de gateway está apenas esboçado: o serviço não conversa com `PaymentBackend`, não há adaptação real entre gateway externo e estado interno, e não há idempotency key.

### Protocol boundary

Arquivo-chave: [`packages/payman/shopman/payman/protocols.py:21`](../../packages/payman/shopman/payman/protocols.py#L21)

- Existem DTOs frozen para intenção do gateway, resultado de captura, resultado de refund e status.
- Há um `PaymentBackend` protocol com `create_intent`, `authorize`, `capture`, `refund`, `cancel`, `get_status`.
- O boundary é útil como spec, mas hoje é decorativo: nenhuma parte do pacote usa o protocolo de forma efetiva.
- `authorize()` retorna `CaptureResult`, o que mistura semântica de autorização e captura e tende a contaminar implementações futuras.

## Fluxos e transições

Arquivo de referência: [`packages/payman/shopman/payman/models/intent.py:46`](../../packages/payman/shopman/payman/models/intent.py#L46)

- Pending aceita authorize, fail ou cancel.
- Authorized aceita capture, fail ou cancel.
- Captured aceita refund.
- Failed, cancelled e refunded são terminais.
- A transição é validada tanto em `PaymentService` quanto em `PaymentIntent.save()` quando há mudança de status em instância persistida.
- `transition_status()` existe para cenários concorrentes e os testes de concorrência provam a intenção de serialização de linha.

Nuance importante:

- A máquina de estados é robusta no caminho feliz e no caminho bloqueado, mas não é uma garantia global do banco. Criações diretas e `QuerySet.update()` ainda escapam da disciplina do serviço.

## Invariantes e contratos que o código realmente sustenta

- `amount_q` em intent e transação é sempre positivo quando o objeto passa pelo fluxo normal.
- Um intent capturado não aceita nova captura.
- Um refund não pode exceder o capturado disponível.
- Refund parcial sucessivo é permitido até zerar o saldo capturado.
- `refunded_total()` é a verdade financeira, não o status `refunded`.
- `PaymentTransaction` não deve ser alterada ou deletada depois de criada.
- O intent pode coexistir com múltiplas transações de refund, mas nunca com múltiplas capturas.

## Superfícies públicas

### API read-only

Arquivo-chave: [`packages/payman/shopman/payman/api/views.py:14`](../../packages/payman/shopman/payman/api/views.py#L14)

- `PaymentIntentViewSet` expõe listagem e detalhe por `ref`.
- `ActiveIntentView` busca o intent ativo mais recente para um `order_ref`.
- Ambas as views exigem autenticação, mas não existe escopo por tenant, usuário, loja ou domínio de negócio.
- A API não expõe mutações, webhooks ou comandos de reconciliação.

### Serialização

Arquivo-chave: [`packages/payman/shopman/payman/api/serializers.py:8`](../../packages/payman/shopman/payman/api/serializers.py#L8)

- O serializer de detalhe inclui o histórico de transações.
- `gateway_data` não é exposto pela API.
- O serializer de listagem é mínimo, o que é bom para leitura, mas não resolve governança de acesso.

## Erros

Arquivo-chave: [`packages/payman/shopman/payman/exceptions.py:8`](../../packages/payman/shopman/payman/exceptions.py#L8)

- O pacote usa uma exceção única `PaymentError` com `code`, `message` e `context`.
- Códigos realmente emitidos pelo serviço: `invalid_amount`, `invalid_transition`, `capture_exceeds_authorized`, `amount_exceeds_captured`, `already_refunded`, `intent_not_found`, `intent_expired`.
- O modelo de erro é bom para máquina e humano, mas ainda é estreito para a superfície que o domínio exige.

Gaps:

- Não há erro específico para método/currency inválidos, gateway duplicado, autorização não autorizada por escopo, expiração operacional ou conflito de idempotência.

## Concorrência

Arquivo-chave: [`packages/payman/shopman/payman/tests/test_concurrency.py:1`](../../packages/payman/shopman/payman/tests/test_concurrency.py#L1)

- O core trata concorrência com `select_for_update` e transação atômica por operação.
- Os testes de concorrência existem e documentam a intenção de serialização entre capture/cancel.
- A cobertura concorrente real está condicionada ao backend de banco; no ambiente local ela foi saltada em SQLite.

Leitura crítica:

- A estratégia é correta para row-level locking.
- O problema está antes disso: se o código contorna o serviço ou cria o objeto já em estado inválido, a concorrência não protege o contrato.

## Segurança

Arquivo-chave: [`packages/payman/shopman/payman/api/views.py:17`](../../packages/payman/shopman/payman/api/views.py#L17)

- A API exige autenticação, mas não faz autorização por objeto nem por domínio de dados.
- Isso significa que um usuário autenticado pode listar e recuperar intents de qualquer `order_ref` se a view estiver exposta sem camadas adicionais.
- Não há proteção explícita contra enumeração de `ref` ou vazamento de relacionamento entre pedido, gateway e status.
- `gateway_data` não vaza pela API, o que é um acerto.

Em termos de standalone seguro, isso ainda está aquém do aceitável para um core financeiro multi-uso.

## Onboarding e elegância

- Para quem usa Python e Django por dentro, a entrada é simples: um service, dois modelos, sinais e serializers enxutos.
- Para quem integra via HTTP, a experiência é incompleta porque a API é apenas leitura.
- A ideia de protocol é elegante, mas o pacote ainda não fecha o ciclo entre spec, adapter e execução.
- A separação entre intent e transaction é boa e evita um modelo monolítico de pagamento.

## Distância entre promessa e implementação

- A promessa de "core agnóstico" é parcialmente verdadeira. O core não depende de gateway específico, mas também não oferece uma ponte concreta para gateways reais.
- A promessa de "all mutations through PaymentService" é forte na narrativa, mas fraca como enforcement. A criação direta do model ainda pode nascer com status arbitrário válido e não há validação de choices por `full_clean`.
- A promessa de "payment core completo" é forte demais para o que o pacote entrega hoje. Ele cobre lifecycle básico com boa disciplina, mas não cobre bem expiração operacional, chargeback, idempotência, auth de domínio, ou auditoria de motivos.

## Falhas fundamentais potenciais

- Falta validação de criação no modelo ou no serviço para impedir intent já nascida em estado terminal/inválido.
- Falta uma noção operacional de `expired`, não só um timestamp de validade.
- Falta uma política explícita para `gateway_id` como identificador de reconciliação, inclusive índice e unicidade.
- Falta persistir motivos de cancelamento e refund em estrutura consultável, não apenas em log.
- Falta alinhar protocolo de gateway com a semântica real do domínio, especialmente `authorize`.
- Falta escopo de acesso no read API para uso seguro em múltiplos domínios/tenants.

## Serve como standalone?

Como núcleo interno de pagamentos para um app Django, sim: a modelagem de estado é enxuta, a disciplina transacional é boa e os testes cobrem o essencial.

Como solução standalone para servir aplicações diversas que delegam resolução confiável de pagamentos em diferentes domínios, ainda não. O pacote ainda carece de:

- fronteira de adapter real para gateway;
- autorização e isolamento de dados por domínio/tenant;
- idempotência de comandos;
- expiração como estado de domínio;
- chargeback como fluxo de primeira classe;
- trilha de auditoria consultável;
- enforcement mais forte contra bypass do serviço.

## Correções prioritárias

- Validar `method`, `currency` e `status` na criação, de preferência com `full_clean()` ou guardas explícitas no serviço e no modelo.
- Adicionar `failed_at` e, se fizer sentido, `refunded_at` ou um audit/event log de lifecycle.
- Tratar intent expirada como não ativa e, idealmente, como estado explícito do domínio.
- Indexar e possivelmente tornar único `gateway_id` por gateway.
- Persistir `reason` de cancelamento e refund em campo próprio ou registro de evento.
- Reconciliar `PaymentBackend` com o serviço ou rebaixá-lo de contrato público até existir implementação real.
- Proteger a API com escopo de acesso por entidade de negócio.
- Definir se `chargeback` entra no core ou sai do modelo até haver fluxo completo.

## Síntese final

O `payman` já tem uma base tecnicamente séria: a máquina de estados é clara, as transações são imutáveis, o uso de locks é correto e os testes mostram boa maturidade do fluxo básico. O que ainda o impede de ser um payment core robusto e standalone não é a falta de ideias, mas a falta de fechamento de contrato em pontos que são decisivos em produção: validação de criação, expiração, autorização de acesso, idempotência, reconciliação e auditoria.
